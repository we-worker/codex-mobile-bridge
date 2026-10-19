package mobiletsnet

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/netip"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
)

type dialFunc func(context.Context, string, string) (net.Conn, error)

var tailnetHostPattern = regexp.MustCompile(`^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.ts\.net$`)
var tailnetAddressRange = netip.MustParsePrefix("100.64.0.0/10")

const privateHTTPPort = "8787"

type connectProxy struct {
	listener  net.Listener
	dial      dialFunc
	server    *http.Server
	transport *http.Transport

	mu       sync.Mutex
	closed   bool
	conns    map[net.Conn]struct{}
	stopOnce sync.Once
}

func startConnectProxy(parent context.Context, dial dialFunc) (*connectProxy, error) {
	if dial == nil {
		return nil, errors.New("tailnet dialer is required")
	}
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		return nil, fmt.Errorf("listen on loopback: %w", err)
	}
	proxy := &connectProxy{
		listener: listener,
		dial:     dial,
		conns:    make(map[net.Conn]struct{}),
	}
	proxy.transport = &http.Transport{
		Proxy:                 nil,
		DialContext:           dial,
		MaxIdleConns:          32,
		MaxIdleConnsPerHost:   8,
		IdleConnTimeout:       90 * time.Second,
		ResponseHeaderTimeout: 30 * time.Second,
	}
	proxy.server = &http.Server{
		Handler:           proxy,
		ReadHeaderTimeout: 15 * time.Second,
		IdleTimeout:       2 * time.Minute,
		MaxHeaderBytes:    1 << 20,
		ConnState:         proxy.connectionState,
	}
	go proxy.serve(parent)
	return proxy, nil
}

func (p *connectProxy) address() string {
	return p.listener.Addr().String()
}

func (p *connectProxy) port() int {
	return p.listener.Addr().(*net.TCPAddr).Port
}

func (p *connectProxy) close() {
	p.stopOnce.Do(func() {
		_ = p.listener.Close()
		if p.server != nil {
			_ = p.server.Close()
		}
		p.transport.CloseIdleConnections()
		p.mu.Lock()
		p.closed = true
		for connection := range p.conns {
			_ = connection.Close()
		}
		p.conns = make(map[net.Conn]struct{})
		p.mu.Unlock()
	})
}

func (p *connectProxy) serve(ctx context.Context) {
	go func() {
		<-ctx.Done()
		p.close()
	}()
	_ = p.server.Serve(p.listener)
}

func (p *connectProxy) connectionState(connection net.Conn, state http.ConnState) {
	switch state {
	case http.StateNew:
		p.mu.Lock()
		if !p.closed {
			p.conns[connection] = struct{}{}
		}
		p.mu.Unlock()
	case http.StateClosed, http.StateHijacked:
		p.mu.Lock()
		delete(p.conns, connection)
		p.mu.Unlock()
	}
}

func (p *connectProxy) ServeHTTP(response http.ResponseWriter, request *http.Request) {
	if request.Method == http.MethodConnect {
		p.handleConnect(response, request)
		return
	}
	p.handleHTTP(response, request)
}

func (p *connectProxy) handleConnect(response http.ResponseWriter, request *http.Request) {
	authority := request.Host
	if request.URL != nil && request.URL.Host != "" {
		authority = request.URL.Host
	}
	target, err := validateTailnetTarget(authority)
	if err != nil {
		http.Error(response, http.StatusText(http.StatusForbidden), http.StatusForbidden)
		return
	}
	hijacker, ok := response.(http.Hijacker)
	if !ok {
		http.Error(response, http.StatusText(http.StatusInternalServerError), http.StatusInternalServerError)
		return
	}
	client, buffered, err := hijacker.Hijack()
	if err != nil {
		return
	}
	p.mu.Lock()
	if p.closed {
		p.mu.Unlock()
		_ = client.Close()
		return
	}
	p.conns[client] = struct{}{}
	p.mu.Unlock()
	defer func() {
		_ = client.Close()
		p.mu.Lock()
		delete(p.conns, client)
		p.mu.Unlock()
	}()

	dialCtx, cancel := context.WithTimeout(request.Context(), 20*time.Second)
	upstream, err := p.dial(dialCtx, "tcp", target)
	cancel()
	if err != nil {
		writeProxyError(client, http.StatusBadGateway)
		return
	}
	defer upstream.Close()

	_ = client.SetDeadline(time.Time{})
	if _, err := io.WriteString(client, "HTTP/1.1 200 Connection Established\r\nProxy-Agent: Codex-Mobile-Bridge\r\n\r\n"); err != nil {
		return
	}
	copyTunnel(client, buffered.Reader, upstream)
}

