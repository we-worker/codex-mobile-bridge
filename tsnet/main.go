// Command codex-tsnet owns one userspace Tailscale node for the desktop bridge.
package main

import (
	"bufio"
	"context"
	"crypto/tls"
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

	"tailscale.com/ipn"
	"tailscale.com/tailcfg/nodecap"
	"tailscale.com/tsnet"
)

const (
	version               = "1.0.2"
	controlPlaneHost      = "controlplane.tailscale.com"
	controlProbeTimeout   = 4 * time.Second
	authKeyStartupTimeout = 75 * time.Second
)

var (
	publicPublishWindow   = 90 * time.Second
	publicProbeInterval   = 3 * time.Second
	funnelReregisterDelay = 10 * time.Second
	funnelPublishAttempts = 3
	funnelHealthInterval  = 45 * time.Second
	funnelHealthRetry     = 5 * time.Second
	funnelHealthFailures  = 2
	tailnetAddressRange   = netip.MustParsePrefix("100.64.0.0/10")
)

var authURLPattern = regexp.MustCompile(`https://login\.tailscale\.com/[^\s<>"']+`)

type launchConfig struct {
	AuthKey string `json:"authKey"`
}

type statusRecord struct {
	State      string            `json:"state"`
	Code       string            `json:"code,omitempty"`
	AuthURL    string            `json:"authUrl,omitempty"`
	Mode       string            `json:"mode,omitempty"`
	URL        string            `json:"url,omitempty"`
	URLs       []string          `json:"urls,omitempty"`
	TailnetURL string            `json:"tailnetUrl,omitempty"`
	TailnetIPs []string          `json:"tailnetIps,omitempty"`
	NodeID     string            `json:"nodeId,omitempty"`
	InstanceID string            `json:"instanceId,omitempty"`
	Version    string            `json:"version,omitempty"`
	Message    string            `json:"message,omitempty"`
	Diagnostic *statusDiagnostic `json:"diagnostic,omitempty"`
}

