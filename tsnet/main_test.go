package main

import (
	"context"
	"errors"
	"net"
	"net/netip"
	"net/url"
	"strings"
	"testing"
	"time"
)

func TestReadLaunch(t *testing.T) {
	value, err := readLaunch(strings.NewReader(`{"authKey":"tskey-auth-fixture"}` + "\n"))
	if err != nil {
		t.Fatal(err)
	}
	if value.AuthKey != "tskey-auth-fixture" {
		t.Fatalf("unexpected auth key: %q", value.AuthKey)
	}

	for name, input := range map[string]string{
		"missing":     "",
		"malformed":   "{",
		"newline":     "{\"authKey\":\"line\\nbreak\"}\n",
		"nul":         "{\"authKey\":\"line\\u0000break\"}\n",
		"unknownType": "{\"authKey\":42}\n",
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := readLaunch(strings.NewReader(input)); err == nil {
				t.Fatal("expected invalid launch to fail")
			}
		})
	}
}

func TestValidateFlags(t *testing.T) {
	const instance = "0123456789abcdef0123456789abcdef"
	if err := validateFlags(`C:\private\tsnet`, "codex-mobile-bridge", "serve", 443,
		"http://127.0.0.1:18787", instance); err != nil {
		t.Fatal(err)
	}

	for name, test := range map[string]struct {
		stateDir, hostname, mode string
		port                     int
		upstream, instance       string
	}{
		"empty state":  {"", "bridge", "serve", 443, "http://127.0.0.1:18787", instance},
		"bad hostname": {"/state", "-bridge", "serve", 443, "http://127.0.0.1:18787", instance},
		"bad mode":     {"/state", "bridge", "proxy", 443, "http://127.0.0.1:18787", instance},
		"bad port":     {"/state", "bridge", "serve", 8444, "http://127.0.0.1:18787", instance},
		"remote upstream": {"/state", "bridge", "serve", 443,
			"http://example.test:18787", instance},
		"upstream path": {"/state", "bridge", "serve", 443,
			"http://127.0.0.1:18787/path", instance},
		"missing instance": {"/state", "bridge", "serve", 443,
			"http://127.0.0.1:18787", ""},
	} {
		t.Run(name, func(t *testing.T) {
			if err := validateFlags(test.stateDir, test.hostname, test.mode, test.port,
				test.upstream, test.instance); err == nil {
				t.Fatal("expected invalid flags to fail")
			}
		})
	}
}

func TestSafeAuthorizationURL(t *testing.T) {
	if !safeAuthorizationURL("https://login.tailscale.com/f/funnel?node=n123") {
		t.Fatal("expected official authorization URL")
	}
	for _, value := range []string{
		"http://login.tailscale.com/a",
		"https://login.tailscale.com.evil.test/a",
		"https://user:pass@login.tailscale.com/a",
		"https://login.tailscale.com:8443/a",
		"javascript:alert(1)",
	} {
		if safeAuthorizationURL(value) {
			t.Fatalf("accepted unsafe URL %q", value)
		}
	}
}

func TestErrorCode(t *testing.T) {
	for message, want := range map[string]string{
		"startup timed out":                         "network_timeout",
		"invalid auth key provided":                 "auth_key_rejected",
		"verify gateway instance":                   "verification_failed",
		"funnel public endpoint was not published":  "funnel_publishing",
		"funnel public endpoint became unavailable": "funnel_publishing",
		"funnel is unavailable":                     "funnel_unavailable",
		"HTTPS certificate":                         "https_unavailable",
		"authentication required":                   "authentication_failed",
		"listen tcp":                                "listener_failed",
		"other failure":                             "tailscale_failed",
	} {
		if got := errorCode(errors.New(message)); got != want {
			t.Fatalf("errorCode(%q) = %q, want %q", message, got, want)
		}
	}
}

func TestFirstReachableControlURL(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	addresses := []netip.Addr{
		netip.MustParseAddr("10.0.0.1"),
		netip.MustParseAddr("10.0.0.2"),
	}
	dial := func(_ context.Context, _ string, address string) (net.Conn, error) {
		if !strings.HasPrefix(address, "10.0.0.2:") {
			return nil, errors.New("unreachable")
		}
		client, server := net.Pipe()
		_ = server.Close()
		return client, nil
	}
	if got, want := firstReachableControlURL(ctx, addresses, dial),
		"https://10.0.0.2"; got != want {
		t.Fatalf("firstReachableControlURL = %q, want %q", got, want)
	}
}

func TestChooseControlURLRespectsExplicitControlServer(t *testing.T) {
	t.Setenv("TS_CONTROL_URL", "https://control.example.test")
	if got := chooseControlURL(context.Background()); got != "" {
		t.Fatalf("chooseControlURL overrode explicit server with %q", got)
	}
}

func TestTargetPort(t *testing.T) {
	for authority, want := range map[string]string{
		"bridge.example.ts.net":      "443",
		"bridge.example.ts.net:8443": "8443",
	} {
		if got := targetPort(authority); got != want {
			t.Fatalf("targetPort(%q) = %q, want %q", authority, got, want)
		}
	}
}

