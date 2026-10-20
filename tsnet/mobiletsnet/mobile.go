// Package mobiletsnet exposes a userspace Tailscale node and a loopback HTTP
// CONNECT proxy for gomobile. It never creates a VPN interface or changes
// system routes.
package mobiletsnet

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"

	"tailscale.com/tsnet"
)

const Version = "1.0.0"

const (
	stateStopped      = "stopped"
	stateStarting     = "starting"
	stateAuthRequired = "auth_required"
	stateReady        = "ready"
	stateFailed       = "failed"
)

const authKeyStartupTimeout = 75 * time.Second

var (
	authURLPattern        = regexp.MustCompile(`https://login\.tailscale\.com/[^\s<>"']+`)
	authLoginPattern      = regexp.MustCompile(`(?i)https://login\.tailscale\.com/[^\s<>"']+`)
	authKeyPattern        = regexp.MustCompile(`(?i)\btskey-[a-z0-9][a-z0-9_-]{5,}\b`)
	keyIdentifierPattern  = regexp.MustCompile(`(?i)\b(?:auth|api) key\s+[a-z0-9_-]{8,}\b`)
	authorizationPattern  = regexp.MustCompile(`(?i)\bbearer\s+[a-z0-9._~+/=-]{8,}`)
	deviceSecretPattern   = regexp.MustCompile(`(?i)\b[a-z0-9_-]{40,}\b`)
	diagnosticLinePattern = regexp.MustCompile(`[\x00-\x1f\x7f]+`)
)

// Mobile is generated as a Java class by gomobile.
type Mobile struct {
	mu           sync.Mutex
	generation   uint64
	state        string
	authURL      string
	errorCode    string
	errorDetail  string
	diagnostic   string
	controlPlane string
	proxyAddress string
	cancel       context.CancelFunc
	done         chan struct{}
	server       *tsnet.Server
	proxy        *connectProxy
}

// NewMobile returns an idle embedded Tailscale client.
func NewMobile() *Mobile {
	return &Mobile{state: stateStopped}
}

// Start joins the configured tailnet asynchronously. Interactive authorization
// is surfaced through Status and AuthURL while the Go goroutine waits for Up.
func (m *Mobile) Start(stateDir, hostname, authKey string) error {
	if m == nil {
		return errors.New("mobile Tailscale instance is nil")
	}
	root, err := validateStart(stateDir, hostname, authKey)
	if err != nil {
		return err
	}
	if err := prepareRuntimeDirectories(root); err != nil {
		return err
	}

	m.mu.Lock()
	if m.state == stateFailed {
		m.mu.Unlock()
		m.Stop()
		m.mu.Lock()
	}
	if m.state == stateStarting || m.state == stateAuthRequired || m.state == stateReady {
		m.mu.Unlock()
		return errors.New("mobile Tailscale is already running")
	}
	m.generation++
	generation := m.generation
	ctx, cancel := context.WithCancel(context.Background())
	m.state = stateStarting
	m.authURL = ""
	m.errorCode = ""
	m.errorDetail = ""
	m.diagnostic = "正在探测 Tailscale 控制面网络"
	m.controlPlane = ""
	m.proxyAddress = ""
	m.cancel = cancel
	m.done = nil
	m.server = nil
	m.proxy = nil
	m.mu.Unlock()

	selection := chooseMobileControlURL(ctx)
	m.mu.Lock()
	if generation != m.generation || ctx.Err() != nil {
		m.mu.Unlock()
		cancel()
		return errors.New("mobile Tailscale start was cancelled")
	}
	server := &tsnet.Server{
		Dir:        root,
		Hostname:   hostname,
		AuthKey:    authKey,
		ControlURL: selection.URL,
		UserLogf: func(format string, args ...any) {
			authURL := safeAuthorizationURLFromLog(fmt.Sprintf(format, args...))
			if authURL == "" {
				return
			}
			m.mu.Lock()
			defer m.mu.Unlock()
			if generation == m.generation && (m.state == stateStarting || m.state == stateAuthRequired) {
				m.authURL = authURL
				m.state = stateAuthRequired
			}
		},
		Logf: func(string, ...any) {},
	}
	m.done = make(chan struct{})
	m.server = server
	m.diagnostic = selection.Detail
	m.controlPlane = selection.URL
	m.mu.Unlock()

	log.SetFlags(0)
	log.SetOutput(io.Discard)

	proxy, err := startConnectProxy(ctx, server.Dial)
	if err != nil {
		cancel()
		_ = server.Close()
		m.finishStartFailure(generation, "proxy_failed", safeErrorDetail(err))
		return err
	}

	m.mu.Lock()
	if generation != m.generation {
		m.mu.Unlock()
		proxy.close()
		cancel()
		_ = server.Close()
		return errors.New("mobile Tailscale start was cancelled")
	}
	m.proxy = proxy
	m.proxyAddress = proxy.address()
	done := m.done
	m.mu.Unlock()

	go m.run(ctx, generation, server, done)
	return nil
}