type statusDiagnostic struct {
	BackendState     string `json:"backendState,omitempty"`
	HealthCount      int    `json:"healthCount"`
	OnlinePeers      int    `json:"onlinePeers"`
	FunnelCapability bool   `json:"funnelCapability"`
	HTTPSCapability  bool   `json:"httpsCapability"`
	FunnelPortsCap   bool   `json:"funnelPortsCapability"`
	FunnelRegistered bool   `json:"funnelRegistered"`
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
	var port, httpPort int
	flag.StringVar(&stateDir, "state-dir", "", "private directory for the embedded node state")
	flag.StringVar(&hostname, "hostname", "codex-mobile-bridge", "Tailscale device hostname")
	flag.StringVar(&mode, "mode", "serve", "serve or funnel")
	flag.IntVar(&port, "port", 443, "HTTPS listener port")
	flag.IntVar(&httpPort, "http-port", 8787, "Tailnet-only HTTP listener port")
	flag.StringVar(&upstream, "upstream", "", "loopback HTTP upstream")
	flag.StringVar(&expectedInstance, "instance-id", "", "gateway instance expected behind the listener")
	flag.Parse()

	status := &statusWriter{output: os.Stdout}
	if err := validateFlags(stateDir, hostname, mode, port, httpPort, upstream, expectedInstance); err != nil {
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
	if err := run(ctx, status, launch, stateDir, hostname, mode, port, httpPort, upstream, expectedInstance); err != nil {
		status.write(statusRecord{State: "failed", Code: errorCode(err), Version: version})
	}
}

func run(ctx context.Context, output *statusWriter, launch launchConfig, stateDir, hostname, mode string, port, httpPort int, upstream, expectedInstance string) error {
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
	if status.Self == nil {
		return errors.New("tailnet did not provide this device")
	}
	if len(status.CertDomains) == 0 {
		return errors.New("HTTPS is not enabled for this tailnet")
	}
	nodeID := string(status.Self.ID)
	if nodeID == "" {
		return errors.New("tailnet did not provide a stable device ID")
	}
	deviceURL, tailnetURL, tailnetIP, urls, err := resolveEndpoints(
		status.Self.DNSName, port, httpPort, status.Self.TailscaleIPs, mode)
	if err != nil {
		return err
	}
	// The gateway must allow this exact origin before the loopback identity
	// probe below. This is a provisional authorization for the current child
	// process; the "listening" event is only emitted after the gateway instance
	// and URL have both been verified.
	output.write(statusRecord{
		State:      "resolved",
		Mode:       mode,
		URL:        deviceURL,
		URLs:       urls,
		TailnetURL: tailnetURL,
		TailnetIPs: optionalValues(tailnetIP),
		NodeID:     nodeID,
		InstanceID: expectedInstance,
		Version:    version,
	})

	if mode == "funnel" {
		return runFunnel(ctx, output, server, deviceURL, nodeID, upstream, port, expectedInstance)
	}
	return runServe(ctx, output, server, deviceURL, tailnetURL, tailnetIP, nodeID, upstream, port, httpPort, expectedInstance)
}

func runServe(ctx context.Context, output *statusWriter, server *tsnet.Server, deviceURL, tailnetURL, tailnetIP, nodeID, upstream string, port, httpPort int, expectedInstance string) error {
	listener, httpServer, secureErrors, err := openListener(server, upstream, port, false, "https")
	if err != nil {
		return err
	}
	defer closeListener(httpServer, listener)
	tailnetListener, tailnetHTTPServer, tailnetErrors, err := openTailnetHTTPListener(server, upstream, httpPort)
	if err != nil {
		return err
	}
	defer closeListener(tailnetHTTPServer, tailnetListener)

	instanceID, diagnostic, err := verifyListener(ctx, output, server, deviceURL, nodeID, port, expectedInstance)
	if err != nil {
		return err
	}
	if got := verifyLoopback(ctx, server, tailnetURL, expectedInstance); got != expectedInstance {
		return errors.New("verify tailnet HTTP gateway instance")
	}
	output.write(statusRecord{
		State:      "connected",
		Mode:       "serve",
		URL:        deviceURL,
		URLs:       []string{deviceURL, tailnetURL},
		TailnetURL: tailnetURL,
		TailnetIPs: []string{tailnetIP},
		NodeID:     nodeID,
		InstanceID: instanceID,
		Version:    version,
		Message:    "Tailnet HTTPS、私有 HTTP 入口和当前网关身份均已验证。",
		Diagnostic: diagnostic,
	})
	return waitForServerPair(ctx, secureErrors, tailnetErrors)
}

func runFunnel(ctx context.Context, output *statusWriter, server *tsnet.Server, deviceURL, nodeID, upstream string, port int, expectedInstance string) error {
	attempts := 0
	for {
		attempts++
		err := runFunnelRound(ctx, output, server, deviceURL, nodeID, upstream, port, expectedInstance)
		if ctx.Err() != nil {
			return nil
		}
		if err == nil {
			return nil
		}
		if !errors.Is(err, errFunnelPublishTimeout) && !errors.Is(err, errFunnelHealthLost) {
			return err
		}
		if attempts >= funnelPublishAttempts {
			return err
		}
		message := "Funnel 已在 Tailnet 内登记，但公网入口尚未发布；正在自动重新登记。"
		if errors.Is(err, errFunnelHealthLost) {
			message = "公网入口运行中失效；正在撤回临时来源并重新登记 Funnel。"
		}
		output.write(statusRecord{
			State:      "retrying",
			Code:       "funnel_publishing",
			Mode:       "funnel",
			URL:        deviceURL,
			URLs:       []string{deviceURL},
			NodeID:     nodeID,
			InstanceID: expectedInstance,
			Version:    version,
			Message:    message,
		})
		retryDelay := funnelReregisterDelay
		for retryAttempt := 1; retryAttempt < attempts && retryDelay < time.Minute; retryAttempt++ {
			retryDelay *= 2
		}
		timer := time.NewTimer(retryDelay)
		select {
		case <-ctx.Done():
			timer.Stop()
			return nil
		case <-timer.C:
		}
	}
}

var errFunnelPublishTimeout = errors.New("funnel public endpoint was not published")
var errFunnelHealthLost = errors.New("funnel public endpoint became unavailable")

func runFunnelRound(ctx context.Context, output *statusWriter, server *tsnet.Server, deviceURL, nodeID, upstream string, port int, expectedInstance string) error {
	listener, httpServer, serveErrors, err := openListener(server, upstream, port, true, "https")
	if err != nil {
		return err
	}
	defer closeListener(httpServer, listener)

	instanceID, diagnostic, err := verifyListener(ctx, output, server, deviceURL, nodeID, port, expectedInstance)
	if err != nil {
		return err
	}
	output.write(statusRecord{
		State:      "listening",
		Mode:       "funnel",
		URL:        deviceURL,
		URLs:       []string{deviceURL},
		NodeID:     nodeID,
		InstanceID: instanceID,
		Version:    version,
		Message:    "Tailnet 内入口已就绪，正在验证公网 Funnel、TLS 与当前网关身份…",
		Diagnostic: diagnostic,
	})

	verified, err := waitForPublicGateway(ctx, deviceURL, expectedInstance, func() {
		output.write(statusRecord{
			State:      "publishing",
			Mode:       "funnel",
			URL:        deviceURL,
			URLs:       []string{deviceURL},
			NodeID:     nodeID,
			InstanceID: instanceID,
			Version:    version,
			Message:    "Funnel 已在本机登记，正在等待公网 DNS 与 HTTPS 生效…",
			Diagnostic: diagnostic,
		})
	}, serveErrors)
	if err != nil || verified != expectedInstance {
		if err != nil && !errors.Is(err, errFunnelPublishTimeout) {
			return err
		}
		return errFunnelPublishTimeout
	}

	output.write(statusRecord{
		State:      "connected",
		Mode:       "funnel",
		URL:        deviceURL,
		URLs:       []string{deviceURL},
		NodeID:     nodeID,
		InstanceID: verified,
		Version:    version,
		Message:    "公网 Funnel、TLS 和当前网关身份均已验证。",
		Diagnostic: diagnostic,
	})
	return waitForFunnelHealth(ctx, deviceURL, verified, serveErrors)
}

func openListener(server *tsnet.Server, upstream string, port int, funnel bool, forwardedProto string) (net.Listener, *http.Server, <-chan error, error) {
	var (
		listener net.Listener
		err      error
	)
	if funnel {
		listener, err = server.ListenFunnel("tcp", ":"+strconv.Itoa(port))
	} else {
		listener, err = server.ListenTLS("tcp", ":"+strconv.Itoa(port))
	}
	if err != nil {
		return nil, nil, nil, fmt.Errorf("listen on tailnet: %w", err)
	}
	return serveProxyListener(listener, upstream, forwardedProto)
}

func openTailnetHTTPListener(server *tsnet.Server, upstream string, port int) (net.Listener, *http.Server, <-chan error, error) {
	listener, err := server.Listen("tcp", ":"+strconv.Itoa(port))
	if err != nil {
		return nil, nil, nil, fmt.Errorf("listen on private tailnet HTTP: %w", err)
	}
	return serveProxyListener(listener, upstream, "http")
}

func serveProxyListener(listener net.Listener, upstream, forwardedProto string) (net.Listener, *http.Server, <-chan error, error) {
	target, _ := url.Parse(upstream)
	httpServer := &http.Server{
		Handler:           newProxy(target, forwardedProto),
		ReadHeaderTimeout: 15 * time.Second,
		IdleTimeout:       2 * time.Minute,
		MaxHeaderBytes:    1 << 20,
	}
	serveErrors := make(chan error, 1)
	go func() {
		serveErrors <- httpServer.Serve(listener)
	}()
	return listener, httpServer, serveErrors, nil
}

func closeListener(httpServer *http.Server, listener net.Listener) {
	if httpServer != nil {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		_ = httpServer.Shutdown(shutdownCtx)
		cancel()
	}
	if listener != nil {
		_ = listener.Close()
	}
}

func waitForServer(ctx context.Context, serveErrors <-chan error) error {
	select {
	case <-ctx.Done():
		return nil
	case err := <-serveErrors:
		if errors.Is(err, http.ErrServerClosed) || errors.Is(err, net.ErrClosed) {
			return nil
		}
		return fmt.Errorf("serve tailnet listener: %w", err)
	}
}

func waitForServerPair(ctx context.Context, secureErrors, privateErrors <-chan error) error {
	select {
	case <-ctx.Done():
		return nil
	case err := <-secureErrors:
		if errors.Is(err, http.ErrServerClosed) || errors.Is(err, net.ErrClosed) {
			return nil
		}
		return fmt.Errorf("serve tailnet HTTPS listener: %w", err)
	case err := <-privateErrors:
		if errors.Is(err, http.ErrServerClosed) || errors.Is(err, net.ErrClosed) {
			return nil
		}
		return fmt.Errorf("serve private tailnet HTTP listener: %w", err)
	}
}

func verifyListener(ctx context.Context, output *statusWriter, server *tsnet.Server, deviceURL, nodeID string, port int, expectedInstance string) (string, *statusDiagnostic, error) {
	output.write(statusRecord{
		State:   "verifying",
		URL:     deviceURL,
		NodeID:  nodeID,
		Version: version,
		Message: "Tailscale 地址已就绪，正在校验它连接到当前网关…",
	})
	instanceID := verifyLoopback(ctx, server, deviceURL, expectedInstance)
	if instanceID != expectedInstance {
		return "", nil, errors.New("verify gateway instance")
	}
	diagnostic := collectDiagnostic(ctx, server, deviceURL, port)
	return instanceID, diagnostic, nil
}

type publicDNSLookup func(context.Context, string) ([]netip.Addr, error)
type publicGatewayProbe func(context.Context, *url.URL, []netip.Addr, string) (string, error)

var resolvePublicAddresses publicDNSLookup = lookupPublicAddresses
var probePublicGateway publicGatewayProbe = probePublicGatewayHTTP

func waitForPublicGateway(ctx context.Context, deviceURL, expectedInstance string, notify func(), serveErrors <-chan error) (string, error) {
	parsed, err := url.Parse(deviceURL)
	if err != nil || parsed.Scheme != "https" || parsed.Hostname() == "" {
		return "", errors.New("invalid public gateway URL")
	}
	publishCtx, cancelPublish := context.WithTimeout(ctx, publicPublishWindow)
	defer cancelPublish()
	for {
		select {
		case err := <-serveErrors:
			if errors.Is(err, http.ErrServerClosed) || errors.Is(err, net.ErrClosed) {
				return "", errors.New("funnel listener closed")
			}
			return "", fmt.Errorf("serve tailnet listener: %w", err)
		default:
		}

		addresses, lookupErr := resolvePublicAddresses(publishCtx, parsed.Hostname())
		if lookupErr == nil && len(addresses) > 0 {
			probeCtx, cancel := context.WithTimeout(publishCtx, 20*time.Second)
			instanceID, probeErr := probePublicGateway(probeCtx, parsed, addresses, expectedInstance)
			cancel()
			if probeErr == nil && instanceID == expectedInstance {
				return instanceID, nil
			}
		}
		notify()

		timer := time.NewTimer(publicProbeInterval)
		select {
		case <-ctx.Done():
			timer.Stop()
			return "", ctx.Err()
		case <-publishCtx.Done():
			timer.Stop()
			return "", errFunnelPublishTimeout
		case err := <-serveErrors:
			timer.Stop()
			if errors.Is(err, http.ErrServerClosed) || errors.Is(err, net.ErrClosed) {
				return "", errors.New("funnel listener closed")
			}
			return "", fmt.Errorf("serve tailnet listener: %w", err)
		case <-timer.C:
		}
	}
}

func waitForFunnelHealth(ctx context.Context, deviceURL, instanceID string, serveErrors <-chan error) error {
	parsed, err := url.Parse(deviceURL)
	if err != nil || parsed.Scheme != "https" || parsed.Hostname() == "" {
		return errors.New("invalid public gateway URL")
	}
	failures := 0
	timer := time.NewTimer(funnelHealthInterval)
	defer timer.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil
		case err := <-serveErrors:
			if errors.Is(err, http.ErrServerClosed) || errors.Is(err, net.ErrClosed) {
				return nil
			}
			return fmt.Errorf("serve tailnet listener: %w", err)
		case <-timer.C:
			probeCtx, cancel := context.WithTimeout(ctx, 20*time.Second)
			addresses, probeErr := resolvePublicAddresses(probeCtx, parsed.Hostname())
			if probeErr == nil && len(addresses) == 0 {
				probeErr = errors.New("public DNS returned no public address")
			}
			if probeErr == nil {
				var got string
				got, probeErr = probePublicGateway(probeCtx, parsed, addresses, instanceID)
				if probeErr == nil && got != instanceID {
					probeErr = errors.New("public gateway instance mismatch")
				}
			}
			cancel()
			if ctx.Err() != nil {
				return nil
			}
			if probeErr == nil {
				failures = 0
				timer.Reset(funnelHealthInterval)
				continue
			}
			failures++
			if failures < funnelHealthFailures {
				timer.Reset(funnelHealthRetry)
				continue
			}
			return fmt.Errorf("%w: %v", errFunnelHealthLost, probeErr)
		}
	}
}

