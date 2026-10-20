package mobiletsnet

import (
	"context"
	"fmt"
	"net"
	"net/netip"
	"os"
	"strings"
	"time"
)

const (
	controlPlaneHost    = "controlplane.tailscale.com"
	controlProbeTimeout = 4 * time.Second
)

type controlPlaneSelection struct {
	URL     string
	Detail  string
	Address int
}

// chooseMobileControlURL avoids handing tsnet a cached DNS answer containing
// only unreachable control-plane addresses. The Noise protocol and Tailscale
// authentication still run normally after this TCP reachability check.
func chooseMobileControlURL(ctx context.Context) controlPlaneSelection {
	if strings.TrimSpace(os.Getenv("TS_CONTROL_URL")) != "" {
		return controlPlaneSelection{Detail: "正在使用显式配置的 Tailscale 控制面地址"}
	}
	addresses := resolveMobileControlPlane(ctx)
	if len(addresses) == 0 {
		return controlPlaneSelection{Detail: "Tailscale 控制面 DNS 未返回可用 IPv4 地址"}
	}
	if value := firstReachableMobileControlURL(ctx, addresses, dialMobileControlPlane); value != "" {
		return controlPlaneSelection{
			URL:     value,
			Detail:  fmt.Sprintf("已选择可达的 Tailscale 控制面（%d 个候选中）", len(addresses)),
			Address: len(addresses),
		}
	}
	return controlPlaneSelection{
		Detail:  fmt.Sprintf("Tailscale 控制面返回 %d 个 IPv4 地址，但 443 端口均未及时连通", len(addresses)),
		Address: len(addresses),
	}
}

func resolveMobileControlPlane(ctx context.Context) []netip.Addr {
	seen := make(map[netip.Addr]bool)
	result := make([]netip.Addr, 0, 4)
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
			timer := time.NewTimer(150 * time.Millisecond)
			select {
			case <-ctx.Done():
				timer.Stop()
				return result
			case <-timer.C:
			}
		}
	}
	return result
}

func firstReachableMobileControlURL(ctx context.Context, addresses []netip.Addr,
	dial func(context.Context, string, string) (net.Conn, error)) string {
	if len(addresses) == 0 || dial == nil {
		return ""
	}
	probeCtx, cancel := context.WithTimeout(ctx, controlProbeTimeout)
	defer cancel()
	results := make(chan string, len(addresses))
	unreachable := make(chan struct{}, len(addresses))
	for _, address := range addresses {
		address := address
		go func() {
			conn, err := dial(probeCtx, "tcp", net.JoinHostPort(address.String(), "443"))
			if err != nil {
				unreachable <- struct{}{}
				return
			}
			_ = conn.Close()
			select {
			case results <- "https://" + address.String():
			case <-probeCtx.Done():
			}
		}()
	}
	for completed := 0; completed < len(addresses); completed++ {
		select {
		case value := <-results:
			if value != "" {
				return value
			}
		case <-unreachable:
		case <-probeCtx.Done():
			return ""
		}
	}
	return ""
}

var dialMobileControlPlane = (&net.Dialer{Timeout: 3 * time.Second}).DialContext