func (m *Mobile) run(ctx context.Context, generation uint64, server *tsnet.Server, done chan struct{}) {
	defer close(done)
	upCtx := ctx
	cancel := func() {}
	m.mu.Lock()
	hasAuthKey := server.AuthKey != ""
	m.mu.Unlock()
	if hasAuthKey {
		upCtx, cancel = context.WithTimeout(ctx, authKeyStartupTimeout)
	}
	defer cancel()
	_, err := server.Up(upCtx)
	if err != nil {
		m.mu.Lock()
		if generation == m.generation {
			m.authURL = ""
			if ctx.Err() != nil {
				m.state = stateStopped
				m.errorCode = ""
				m.errorDetail = ""
				m.diagnostic = ""
			} else {
				m.state = stateFailed
				if errors.Is(upCtx.Err(), context.DeadlineExceeded) {
					m.errorCode = "network_timeout"
					m.errorDetail = "Tailscale 节点启动超过 75 秒，请检查控制面网络后重试"
				} else {
					m.errorCode = mobileErrorCode(err)
					m.errorDetail = safeErrorDetail(err)
				}
			}
		}
		m.mu.Unlock()
		return
	}
	m.mu.Lock()
	if generation == m.generation {
		m.authURL = ""
		m.errorCode = ""
		m.errorDetail = ""
		m.diagnostic = networkDiagnostic(server)
		m.state = stateReady
	}
	m.mu.Unlock()
}

func networkDiagnostic(server *tsnet.Server) string {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	client, err := server.LocalClient()
	if err != nil {
		return "Tailscale 节点已连接"
	}
	status, err := client.Status(ctx)
	if err != nil {
		return "Tailscale 节点已连接"
	}
	parts := []string{"Tailscale 节点已连接"}
	if len(status.TailscaleIPs) > 0 {
		parts = append(parts, "本机 "+status.TailscaleIPs[0].String())
	}
	if status.CurrentTailnet != nil && status.CurrentTailnet.StableID != "" {
		parts = append(parts, "Tailnet "+string(status.CurrentTailnet.StableID))
	}
	if status.Self != nil && status.Self.UserID != 0 {
		parts = append(parts, fmt.Sprintf("用户 %d", status.Self.UserID))
	}
	parts = append(parts, fmt.Sprintf("可见设备 %d", len(status.Peer)))
	peers := make([]string, 0, len(status.Peer))
	for _, peer := range status.Peer {
		if len(peer.TailscaleIPs) > 0 {
			peers = append(peers, fmt.Sprintf("%s:%t", peer.TailscaleIPs[0], peer.Online))
		}
	}
	sort.Strings(peers)
	if len(peers) > 0 {
		parts = append(parts, "对端 "+strings.Join(peers, ","))
	}
	return strings.Join(parts, " · ")
}

// Stop is safe in every lifecycle state and waits briefly for the node to exit.
func (m *Mobile) Stop() {
	if m == nil {
		return
	}
	m.mu.Lock()
	if m.state == "" || m.state == stateStopped {
		m.mu.Unlock()
		return
	}
	m.generation++
	m.state = stateStopped
	m.authURL = ""
	m.errorCode = ""
	m.errorDetail = ""
	m.diagnostic = ""
	m.controlPlane = ""
	m.proxyAddress = ""
	cancel := m.cancel
	done := m.done
	server := m.server
	proxy := m.proxy
	m.cancel = nil
	m.done = nil
	m.server = nil
	m.proxy = nil
	m.mu.Unlock()

	if proxy != nil {
		proxy.close()
	}
	if cancel != nil {
		cancel()
	}
	if server != nil {
		_ = server.Close()
	}
	if done != nil {
		select {
		case <-done:
		case <-time.After(5 * time.Second):
		}
	}
}