type dohAnswer struct {
	Name string `json:"name"`
	Type int    `json:"type"`
	Data string `json:"data"`
}

type dohResponse struct {
	Status int         `json:"Status"`
	Answer []dohAnswer `json:"Answer"`
}

var dohClient = &http.Client{Timeout: 6 * time.Second}

func lookupPublicAddresses(ctx context.Context, hostname string) ([]netip.Addr, error) {
	endpoints := []string{
		"https://223.5.5.5/resolve",
		"https://1.12.12.12/resolve",
		"https://dns.alidns.com/resolve",
		"https://doh.pub/dns-query",
		"https://cloudflare-dns.com/dns-query",
		"https://dns.google/resolve",
	}
	var (
		lastErr   error
		completed bool
		successes int
	)
	for _, endpoint := range endpoints {
		var found []netip.Addr
		endpointCompleted := true
		for _, recordType := range []string{"A", "AAAA"} {
			query, _ := url.Parse(endpoint)
			values := query.Query()
			values.Set("name", hostname)
			values.Set("type", recordType)
			query.RawQuery = values.Encode()
			request, err := http.NewRequestWithContext(ctx, http.MethodGet, query.String(), nil)
			if err != nil {
				lastErr = err
				endpointCompleted = false
				break
			}
			request.Header.Set("Accept", "application/dns-json")
			response, err := dohClient.Do(request)
			if err != nil {
				lastErr = err
				endpointCompleted = false
				break
			}
			addresses, parseErr := parseDoHAddresses(io.LimitReader(response.Body, 256<<10))
			response.Body.Close()
			if parseErr != nil || response.StatusCode != http.StatusOK {
				lastErr = errors.New("public DNS resolver returned an invalid response")
				endpointCompleted = false
				break
			}
			found = append(found, addresses...)
		}
		if endpointCompleted {
			completed = true
			successes++
		}
		unique := uniqueAddresses(found)
		if len(unique) > 0 {
			return unique, nil
		}
		// Two independent responses are enough to treat NODATA as negative.
		// This avoids waiting on blocked resolvers after a usable regional
		// pair has already answered.
		if successes >= 2 {
			break
		}
	}
	if completed {
		return nil, nil
	}
	if lastErr == nil {
		lastErr = errors.New("public DNS lookup failed")
	}
	return nil, lastErr
}

