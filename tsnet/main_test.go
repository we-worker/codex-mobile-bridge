package main

import (
	"errors"
	"strings"
	"testing"
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
		"verify gateway instance": "verification_failed",
		"funnel is unavailable":   "funnel_unavailable",
		"HTTPS certificate":       "https_unavailable",
		"authentication required": "authentication_failed",
		"listen tcp":              "listener_failed",
		"other failure":           "tailscale_failed",
	} {
		if got := errorCode(errors.New(message)); got != want {
			t.Fatalf("errorCode(%q) = %q, want %q", message, got, want)
		}
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
