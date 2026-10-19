package mobiletsnet

import (
	"bufio"
	"context"
	"io"
	"net"
	"net/http"
	"strings"
	"testing"
	"time"
)

func TestValidateTailnetTarget(t *testing.T) {
	cases := []struct {
		input   string
		want    string
		wantErr bool
	}{
		{"desk.ts.net:443", "desk.ts.net:443", false},
		{"DESK.ts.net:8443", "desk.ts.net:8443", false},
		{"desk.ts.net:10000", "desk.ts.net:10000", false},
		{"desk.ts.net", "", true},
		{"desk.ts.net:80", "", true},
		{"desk.ts.net:443@evil.example", "", true},
		{"[::1]:443", "", true},
		{"127.0.0.1:443", "", true},
		{"desk.ts.net.evil:443", "", true},
		{"evil.example:443", "", true},
	}
	for _, tc := range cases {
		got, err := validateTailnetTarget(tc.input)
		if (err != nil) != tc.wantErr || got != tc.want {
			t.Errorf("validateTailnetTarget(%q) = %q, %v; want %q, error=%v", tc.input, got, err, tc.want, tc.wantErr)
		}
	}
}

func TestConnectProxyAllowsTailnetAndRejectsOtherHosts(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	dialed := make(chan string, 1)
	proxy, err := startConnectProxy(ctx, func(_ context.Context, _ string, target string) (net.Conn, error) {
		dialed <- target
		client, server := net.Pipe()
		go func() {
			defer server.Close()
			_, _ = io.Copy(server, server)
		}()
		return client, nil
	})
	if err != nil {
		t.Fatal(err)
	}
	defer proxy.close()

	connection, err := net.DialTimeout("tcp", proxy.address(), time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer connection.Close()
	_, _ = io.WriteString(connection, "CONNECT desk.ts.net:443 HTTP/1.1\r\nHost: desk.ts.net:443\r\n\r\n")
	response, err := http.ReadResponse(bufio.NewReader(connection), &http.Request{Method: http.MethodConnect})
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != http.StatusOK {
		t.Fatalf("CONNECT status = %d", response.StatusCode)
	}
	select {
	case got := <-dialed:
		if got != "desk.ts.net:443" {
			t.Fatalf("dial target = %q", got)
		}
	case <-time.After(time.Second):
		t.Fatal("tailnet dialer was not called")
	}

	rejected, err := net.DialTimeout("tcp", proxy.address(), time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer rejected.Close()
	_, _ = io.WriteString(rejected, "CONNECT evil.example:443 HTTP/1.1\r\nHost: evil.example:443\r\n\r\n")
	rejectedResponse, err := http.ReadResponse(bufio.NewReader(rejected), &http.Request{Method: http.MethodConnect})
	if err != nil {
		t.Fatal(err)
	}
	if rejectedResponse.StatusCode != http.StatusForbidden {
		t.Fatalf("non-tailnet CONNECT status = %d", rejectedResponse.StatusCode)
	}

	spoofed, err := net.DialTimeout("tcp", proxy.address(), time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer spoofed.Close()
	_, _ = io.WriteString(spoofed, "CONNECT evil.example:443 HTTP/1.1\r\nHost: desk.ts.net:443\r\n\r\n")
	spoofedResponse, err := http.ReadResponse(bufio.NewReader(spoofed), &http.Request{Method: http.MethodConnect})
	if err != nil {
		t.Fatal(err)
	}
	if spoofedResponse.StatusCode != http.StatusForbidden {
		t.Fatalf("spoofed CONNECT status = %d", spoofedResponse.StatusCode)
	}
}

func TestAuthorizationURLBoundary(t *testing.T) {
	valid := "https://login.tailscale.com/a/0123456789"
	if got := safeAuthorizationURLFromLog("open " + valid + " to authorize"); got != valid {
		t.Fatalf("authorization URL = %q", got)
	}
	for _, value := range []string{
		"http://login.tailscale.com/a/123",
		"https://login.tailscale.com.evil/a/123",
		"https://user@login.tailscale.com/a/123",
		"https://login.tailscale.com:8443/a/123",
	} {
		if safeAuthorizationURL(value) {
			t.Fatalf("accepted unsafe URL %q", value)
		}
	}
}

func TestStopIsIdempotentInIdleState(t *testing.T) {
	mobile := NewMobile()
	mobile.Stop()
	mobile.Stop()
	if mobile.Status() != stateStopped {
		t.Fatalf("idle status = %q", mobile.Status())
	}
	if strings.Contains(mobile.AuthURL()+mobile.ProxyAddress()+mobile.ErrorCode(), "tskey-") {
		t.Fatal("status leaked an auth key")
	}
}