func parseDoHAddresses(reader io.Reader) ([]netip.Addr, error) {
	var response dohResponse
	if err := json.NewDecoder(reader).Decode(&response); err != nil {
		return nil, err
	}
	if response.Status != 0 && response.Status != 3 {
		return nil, errors.New("public DNS resolver error")
	}
	var result []netip.Addr
	for _, answer := range response.Answer {
		if answer.Type != 1 && answer.Type != 28 {
			continue
		}
		address, err := netip.ParseAddr(answer.Data)
		if err == nil && publicAddress(address.Unmap()) {
			result = append(result, address.Unmap())
		}
	}
	return uniqueAddresses(result), nil
}

func publicAddress(address netip.Addr) bool {
	return address.IsValid() && address.IsGlobalUnicast() &&
		!address.IsPrivate() && !address.IsLoopback() && !address.IsLinkLocalUnicast() &&
		!address.IsMulticast() && !tailnetAddressRange.Contains(address)
}

func uniqueAddresses(values []netip.Addr) []netip.Addr {
	seen := make(map[netip.Addr]bool)
	result := make([]netip.Addr, 0, len(values))
	for _, value := range values {
		value = value.Unmap()
		if !value.IsValid() || seen[value] {
			continue
		}
		seen[value] = true
		result = append(result, value)
	}
	return result
}

