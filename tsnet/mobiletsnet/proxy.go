package mobiletsnet

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
)

type dialFunc func(context.Context, string, string) (net.Conn, error)

var tailnetHostPattern = regexp.MustCompile(`^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.ts\.net$`)

type connectProxy struct {
	listener net.Listener
	dial     dialFunc

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
	for {
		connection, err := p.listener.Accept()
		if err != nil {
			return
		}
		p.mu.Lock()
		if p.closed {
			p.mu.Unlock()
			_ = connection.Close()
			return
		}
		p.conns[connection] = struct{}{}
		p.mu.Unlock()
		go p.handle(ctx, connection)
	}
}

func (p *connectProxy) handle(ctx context.Context, client net.Conn) {
	defer func() {
		_ = client.Close()
		p.mu.Lock()
		delete(p.conns, client)
		p.mu.Unlock()
	}()

	_ = client.SetDeadline(time.Now().Add(15 * time.Second))
	reader := bufio.NewReaderSize(client, 32<<10)
	request, err := http.ReadRequest(reader)
	if err != nil {
		writeProxyError(client, http.StatusBadRequest)
		return
	}
	if request.Body != nil {
		_ = request.Body.Close()
	}
	if request.Method != http.MethodConnect {
		writeProxyError(client, http.StatusMethodNotAllowed)
		return
	}
	authority := request.Host
	if request.URL != nil && request.URL.Host != "" {
		authority = request.URL.Host
	}
	target, err := validateTailnetTarget(authority)
	if err != nil {
		writeProxyError(client, http.StatusForbidden)
		return
	}

	dialCtx, cancel := context.WithTimeout(ctx, 20*time.Second)
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
	copyTunnel(client, reader, upstream)
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
