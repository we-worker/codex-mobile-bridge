package mobiletsnet

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
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

func TestValidatePrivateHTTPTargetBoundaries(t *testing.T) {
	cases := []struct {
		input   string
		want    string
		wantErr bool
	}{
		{"http://100.64.0.0:8787/api/auth", "100.64.0.0:8787", false},
		{"http://100.127.255.255:8787/api/auth?x=1", "100.127.255.255:8787", false},
		{"http://100.63.255.255:8787/", "", true},
		{"http://100.128.0.0:8787/", "", true},
		{"http://8.8.8.8:8787/", "", true},
		{"http://100.64.0.1:8788/", "", true},
		{"https://100.64.0.1:8787/", "", true},
		{"http://user@100.64.0.1:8787/", "", true},
		{"http://100.64.0.1:8787/#fragment", "", true},
		{"http://bridge.example.ts.net:8787/", "", true},
	}
	for _, test := range cases {
		parsed, parseErr := url.Parse(test.input)
		if parseErr != nil {
			t.Fatalf("parse %q: %v", test.input, parseErr)
		}
		got, err := validatePrivateHTTPTarget(parsed)
		if (err != nil) != test.wantErr || got != test.want {
			t.Errorf("validatePrivateHTTPTarget(%q) = %q, %v; want %q, error=%v",
				test.input, got, err, test.want, test.wantErr)
		}
	}
}

func TestHTTPProxyAllowsOnlyPrivateTailnetPort(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	type observed struct {
		host, uri, proxyAuthorization string
	}
	seen := make(chan observed, 1)
	upstream := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		seen <- observed{
			host: request.Host, uri: request.URL.RequestURI(),
			proxyAuthorization: request.Header.Get("Proxy-Authorization"),
		}
		response.Header().Set("Content-Type", "text/plain")
		_, _ = io.WriteString(response, "private gateway")
	}))
	defer upstream.Close()
	dialed := make(chan string, 4)
	proxy, err := startConnectProxy(ctx, func(ctx context.Context, network, target string) (net.Conn, error) {
		dialed <- target
		return (&net.Dialer{}).DialContext(ctx, network, upstream.Listener.Addr().String())
	})
	if err != nil {
		t.Fatal(err)
	}
	defer proxy.close()
	proxyURL, _ := url.Parse("http://" + proxy.address())
	client := &http.Client{Transport: &http.Transport{Proxy: http.ProxyURL(proxyURL)}}

	request, _ := http.NewRequestWithContext(ctx, http.MethodGet,
		"http://100.64.0.10:8787/api/auth?x=1", nil)
	request.Header.Set("Proxy-Authorization", "Basic secret")
	response, err := client.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	body, _ := io.ReadAll(response.Body)
	if response.StatusCode != http.StatusOK || string(body) != "private gateway" {
		t.Fatalf("HTTP proxy response = %d %q", response.StatusCode, body)
	}
	select {
	case target := <-dialed:
		if target != "100.64.0.10:8787" {
			t.Fatalf("HTTP proxy dial target = %q", target)
		}
	case <-time.After(time.Second):
		t.Fatal("private HTTP upstream was not dialed")
	}
	select {
	case got := <-seen:
		if got.host != "100.64.0.10:8787" || got.uri != "/api/auth?x=1" ||
			got.proxyAuthorization != "" {
			t.Fatalf("unexpected upstream request: %+v", got)
		}
	case <-time.After(time.Second):
		t.Fatal("private HTTP request was not forwarded")
	}

	for _, target := range []string{
		"http://8.8.8.8:8787/",
		"http://100.64.0.10:80/",
	} {
		request, _ := http.NewRequestWithContext(ctx, http.MethodGet, target, nil)
		response, err := client.Do(request)
		if err != nil {
			t.Fatalf("rejected target %q returned transport error: %v", target, err)
		}
		_, _ = io.Copy(io.Discard, response.Body)
		response.Body.Close()
		if response.StatusCode != http.StatusForbidden {
			t.Fatalf("rejected target %q status = %d", target, response.StatusCode)
		}
	}
}

func TestHTTPProxyHandlesConcurrentAssetRequests(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	upstream := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		response.Header().Set("Content-Type", "text/javascript; charset=utf-8")
		_, _ = io.WriteString(response, request.URL.Path)
	}))
	defer upstream.Close()

	proxy, err := startConnectProxy(ctx, func(ctx context.Context, network, _ string) (net.Conn, error) {
		return (&net.Dialer{}).DialContext(ctx, network, upstream.Listener.Addr().String())
	})
	if err != nil {
		t.Fatal(err)
	}
	defer proxy.close()

	proxyURL, _ := url.Parse("http://" + proxy.address())
	client := &http.Client{Transport: &http.Transport{
		Proxy:               http.ProxyURL(proxyURL),
		MaxConnsPerHost:     4,
		MaxIdleConnsPerHost: 4,
	}}
	defer client.CloseIdleConnections()

	const requests = 20
	var wait sync.WaitGroup
	failures := make(chan error, requests)
	for index := 0; index < requests; index++ {
		index := index
		wait.Add(1)
		go func() {
			defer wait.Done()
			path := fmt.Sprintf("/asset-%02d.js", index)
			request, _ := http.NewRequestWithContext(ctx, http.MethodGet,
				"http://100.64.0.10:8787"+path, nil)
			response, err := client.Do(request)
			if err != nil {
				failures <- fmt.Errorf("%s request: %w", path, err)
				return
			}
			defer response.Body.Close()
			body, err := io.ReadAll(response.Body)
			if err != nil {
				failures <- fmt.Errorf("%s body: %w", path, err)
				return
			}
			if response.StatusCode != http.StatusOK || string(body) != path ||
				!strings.HasPrefix(response.Header.Get("Content-Type"), "text/javascript") {
				failures <- fmt.Errorf("%s response = %d %q %q", path, response.StatusCode,
					response.Header.Get("Content-Type"), body)
			}
		}()
	}
	wait.Wait()
	close(failures)
	for failure := range failures {
		t.Error(failure)
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

func TestMobileErrorRedactsKeyIdentifiers(t *testing.T) {
	err := errors.New("backend: invalid key: API key abcdef0123456789 not valid")
	if got := mobileErrorCode(err); got != "auth_key_invalid" {
		t.Fatalf("mobileErrorCode = %q", got)
	}
	detail := safeErrorDetail(err)
	if strings.Contains(detail, "abcdef0123456789") || !strings.Contains(detail, "[已隐藏 Tailscale 密钥]") {
		t.Fatalf("safeErrorDetail = %q", detail)
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

func TestPrepareRuntimeDirectoriesUsesAppPrivateStorage(t *testing.T) {
	root := t.TempDir()
	t.Setenv("TS_LOGS_DIR", "")
	t.Setenv("TMPDIR", "")
	if err := prepareRuntimeDirectories(root); err != nil {
		t.Fatal(err)
	}
	for env, name := range map[string]string{
		"TS_LOGS_DIR": "logs",
		"TMPDIR":      "tmp",
	} {
		want := filepath.Join(root, name)
		if got := os.Getenv(env); got != want {
			t.Fatalf("%s = %q, want %q", env, got, want)
		}
		info, err := os.Stat(want)
		if err != nil || !info.IsDir() {
			t.Fatalf("%s directory %q was not created: %v", env, want, err)
		}
	}
}