func probePublicGatewayHTTP(ctx context.Context, deviceURL *url.URL, addresses []netip.Addr, expectedInstance string) (string, error) {
	hostname := deviceURL.Hostname()
	port := deviceURL.Port()
	if port == "" {
		port = "443"
	}
	dialer := &net.Dialer{Timeout: 4 * time.Second, KeepAlive: 30 * time.Second}
	transport := &http.Transport{
		Proxy: nil,
		DialContext: func(dialCtx context.Context, network, _ string) (net.Conn, error) {
			var lastErr error
			for _, address := range uniqueAddresses(addresses) {
				connection, err := dialer.DialContext(dialCtx, network, net.JoinHostPort(address.String(), port))
				if err == nil {
					return connection, nil
				}
				lastErr = err
			}
			if lastErr == nil {
				lastErr = errors.New("public DNS returned no usable addresses")
			}
			return nil, lastErr
		},
		TLSClientConfig: &tls.Config{
			ServerName: hostname,
			MinVersion: tls.VersionTLS12,
		},
		DisableKeepAlives:     true,
		ForceAttemptHTTP2:     true,
		TLSHandshakeTimeout:   6 * time.Second,
		ResponseHeaderTimeout: 8 * time.Second,
	}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: 15 * time.Second}
	probeURL := strings.TrimSuffix(deviceURL.String(), "/") + "/api/auth"
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, probeURL, nil)
	if err != nil {
		return "", err
	}
	response, err := client.Do(request)
	if err != nil {
		return "", err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return "", fmt.Errorf("public gateway returned HTTP %d", response.StatusCode)
	}
	var value struct {
		InstanceID string `json:"instanceId"`
	}
	if err := json.NewDecoder(io.LimitReader(response.Body, 64<<10)).Decode(&value); err != nil {
		return "", err
	}
	if value.InstanceID == "" || (expectedInstance != "" && value.InstanceID != expectedInstance) {
		return "", errors.New("public gateway instance mismatch")
	}
	return value.InstanceID, nil
}