func TestParseDoHAddresses(t *testing.T) {
	addresses, err := parseDoHAddresses(strings.NewReader(`{
		"Status": 0,
		"Answer": [
			{"name":"bridge.example.ts.net","type":5,"data":"edge.example."},
			{"name":"bridge.example.ts.net","type":1,"data":"203.0.113.10"},
			{"name":"bridge.example.ts.net","type":28,"data":"2001:db8::10"},
			{"name":"bridge.example.ts.net","type":1,"data":"203.0.113.10"},
			{"name":"bridge.example.ts.net","type":1,"data":"100.64.0.2"},
			{"name":"bridge.example.ts.net","type":1,"data":"192.168.1.2"},
			{"name":"bridge.example.ts.net","type":1,"data":"not-an-address"}
		]
	}`))
	if err != nil {
		t.Fatal(err)
	}
	if len(addresses) != 2 || addresses[0].String() != "203.0.113.10" ||
		addresses[1].String() != "2001:db8::10" {
		t.Fatalf("unexpected addresses: %v", addresses)
	}
}

func TestWaitForPublicGatewayUsesIndependentDNSAndCurrentInstance(t *testing.T) {
	oldLookup, oldProbe := resolvePublicAddresses, probePublicGateway
	oldWindow, oldInterval := publicPublishWindow, publicProbeInterval
	defer func() {
		resolvePublicAddresses, probePublicGateway = oldLookup, oldProbe
		publicPublishWindow, publicProbeInterval = oldWindow, oldInterval
	}()
	publicPublishWindow = 100 * time.Millisecond
	publicProbeInterval = 5 * time.Millisecond
	instance := "0123456789abcdef0123456789abcdef"
	lookupHost := ""
	resolvePublicAddresses = func(_ context.Context, host string) ([]netip.Addr, error) {
		lookupHost = host
		return []netip.Addr{netip.MustParseAddr("203.0.113.10")}, nil
	}
	probePublicGateway = func(_ context.Context, endpoint *url.URL, addresses []netip.Addr, expected string) (string, error) {
		if endpoint.Hostname() != "bridge.example.ts.net" || len(addresses) != 1 ||
			expected != instance {
			t.Fatal("public probe received the wrong endpoint or identity")
		}
		return instance, nil
	}
	got, err := waitForPublicGateway(context.Background(),
		"https://bridge.example.ts.net", instance, func() {}, make(chan error))
	if err != nil {
		t.Fatal(err)
	}
	if got != instance || lookupHost != "bridge.example.ts.net" {
		t.Fatalf("unexpected public verification: got=%q host=%q", got, lookupHost)
	}
}

func TestWaitForPublicGatewayStopsAfterPublishWindow(t *testing.T) {
	oldLookup, oldProbe := resolvePublicAddresses, probePublicGateway
	oldWindow, oldInterval := publicPublishWindow, publicProbeInterval
	defer func() {
		resolvePublicAddresses, probePublicGateway = oldLookup, oldProbe
		publicPublishWindow, publicProbeInterval = oldWindow, oldInterval
	}()
	publicPublishWindow = 25 * time.Millisecond
	publicProbeInterval = 5 * time.Millisecond
	resolvePublicAddresses = func(context.Context, string) ([]netip.Addr, error) {
		return nil, nil
	}
	probePublicGateway = func(context.Context, *url.URL, []netip.Addr, string) (string, error) {
		t.Fatal("probe must not run without a public DNS address")
		return "", nil
	}
	notifications := 0
	_, err := waitForPublicGateway(context.Background(),
		"https://bridge.example.ts.net", "0123456789abcdef0123456789abcdef",
		func() { notifications++ }, make(chan error))
	if !errors.Is(err, errFunnelPublishTimeout) {
		t.Fatalf("expected publish timeout, got %v", err)
	}
	if notifications == 0 {
		t.Fatal("expected an intermediate publishing status")
	}
}

func TestWaitForFunnelHealthRechecksAndDetectsPublicFailure(t *testing.T) {
	oldLookup, oldProbe := resolvePublicAddresses, probePublicGateway
	oldInterval, oldRetry, oldFailures := funnelHealthInterval, funnelHealthRetry, funnelHealthFailures
	defer func() {
		resolvePublicAddresses, probePublicGateway = oldLookup, oldProbe
		funnelHealthInterval, funnelHealthRetry, funnelHealthFailures = oldInterval, oldRetry, oldFailures
	}()
	funnelHealthInterval = time.Millisecond
	funnelHealthRetry = time.Millisecond
	funnelHealthFailures = 2
	instance := "0123456789abcdef0123456789abcdef"
	resolvePublicAddresses = func(context.Context, string) ([]netip.Addr, error) {
		return []netip.Addr{netip.MustParseAddr("203.0.113.10")}, nil
	}
	probes := 0
	probePublicGateway = func(context.Context, *url.URL, []netip.Addr, string) (string, error) {
		probes++
		if probes == 1 {
			return instance, nil
		}
		return "", errors.New("synthetic public outage")
	}
	err := waitForFunnelHealth(context.Background(),
		"https://bridge.example.ts.net", instance, make(chan error))
	if !errors.Is(err, errFunnelHealthLost) {
		t.Fatalf("expected health loss, got %v", err)
	}
	if probes != 3 {
		t.Fatalf("public probe count = %d, want 3", probes)
	}
}
