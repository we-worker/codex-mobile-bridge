//go:build android

package mobiletsnet

import (
	"errors"
	"net"
	"net/netip"
	"time"

	"tailscale.com/net/netmon"

	_ "tailscale.com/feature/androidbin"
)

// Android app UIDs cannot open NETLINK_ROUTE, so net.Interfaces fails before
// tsnet can initialize. gomobile builds GOOS=android with cgo, for which
// Tailscale deliberately leaves androidbin's fallback hook unregistered and
// expects the host app to provide interfaces. Register a small userspace
// implementation directly because this app uses tsnet without VpnService.
func init() {
	netmon.RegisterInterfaceGetter(androidNetworkInterfaces)
	netmon.UpdateLastKnownDefaultRouteInterface("android")
}

func androidNetworkInterfaces() ([]netmon.Interface, error) {
	var addrs []net.Addr
	if ip, ok := androidOutboundIP("udp4", "8.8.8.8:53"); ok {
		addrs = append(addrs, &net.IPNet{IP: ip.AsSlice(), Mask: net.CIDRMask(32, 32)})
	}
	if ip, ok := androidOutboundIP("udp6", "[2001:4860:4860::8888]:53"); ok {
		addrs = append(addrs, &net.IPNet{IP: ip.AsSlice(), Mask: net.CIDRMask(128, 128)})
	}
	if len(addrs) == 0 {
		return nil, errors.New("android network fallback: no outbound routes found")
	}
	return []netmon.Interface{{
		Interface: &net.Interface{
			Index: 1,
			MTU:   1500,
			Name:  "android",
			Flags: net.FlagUp | net.FlagRunning,
		},
		AltAddrs: addrs,
	}}, nil
}

func androidOutboundIP(network, address string) (netip.Addr, bool) {
	dialer := net.Dialer{Timeout: 2 * time.Second}
	conn, err := dialer.Dial(network, address)
	if err != nil {
		return netip.Addr{}, false
	}
	defer conn.Close()

	udpAddress, ok := conn.LocalAddr().(*net.UDPAddr)
	if !ok {
		return netip.Addr{}, false
	}
	ip, ok := netip.AddrFromSlice(udpAddress.IP)
	if !ok {
		return netip.Addr{}, false
	}
	ip = ip.Unmap()
	if ip.IsLoopback() || ip.IsUnspecified() {
		return netip.Addr{}, false
	}
	return ip, true
}