func collectDiagnostic(ctx context.Context, server *tsnet.Server, deviceURL string, port int) *statusDiagnostic {
	diagnosticCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	value := &statusDiagnostic{}
	local, err := server.LocalClient()
	if err != nil {
		return value
	}
	status, err := local.Status(diagnosticCtx)
	if err == nil && status != nil {
		value.BackendState = status.BackendState
		value.HealthCount = len(status.Health)
		for _, peer := range status.Peer {
			if peer != nil && peer.Online {
				value.OnlinePeers++
			}
		}
		if status.Self != nil {
			value.FunnelCapability = status.Self.HasCap(nodecap.Funnel)
			value.HTTPSCapability = status.Self.HasCap(nodecap.HTTPS)
			for capability := range status.Self.CapMap {
				if strings.HasPrefix(string(capability), string(nodecap.FunnelPorts)) {
					value.FunnelPortsCap = true
					break
				}
			}
		}
	}
	config, err := local.GetServeConfig(diagnosticCtx)
	if err == nil && config != nil {
		hostname := deviceURL
		if parsed, parseErr := url.Parse(deviceURL); parseErr == nil {
			hostname = parsed.Hostname()
		}
		hostPort := ipn.HostPort(hostname + ":" + strconv.Itoa(port))
		value.FunnelRegistered = config.AllowFunnel[hostPort]
	}
	return value
}

func newProxy(target *url.URL, forwardedProto string) *httputil.ReverseProxy {
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
			// Origin pair. Preserve the exact tailnet authority.
			request.Out.Host = originalHost
			request.SetXForwarded()
			request.Out.Header.Set("X-Forwarded-Proto", forwardedProto)
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

func firstTailnetIPv4(addresses []netip.Addr) string {
	for _, address := range addresses {
		address = address.Unmap()
		if address.Is4() && tailnetAddressRange.Contains(address) {
			return address.String()
		}
	}
	return ""
}

func resolveEndpoints(dnsName string, port, httpPort int, addresses []netip.Addr, mode string) (string, string, string, []string, error) {
	dnsName = strings.TrimSuffix(dnsName, ".")
	if dnsName == "" {
		return "", "", "", nil, errors.New("tailnet did not provide a device DNS name")
	}
	deviceURL := "https://" + dnsName
	if port != 443 {
		deviceURL += ":" + strconv.Itoa(port)
	}
	if mode != "serve" {
		return deviceURL, "", "", []string{deviceURL}, nil
	}
	tailnetIP := firstTailnetIPv4(addresses)
	if tailnetIP == "" {
		return "", "", "", nil, errors.New("tailnet did not provide a private IPv4 address")
	}
	tailnetURL := "http://" + net.JoinHostPort(tailnetIP, strconv.Itoa(httpPort))
	return deviceURL, tailnetURL, tailnetIP, []string{deviceURL, tailnetURL}, nil
}

func optionalValues(value string) []string {
	if value == "" {
		return nil
	}
	return []string{value}
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

func validateFlags(stateDir, hostname, mode string, port, httpPort int, upstream, expectedInstance string) error {
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
	if httpPort != 8787 || httpPort == port {
		return errors.New("invalid private HTTP port")
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
	case strings.Contains(text, "funnel public endpoint"):
		return "funnel_publishing"
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
