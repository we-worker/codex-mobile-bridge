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

var authURLPattern = regexp.MustCompile(`https://login\.tailscale\.com/[^\s<>"']+`)

// Mobile is generated as a Java class by gomobile.
type Mobile struct {
	mu           sync.Mutex
	generation   uint64
	state        string
	authURL      string
	errorCode    string
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
	server := &tsnet.Server{
		Dir:      root,
		Hostname: hostname,
		AuthKey:  authKey,
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
	m.state = stateStarting
	m.authURL = ""
	m.errorCode = ""
	m.proxyAddress = ""
	m.cancel = cancel
	m.done = make(chan struct{})
	m.server = server
	m.mu.Unlock()

	log.SetFlags(0)
	log.SetOutput(io.Discard)

	proxy, err := startConnectProxy(ctx, server.Dial)
	if err != nil {
		cancel()
		_ = server.Close()
		m.finishStartFailure(generation, "proxy_failed")
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
	_, err := server.Up(ctx)
	if err != nil {
		m.mu.Lock()
		if generation == m.generation {
			m.authURL = ""
			if ctx.Err() != nil {
				m.state = stateStopped
				m.errorCode = ""
			} else {
				m.state = stateFailed
				m.errorCode = mobileErrorCode(err)
			}
		}
		m.mu.Unlock()
		return
	}
	m.mu.Lock()
	if generation == m.generation {
		m.authURL = ""
		m.errorCode = ""
		m.state = stateReady
	}
	m.mu.Unlock()
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

func (m *Mobile) finishStartFailure(generation uint64, code string) {
	m.mu.Lock()
	if generation == m.generation {
		m.state = stateFailed
		m.errorCode = code
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