func (p *connectProxy) handleHTTP(response http.ResponseWriter, request *http.Request) {
	target, err := validatePrivateHTTPTarget(request.URL)
	if err != nil {
		http.Error(response, http.StatusText(http.StatusForbidden), http.StatusForbidden)
		return
	}
	out := request.Clone(request.Context())
	out.RequestURI = ""
	out.URL.Scheme = "http"
	out.URL.Host = target
	out.Host = target
	removeHopHeaders(out.Header)
	out.Header.Del("Proxy-Authorization")
	out.Header.Del("Proxy-Connection")

	upstream, err := p.transport.RoundTrip(out)
	if err != nil {
		http.Error(response, http.StatusText(http.StatusBadGateway), http.StatusBadGateway)
		return
	}
	defer upstream.Body.Close()
	removeHopHeaders(upstream.Header)
	copyHeaders(response.Header(), upstream.Header)
	response.WriteHeader(upstream.StatusCode)
	_, _ = io.Copy(flushWriter{writer: response}, upstream.Body)
}

func writeProxyError(connection net.Conn, status int) {
	text := http.StatusText(status)
	_, _ = fmt.Fprintf(connection, "HTTP/1.1 %d %s\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s\n",
		status, text, len(text)+1, text)
}

func copyTunnel(client net.Conn, clientReader io.Reader, upstream net.Conn) {
	done := make(chan struct{}, 2)
	go func() {
		_, _ = io.Copy(upstream, clientReader)
		if tcp, ok := upstream.(*net.TCPConn); ok {
			_ = tcp.CloseWrite()
		}
		done <- struct{}{}
	}()
	go func() {
		_, _ = io.Copy(client, upstream)
		if tcp, ok := client.(*net.TCPConn); ok {
			_ = tcp.CloseWrite()
		}
		done <- struct{}{}
	}()
	<-done
	_ = client.Close()
	_ = upstream.Close()
	<-done
}

type flushWriter struct {
	writer http.ResponseWriter
}

func (w flushWriter) Write(data []byte) (int, error) {
	written, err := w.writer.Write(data)
	if flusher, ok := w.writer.(http.Flusher); ok {
		flusher.Flush()
	}
	return written, err
}

func removeHopHeaders(header http.Header) {
	for _, value := range header.Values("Connection") {
		for _, name := range strings.Split(value, ",") {
			if name = strings.TrimSpace(name); name != "" {
				header.Del(name)
			}
		}
	}
	for _, name := range []string{
		"Connection", "Keep-Alive", "Proxy-Connection", "Proxy-Authenticate",
		"Proxy-Authorization", "TE", "Trailer", "Transfer-Encoding", "Upgrade",
	} {
		header.Del(name)
	}
}

func copyHeaders(destination, source http.Header) {
	for name, values := range source {
		for _, value := range values {
			destination.Add(name, value)
		}
	}
}

func validateTailnetTarget(authority string) (string, error) {
	if authority == "" || strings.ContainsAny(authority, "\x00\r\n\t /\\@") {
		return "", errors.New("invalid proxy authority")
	}
	host, port, err := net.SplitHostPort(authority)
	if err != nil {
		return "", errors.New("proxy target must include a port")
	}
	host = strings.ToLower(host)
	if strings.HasSuffix(host, ".") || net.ParseIP(host) != nil || !tailnetHostPattern.MatchString(host) {
		return "", errors.New("proxy target is not a Tailscale DNS name")
	}
	number, err := strconv.Atoi(port)
	if err != nil || (number != 443 && number != 8443 && number != 10000) {
		return "", errors.New("proxy target port is not allowed")
	}
	return net.JoinHostPort(host, strconv.Itoa(number)), nil
}

func validatePrivateHTTPTarget(target *url.URL) (string, error) {
	if target == nil || target.Scheme != "http" || !target.IsAbs() ||
		target.Opaque != "" || target.User != nil || target.Hostname() == "" ||
		target.Port() != privateHTTPPort || target.Fragment != "" {
		return "", errors.New("private HTTP target is not allowed")
	}
	address, err := netip.ParseAddr(target.Hostname())
	if err != nil {
		return "", errors.New("private HTTP target must be an IPv4 address")
	}
	address = address.Unmap()
	if !address.Is4() || !tailnetAddressRange.Contains(address) {
		return "", errors.New("private HTTP target is outside the tailnet range")
	}
	return net.JoinHostPort(address.String(), privateHTTPPort), nil
}
