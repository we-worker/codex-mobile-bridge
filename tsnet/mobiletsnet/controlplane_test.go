package mobiletsnet

import (
	"context"
	"errors"
	"net"
	"net/netip"
	"strings"
	"testing"
	"time"
)

func TestFirstReachableMobileControlURL(t *testing.T) {
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
	if got, want := firstReachableMobileControlURL(ctx, addresses, dial),
		"https://10.0.0.2"; got != want {
		t.Fatalf("firstReachableMobileControlURL = %q, want %q", got, want)
	}
}

func TestChooseMobileControlURLRespectsExplicitControlServer(t *testing.T) {
	t.Setenv("TS_CONTROL_URL", "https://control.example.test")
	selection := chooseMobileControlURL(context.Background())
	if selection.URL != "" {
		t.Fatalf("chooseMobileControlURL overrode explicit server with %q", selection.URL)
	}
	if !strings.Contains(selection.Detail, "显式配置") {
		t.Fatalf("explicit server detail = %q", selection.Detail)
	}
}

func TestMobileErrorDetailRedactsCredentials(t *testing.T) {
	value := safeErrorDetail(errors.New(
		"auth tskey-auth-abcdefghijk Bearer abcdefghijklmnopqrstuvwxyz1234567890 " +
			"https://login.tailscale.com/a/private-token device " +
			"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"))
	for _, secret := range []string{
		"tskey-auth-abcdefghijk",
		"abcdefghijklmnopqrstuvwxyz1234567890",
		"https://login.tailscale.com/a/private-token",
		"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
	} {
		if strings.Contains(value, secret) {
			t.Fatalf("safeErrorDetail leaked %q in %q", secret, value)
		}
	}
	if len([]rune(value)) > 320 {
		t.Fatalf("safeErrorDetail exceeded limit: %d", len([]rune(value)))
	}
}