func (m *Mobile) Status() string {
	if m == nil {
		return stateStopped
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.state == "" {
		return stateStopped
	}
	return m.state
}

func (m *Mobile) AuthURL() string {
	if m == nil {
		return ""
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.authURL
}

func (m *Mobile) ProxyAddress() string {
	if m == nil {
		return ""
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.proxyAddress
}

func (m *Mobile) ErrorCode() string {
	if m == nil {
		return ""
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.errorCode
}

// ErrorDetail returns a bounded, credential-redacted explanation suitable for
// an on-device diagnostic screen or logcat.
func (m *Mobile) ErrorDetail() string {
	if m == nil {
		return ""
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.errorDetail
}

// Diagnostic describes the current startup stage without exposing credentials.
func (m *Mobile) Diagnostic() string {
	if m == nil {
		return ""
	}
	m.mu.Lock()
	if m.state != stateReady || m.server == nil {
		value := m.diagnostic
		m.mu.Unlock()
		return value
	}
	generation := m.generation
	server := m.server
	m.mu.Unlock()

	value := networkDiagnostic(server)
	m.mu.Lock()
	if m.generation == generation && m.state == stateReady && m.server == server {
		m.diagnostic = value
	}
	m.mu.Unlock()
	return value
}

// ControlPlane returns the selected public control URL, or empty when the
// embedded client is using its default resolver.
func (m *Mobile) ControlPlane() string {
	if m == nil {
		return ""
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.controlPlane
}

func validateStart(stateDir, hostname, authKey string) (string, error) {
	if stateDir == "" {
		return "", errors.New("state directory is required")
	}
	root, err := filepath.Abs(stateDir)
	if err != nil {
		return "", fmt.Errorf("resolve state directory: %w", err)
	}
	if err := os.MkdirAll(root, 0o700); err != nil {
		return "", fmt.Errorf("create state directory: %w", err)
	}
	if len(hostname) > 63 || !regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9-]{0,62}$`).MatchString(hostname) {
		return "", errors.New("invalid Tailscale hostname")
	}
	if len(authKey) > 16384 || strings.ContainsAny(authKey, "\x00\r\n") {
		return "", errors.New("invalid Tailscale auth key")
	}
	return root, nil
}

func prepareRuntimeDirectories(root string) error {
	logsDir := filepath.Join(root, "logs")
	tempDir := filepath.Join(root, "tmp")
	for _, dir := range []string{logsDir, tempDir} {
		if err := os.MkdirAll(dir, 0o700); err != nil {
			return fmt.Errorf("create embedded Tailscale runtime directory: %w", err)
		}
	}
	if err := os.Setenv("TS_LOGS_DIR", logsDir); err != nil {
		return fmt.Errorf("configure embedded Tailscale log directory: %w", err)
	}
	if err := os.Setenv("TMPDIR", tempDir); err != nil {
		return fmt.Errorf("configure embedded Tailscale temporary directory: %w", err)
	}
	return nil
}

func safeAuthorizationURLFromLog(value string) string {
	match := authURLPattern.FindString(value)
	if match == "" {
		return ""
	}
	match = strings.TrimRight(match, ".,);]}")
	if !safeAuthorizationURL(match) {
		return ""
	}
	return match
}

func safeAuthorizationURL(value string) bool {
	parsed, err := url.Parse(value)
	if err != nil || parsed.Scheme != "https" || parsed.Hostname() != "login.tailscale.com" ||
		parsed.User != nil || parsed.RawQuery != "" {
		return false
	}
	return parsed.Port() == "" || parsed.Port() == "443"
}

func mobileErrorCode(err error) string {
	text := strings.ToLower(err.Error())
	switch {
	case strings.Contains(text, "invalid key") || strings.Contains(text, "api key"):
		return "auth_key_invalid"
	case strings.Contains(text, "auth") || strings.Contains(text, "login") || strings.Contains(text, "machine"):
		return "authentication_failed"
	case strings.Contains(text, "context canceled"):
		return "stopped"
	case strings.Contains(text, "network") || strings.Contains(text, "dial"):
		return "network_failed"
	default:
		return "tailscale_failed"
	}
}

func (m *Mobile) finishStartFailure(generation uint64, code, detail string) {
	m.mu.Lock()
	if generation == m.generation {
		m.state = stateFailed
		m.errorCode = code
		m.errorDetail = detail
		m.proxyAddress = ""
		done := m.done
		m.cancel = nil
		m.done = nil
		m.server = nil
		m.proxy = nil
		m.mu.Unlock()
		if done != nil {
			close(done)
		}
		return
	}
	m.mu.Unlock()
}

func safeErrorDetail(err error) string {
	if err == nil {
		return ""
	}
	value := diagnosticLinePattern.ReplaceAllString(err.Error(), " ")
	value = authLoginPattern.ReplaceAllString(value, "[已隐藏授权链接]")
	value = authKeyPattern.ReplaceAllString(value, "[已隐藏密钥]")
	value = keyIdentifierPattern.ReplaceAllString(value, "[已隐藏 Tailscale 密钥]")
	value = authorizationPattern.ReplaceAllString(value, "[已隐藏令牌]")
	value = deviceSecretPattern.ReplaceAllString(value, "[已隐藏设备密钥]")
	value = strings.Join(strings.Fields(value), " ")
	runes := []rune(value)
	if len(runes) > 320 {
		value = string(runes[:317]) + "..."
	}
	return value
}
