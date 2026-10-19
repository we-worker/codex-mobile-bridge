# Agent Note: 内嵌 Tailscale 避开不可达控制面缓存

Status: implemented

## Problem

Windows 内嵌 Tailscale 拿到有效的 `tskey-auth-*` 后仍长期停在“正在启动 App 内嵌 Tailscale”。状态目录已经生成机器身份，但没有节点身份或 Netmap。Tailscale 控制面域名会返回轮换的多个 anycast IPv4 地址；本机当时解析出的整组地址均在 `SYN_SENT` 超时，而其他 A 记录可以直接连接。Tailscale 的 DNS 缓存默认保留这组结果 10 分钟，`tsnet.Server.Up` 又没有应用级超时，因此界面会持续等待。

## Decision

sidecar 在加入 Tailnet 前连续解析 `controlplane.tailscale.com` 三次，合并并探测返回的 IPv4 地址，再使用一个可建立 TCP 连接的地址作为 `tsnet.Server.ControlURL`。Tailscale 的 Noise 协议仍负责控制通道认证，不降低现有加密或凭据边界。显式 `TS_CONTROL_URL` 继续优先，启动探测失败时回退到 Tailscale 默认解析。

使用认证密钥启动时增加 75 秒上限；Python 网关另设 90 秒看门狗，防止子进程内部状态机无响应时无限显示“正在启动”。启动阶段、网络超时、认证密钥拒绝和 HTTPS 未启用分别给出可操作状态。配置类错误会保留失败结果并停止自动重启，只有网络超时和未知连接错误进入退避重试。

`ListenFunnel` 成功和 Tailnet 内回环成功不再等同公网可用。Funnel 模式先报告 `listening`，随后用独立 DoH 查询 A/AAAA，直接拨接公开地址并用真实 `.ts.net` 主机名验证 TLS，再核对公网 `/api/auth` 的当前 `instanceId`；只有全部通过才报告 `connected`。DoH 先使用当前网络可访问的阿里和 DNSPod，再回退 Cloudflare 和 Google，避免境内系统 DNS 无法解析公共 DoH 域名时产生假失败。

公网地址在 90 秒窗口内未发布时，sidecar 关闭并重新登记 Funnel，再以逐步增加的间隔重试；连续三轮失败后退出，让 Python 生命周期重建 sidecar。状态 JSON 仅保存脱敏计数和能力标记，包括 Funnel、HTTPS、端口策略和本机 `AllowFunnel` 是否登记，不记录密钥、节点私钥或原始日志。

连接成功后，sidecar 每 45 秒重新执行同一组公网 DNS、TLS 和实例身份校验。单次失败会在 5 秒后复核，连续两次失败才撤回临时 Origin、关闭监听并重新登记 Funnel；健康状态下不重复改写状态文件，避免无意义磁盘写入。

## Verification

Go 回归覆盖控制面地址竞速、显式控制服务器优先级、DoH JSON 过滤、公网探测注入、发布窗口、持续健康检查、失败阈值和错误分类。Tailscale Python 回归覆盖 `listening` 不再误报 `connected`、诊断字段持久化、超时重试，以及重新登记前撤回旧 Origin。

验证结果为 Go 全部通过、Tailscale Python 21/21、后端源码集 2035 项通过（68 项按 Windows/POSIX 或原生夹具条件跳过）、桌面前端 758/758。真实 Windows 网络重启开发网关后，Cloudflare、Google 和 DNSPod 三家 DoH 均返回 Funnel 的 A 记录；两个公网边缘地址的 TLS 校验均为 0、首页均返回 `200`，`/api/auth` 均返回当前网关实例，最终状态进入 `connected`。

## Boundary

本次修复解决控制面轮换地址带来的无限连接、本机 Funnel 成功被误当成公网成功，以及连接后公网入口被控制面撤下却仍长期显示可用的问题。未来若所有解析结果均不可达，仍会进入明确的重试或失败状态，不会伪造已连接。Funnel、Serve TLS 和固定 `.ts.net` 地址仍要求 Tailscale 管理后台启用 MagicDNS、HTTPS Certificates 和 Funnel 节点属性；控制面在能力项全部满足后仍不发布或撤下 DNS 的情况属于 Tailscale 公网入口故障，App 无法在客户端侧强制生成该公共记录。
