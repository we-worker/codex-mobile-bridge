# Agent Note: 内嵌 Tailscale 避开不可达控制面缓存

Status: implemented

## Problem

Windows 内嵌 Tailscale 拿到有效的 `tskey-auth-*` 后仍长期停在“正在启动 App 内嵌 Tailscale”。状态目录已经生成机器身份，但没有节点身份或 Netmap。Tailscale 控制面域名会返回轮换的多个 anycast IPv4 地址；本机当时解析出的整组地址均在 `SYN_SENT` 超时，而其他 A 记录可以直接连接。Tailscale 的 DNS 缓存默认保留这组结果 10 分钟，`tsnet.Server.Up` 又没有应用级超时，因此界面会持续等待。

## Decision

sidecar 在加入 Tailnet 前连续解析 `controlplane.tailscale.com` 三次，合并并探测返回的 IPv4 地址，再使用一个可建立 TCP 连接的地址作为 `tsnet.Server.ControlURL`。Tailscale 的 Noise 协议仍负责控制通道认证，不降低现有加密或凭据边界。显式 `TS_CONTROL_URL` 继续优先，启动探测失败时回退到 Tailscale 默认解析。

使用认证密钥启动时增加 75 秒上限；Python 网关另设 90 秒看门狗，防止子进程内部状态机无响应时无限显示“正在启动”。启动阶段、网络超时、认证密钥拒绝和 HTTPS 未启用分别给出可操作状态。配置类错误会保留失败结果并停止自动重启，只有网络超时和未知连接错误进入退避重试。

## Verification

Go 回归覆盖控制面地址竞速、显式控制服务器优先级和错误分类。Tailscale/Tauri Python 回归共 27 项通过。真实 Windows 网络使用现有凭据和状态目录运行时，sidecar 在约 5 秒内完成控制面连接和 Tailscale 后端登录，不再停在启动状态；随后准确报告当前 tailnet 未启用 HTTPS Certificates。

## Boundary

本次修复解决控制面轮换地址带来的无限连接。未来若所有解析结果均不可达，仍会显示网络超时，不会伪造已连接。Funnel、Serve TLS 和固定 `.ts.net` 地址仍要求 Tailscale 管理后台启用 MagicDNS 与 HTTPS Certificates；真实 Funnel 公网链路需要在启用该账号设置后继续验证。
