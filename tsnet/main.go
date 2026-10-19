// Command codex-tsnet owns one userspace Tailscale node for the desktop bridge.
package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/netip"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"tailscale.com/tsnet"
)

const (
	version               = "1.0.1"
	controlPlaneHost      = "controlplane.tailscale.com"
	controlProbeTimeout   = 4 * time.Second
	authKeyStartupTimeout = 75 * time.Second
)

var authURLPattern = regexp.MustCompile(`https://login\.tailscale\.com/[^\s<>"']+`)

type launchConfig struct {
	AuthKey string `json:"authKey"`
}

type statusRecord struct {
	State      string `json:"state"`
	Code       string `json:"code,omitempty"`
	AuthURL    string `json:"authUrl,omitempty"`
	URL        string `json:"url,omitempty"`
	NodeID     string `json:"nodeId,omitempty"`
	InstanceID string `json:"instanceId,omitempty"`
	Version    string `json:"version,omitempty"`
	Message    string `json:"message,omitempty"`
}

type statusWriter struct {
	mu     sync.Mutex
	output io.Writer
}

func (w *statusWriter) write(value statusRecord) {
	w.mu.Lock()
	defer w.mu.Unlock()
	_ = json.NewEncoder(w.output).Encode(value)
}

func main() {
	log.SetFlags(0)
	log.SetOutput(io.Discard)

	var stateDir, hostname, mode, upstream, expectedInstance string
	var port int
	flag.StringVar(&stateDir, "state-dir", "", "private directory for the embedded node state")
	flag.StringVar(&hostname, "hostname", "codex-mobile-bridge", "Tailscale device hostname")
	flag.StringVar(&mode, "mode", "serve", "serve or funnel")
	flag.IntVar(&port, "port", 443, "HTTPS listener port")
	flag.StringVar(&upstream, "upstream", "", "loopback HTTP upstream")
	flag.StringVar(&expectedInstance, "instance-id", "", "gateway instance expected behind the listener")
	flag.Parse()

	status := &statusWriter{output: os.Stdout}
	if err := validateFlags(stateDir, hostname, mode, port, upstream, expectedInstance); err != nil {
		status.write(statusRecord{State: "failed", Code: "invalid_configuration", Version: version})
		return
	}
	launch, err := readLaunch(os.Stdin)
	if err != nil {
		status.write(statusRecord{State: "failed", Code: "invalid_launch", Version: version})
		return
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if err := run(ctx, status, launch, stateDir, hostname, mode, port, upstream, expectedInstance); err != nil {
		status.write(statusRecord{State: "failed", Code: errorCode(err), Version: version})
	}
}

func run(ctx context.Context, output *statusWriter, launch launchConfig, stateDir, hostname, mode string, port int, upstream, expectedInstance string) error {
	if err := os.MkdirAll(stateDir, 0o700); err != nil {
		return fmt.Errorf("create state directory: %w", err)
	}
	root, err := filepath.Abs(stateDir)
	if err != nil {
		return fmt.Errorf("resolve state directory: %w", err)
	}

	output.write(statusRecord{
		State:   "starting",
		Message: "正在探测 Tailscale 控制面网络…",
		Version: version,
	})
	controlURL := chooseControlURL(ctx)

	var authMu sync.Mutex
	currentAuthURL := ""
	server := &tsnet.Server{
		Dir:        root,
		Hostname:   hostname,
		AuthKey:    launch.AuthKey,
		ControlURL: controlURL,
		UserLogf: func(format string, args ...any) {
			match := authURLPattern.FindString(fmt.Sprintf(format, args...))
			if match == "" || !safeAuthorizationURL(match) {
				return
			}
			authMu.Lock()
			changed := currentAuthURL != match
			currentAuthURL = match
			authMu.Unlock()
			if changed {
				output.write(statusRecord{
					State:   "auth_required",
					AuthURL: match,
					Version: version,
				})
			}
		},
		Logf: func(string, ...any) {},
	}
	defer server.Close()

	output.write(statusRecord{
		State:   "connecting",
		Message: "正在连接 Tailscale 控制面并登录内嵌节点…",
		Version: version,
	})
	upCtx := ctx
	cancel := func() {}
	if launch.AuthKey != "" {
		upCtx, cancel = context.WithTimeout(ctx, authKeyStartupTimeout)
	}
	defer cancel()
	status, err := server.Up(upCtx)
	if err != nil {
		if errors.Is(upCtx.Err(), context.DeadlineExceeded) {
			return errors.New("startup timed out")
		}
		return fmt.Errorf("join tailnet: %w", err)
	}
	if len(status.CertDomains) == 0 {
		return errors.New("HTTPS is not enabled for this tailnet")
	}
	dnsName := strings.TrimSuffix(status.Self.DNSName, ".")
	if dnsName == "" {
		return errors.New("tailnet did not provide a device DNS name")
	}
	nodeID := string(status.Self.ID)
	if nodeID == "" {
		return errors.New("tailnet did not provide a stable device ID")
	}
	deviceURL := "https://" + dnsName
	if port != 443 {
		deviceURL += ":" + strconv.Itoa(port)
	}

	var listener net.Listener
	if mode == "funnel" {
		listener, err = server.ListenFunnel("tcp", ":"+strconv.Itoa(port))
	} else {
		listener, err = server.ListenTLS("tcp", ":"+strconv.Itoa(port))
	}
	if err != nil {
		return fmt.Errorf("listen on tailnet: %w", err)
	}
	defer listener.Close()

	target, _ := url.Parse(upstream)
	proxy := newProxy(target)
	httpServer := &http.Server{
		Handler:           proxy,
		ReadHeaderTimeout: 15 * time.Second,
		IdleTimeout:       2 * time.Minute,
		MaxHeaderBytes:    1 << 20,
	}
	serveErrors := make(chan error, 1)
	go func() {
		serveErrors <- httpServer.Serve(listener)
	}()

	output.write(statusRecord{State: "verifying", URL: deviceURL, NodeID: nodeID, Version: version})
	instanceID := verifyLoopback(ctx, server, deviceURL, expectedInstance)
	if instanceID != expectedInstance {
		return errors.New("verify gateway instance")
	}
	output.write(statusRecord{
		State:      "listening",
		URL:        deviceURL,
		NodeID:     nodeID,
		InstanceID: instanceID,
		Version:    version,
	})

	select {
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = httpServer.Shutdown(shutdownCtx)
		return nil
	case err := <-serveErrors:
		if errors.Is(err, http.ErrServerClosed) || errors.Is(err, net.ErrClosed) {
			return nil
		}
		return fmt.Errorf("serve tailnet listener: %w", err)
	}
}

func newProxy(target *url.URL) *httputil.ReverseProxy {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.Proxy = nil
	transport.MaxIdleConns = 100
	transport.MaxIdleConnsPerHost = 16
	transport.IdleConnTimeout = 90 * time.Second
	transport.ResponseHeaderTimeout = 30 * time.Second
	transport.ExpectContinueTimeout = 1 * time.Second
	proxy := &httputil.ReverseProxy{
		Transport:     transport,
		FlushInterval: -1,
		Rewrite: func(request *httputil.ProxyRequest) {
			originalHost := request.In.Host
			request.SetURL(target)
			// The Python gateway validates the externally visible Host and
			// Origin pair. Preserve the exact .ts.net authority.
			request.Out.Host = originalHost
			request.SetXForwarded()
			request.Out.Header.Set("X-Forwarded-Proto", "https")
			request.Out.Header.Set("X-Forwarded-Host", originalHost)
			request.Out.Header.Set("X-Forwarded-Port", targetPort(originalHost))
		},
		ErrorHandler: func(response http.ResponseWriter, request *http.Request, err error) {
			response.Header().Set("Content-Type", "text/plain; charset=utf-8")
			response.WriteHeader(http.StatusBadGateway)
			_, _ = io.WriteString(response, "Codex Mobile Bridge upstream unavailable\n")
		},
	}
	return proxy
}

func targetPort(authority string) string {
	_, port, err := net.SplitHostPort(authority)
	if err == nil {
		return port
	}
	return "443"
}

// chooseControlURL avoids a Tailscale DNS cache trap on networks where the
// control plane rotates between several anycast addresses and some of those
// addresses are temporarily unreachable. We still use the system resolver,
// but probe all addresses returned across a few lookups before handing a
// reachable endpoint to tsnet.
func chooseControlURL(ctx context.Context) string {
	if strings.TrimSpace(os.Getenv("TS_CONTROL_URL")) != "" {
		return ""
	}
	addresses := resolveControlPlane(ctx)
	if len(addresses) == 0 {
		return ""
	}
	if value := firstReachableControlURL(ctx, addresses, dialControlPlane); value != "" {
		return value
	}
	return ""
}

func resolveControlPlane(ctx context.Context) []netip.Addr {
	seen := make(map[netip.Addr]bool)
	var result []netip.Addr
	for attempt := 0; attempt < 3 && ctx.Err() == nil; attempt++ {
		lookupCtx, cancel := context.WithTimeout(ctx, 2*time.Second)
		addresses, err := net.DefaultResolver.LookupNetIP(lookupCtx, "ip4", controlPlaneHost)
		cancel()
		if err == nil {
			for _, address := range addresses {
				address = address.Unmap()
				if address.Is4() && !seen[address] {
					seen[address] = true
					result = append(result, address)
				}
			}
		}
		if attempt != 2 {
			select {
			case <-ctx.Done():
				return result
			case <-time.After(150 * time.Millisecond):
			}
		}
	}
	return result
}

func firstReachableControlURL(ctx context.Context, addresses []netip.Addr, dial func(context.Context, string, string) (net.Conn, error)) string {
	type result struct {
		url string
	}
	results := make(chan result, len(addresses))
	probeCtx, cancel := context.WithTimeout(ctx, controlProbeTimeout)
	defer cancel()
	for _, address := range addresses {
		address := address
		go func() {
			conn, err := dial(probeCtx, "tcp", net.JoinHostPort(address.String(), "443"))
			if err == nil {
				_ = conn.Close()
				select {
				case results <- result{url: "https://" + address.String()}:
				case <-probeCtx.Done():
				}
			}
		}()
	}
	for range addresses {
		select {
		case value := <-results:
			if value.url != "" {
				return value.url
			}
		case <-probeCtx.Done():
			return ""
		}
	}
	return ""
}

var dialControlPlane = (&net.Dialer{Timeout: 3 * time.Second}).DialContext

func verifyLoopback(ctx context.Context, server *tsnet.Server, deviceURL, expectedInstance string) string {
	client := server.HTTPClient()
	client.Timeout = 8 * time.Second
	probeURL := strings.TrimSuffix(deviceURL, "/") + "/api/auth"
	for attempt := 0; attempt < 8; attempt++ {
		request, err := http.NewRequestWithContext(ctx, http.MethodGet, probeURL, nil)
		if err == nil {
			response, requestErr := client.Do(request)
			if requestErr == nil {
				var value struct {
					InstanceID string `json:"instanceId"`
				}
				decodeErr := json.NewDecoder(io.LimitReader(response.Body, 64<<10)).Decode(&value)
				response.Body.Close()
				if decodeErr == nil && response.StatusCode == http.StatusOK &&
					(expectedInstance == "" || value.InstanceID == expectedInstance) {
					return value.InstanceID
				}
			}
		}
		timer := time.NewTimer(time.Duration(attempt+1) * 500 * time.Millisecond)
		select {
		case <-ctx.Done():
			timer.Stop()
			return ""
		case <-timer.C:
		}
	}
	return ""
}

func readLaunch(stream io.Reader) (launchConfig, error) {
	var value launchConfig
	line, err := bufio.NewReaderSize(io.LimitReader(stream, 64<<10), 64<<10).ReadBytes('\n')
	if err != nil && !errors.Is(err, io.EOF) {
		return value, err
	}
	if len(strings.TrimSpace(string(line))) == 0 {
		return value, errors.New("missing launch record")
	}
	if err := json.Unmarshal(line, &value); err != nil {
		return value, err
	}
	if len(value.AuthKey) > 16384 || strings.ContainsAny(value.AuthKey, "\x00\r\n") {
		return value, errors.New("invalid auth key")
	}
	return value, nil
}

func validateFlags(stateDir, hostname, mode string, port int, upstream, expectedInstance string) error {
	if stateDir == "" {
		return errors.New("state directory is required")
	}
	if len(hostname) > 63 || !regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9-]{0,62}$`).MatchString(hostname) {
		return errors.New("invalid hostname")
	}
	if mode != "serve" && mode != "funnel" {
		return errors.New("mode must be serve or funnel")
	}
	if port != 443 && port != 8443 && port != 10000 {
		return errors.New("unsupported HTTPS port")
	}
	parsed, err := url.Parse(upstream)
	if err != nil || parsed.Scheme != "http" || parsed.Hostname() != "127.0.0.1" ||
		parsed.User != nil || parsed.Path != "" || parsed.RawQuery != "" || parsed.Fragment != "" {
		return errors.New("upstream must be a loopback HTTP origin")
	}
	if parsed.Port() == "" {
		return errors.New("upstream port is required")
	}
	if !regexp.MustCompile(`^[A-Fa-f0-9]{32}$`).MatchString(expectedInstance) {
		return errors.New("gateway instance id is required")
	}
	return nil
}

func safeAuthorizationURL(value string) bool {
	parsed, err := url.Parse(value)
	return err == nil && parsed.Scheme == "https" && parsed.Hostname() == "login.tailscale.com" &&
		(parsed.Port() == "" || parsed.Port() == "443") && parsed.User == nil
}

func errorCode(err error) string {
	text := strings.ToLower(err.Error())
	switch {
	case strings.Contains(text, "startup timed out"):
		return "network_timeout"
	case strings.Contains(text, "invalid auth key") ||
		(strings.Contains(text, "auth key") && strings.Contains(text, "reject")):
		return "auth_key_rejected"
	case strings.Contains(text, "verify gateway instance"):
		return "verification_failed"
	case strings.Contains(text, "funnel"):
		return "funnel_unavailable"
	case strings.Contains(text, "https") || strings.Contains(text, "cert"):
		return "https_unavailable"
	case strings.Contains(text, "auth") || strings.Contains(text, "login") || strings.Contains(text, "machine"):
		return "authentication_failed"
	case strings.Contains(text, "context canceled"):
		return "stopped"
	case strings.Contains(text, "listen"):
		return "listener_failed"
	default:
		return "tailscale_failed"
	}
}
