# Tailscale 固定 HTTPS 入口

桌面 App 支持两种互斥的运行方式，Android App 也可在手机进程内加入 Tailnet：

| 运行方式 | 需要系统客户端 | 网络实现 | 适用场景 |
| --- | --- | --- | --- |
| **App 内嵌** | 不需要 `tailscaled`，也不创建系统 TUN/VPN 接口 | 桌面 App 启动 `codex-tsnet`，在进程内运行独立 Tailscale 用户态节点 | 希望由 App 自己管理连接，尤其适合远程或无桌面电脑 |
| **系统客户端** | 需要已安装并登录的 Tailscale 官方客户端 | 复用系统 Tailscale 的 Serve/Funnel | 已经统一维护系统 Tailscale 的电脑 |
| **Android App 内嵌** | 不需要安装 Android Tailscale 客户端，也不创建 `VpnService` | App 通过 `gomobile` 启动用户态 `tsnet`，只把 HTTPS `.ts.net` 交给本机 CONNECT 代理 | 手机位于 Tailnet 外，仍需私有访问固定 Serve 入口 |

两种方式都要求 Tailnet 开启 HTTPS/MagicDNS。选择 **公网访问 · Funnel** 时还需在 Tailscale 管理后台启用 Funnel；选择 **私有组网 · Serve** 时，访问设备必须位于同一 Tailnet 并获得 ACL 授权。

## App 内嵌 Tailscale

新建 Tailscale 连接时默认选择 **App 内嵌**。`codex-tsnet` 使用 Tailscale 的用户态网络栈连接到本机网关，再由 Tailscale 的 `ListenTLS` 或 `ListenFunnel` 提供固定 HTTPS 入口。它不使用 `VpnService` 一类系统 VPN 接口，不接管电脑路由，也不修改现有 Tailscale 客户端或其他 Serve 配置。

### 首次配置

1. 在 **网络访问 → 添加连接 → 固定 HTTPS · Tailscale** 选择 **App 内嵌**。
2. 填写设备名称，选择 **私有组网 · Serve** 或 **公网访问 · Funnel**，保存配置。
3. 选择登录方式：
   - **交互登录**：启动网关后，点击 **继续 Tailscale 授权**，在官方页面登录并授权。
   - **Tailscale 认证密钥**：填写密钥并选择保存。密钥只进入系统凭据存储，运行时通过私密 stdin 交给 sidecar。
4. 启动网关。首次登录或 Funnel/DNS 生效可能需要一段时间；状态从“正在启动”变为“已连接”前，旧地址不会加入网关可信源。
5. 点击 **检测内嵌 Tailscale 并读取地址**，确认它通过自身 Tailscale 网络访问到的 `/api/auth` 实例与当前网关一致。
6. 用手机实际访问、登录、打开聊天并发送一条消息。电脑端检测通过不等于蜂窝网络和 ACL 已通过。

交互登录适合有人操作桌面的电脑。无人值守或纯远程部署应使用 Tailscale 认证密钥。需要固定设备身份和地址时，不要使用会在节点离线后删除设备的 ephemeral key；密钥应按最小权限创建并妥善轮换。

### 公网发布校验

Funnel 模式下，`ListenFunnel` 返回成功、或从同一 Tailnet 内访问成功，只证明本机监听和 Tailnet 内链路成立，不能证明公网入口已发布。App 会继续执行以下检查，全部通过后才报告“已连接”：

1. 通过阿里、腾讯、Cloudflare 和 Google 的独立 DoH 服务查询该 `.ts.net` 地址的 A/AAAA 记录；不使用可能被 MagicDNS 或系统代理影响的普通解析结果。
2. 直接连接公开解析出的地址，使用真实 `.ts.net` 主机名执行证书校验。
3. 请求公网 `/api/auth`，并确认返回的 `instanceId` 与当前网关完全一致。

地址尚未发布时，界面会显示“Funnel 已在本机登记，正在等待公网 DNS 与 HTTPS 生效”，不会一直停在“正在启动”。等待窗口结束后，sidecar 会撤销并重新登记 Funnel；连续失败后会自动重建 sidecar，并逐步增加间隔。状态 JSON 只保留后端状态、健康项数量、在线节点数、能力标记和本机 Funnel 登记状态，不记录认证密钥、节点私钥或原始日志。

入口显示“已连接”后，sidecar 仍会每 45 秒重新查询公共 DNS、验证 `.ts.net` 证书并核对当前网关身份。单次网络抖动会立即复核；连续两次失败才会撤回临时 Origin、关闭旧 Funnel 监听并重新登记。这样既不会因一次短暂超时频繁重建，也不会在公网 DNS 被控制面删除后继续向手机展示一个已经失效的地址。

如果诊断中 `funnelCapability`、`httpsCapability`、`funnelPortsCapability` 和 `funnelRegistered` 均为 `true`，但多个公共 DoH 仍返回 NODATA，说明问题位于 Tailscale 控制面的公网发布，而不是 App 的监听、证书或 ACL 解析。此时应先停止反复手工重启，让 App 的退避重试继续，并检查 Tailscale 服务状态和管理后台设备记录。

公网 Funnel 需要账号策略同时满足 HTTPS 与 `funnel` 节点属性。默认 ACL 可在 Tailscale 管理后台的 `nodeAttrs` 中加入：

```json
{
  "nodeAttrs": [
    {
      "target": ["autogroup:member"],
      "attr": ["funnel"]
    }
  ]
}
```

### 生命周期与安全边界

- sidecar 随网关启停，只终止本实例创建的 `codex-tsnet` 子进程。
- 节点私有状态保存在网关数据目录的 `tsnet/<connection-id>/`。删除该目录会让内嵌节点丢失身份并需要重新登录；不要在未确认影响前清理。
- 内嵌节点只有从自身 Tailscale 网络访问当前网关的 `/api/auth`，并匹配本次运行的 `instanceId` 后，网关才会动态加入这个精确的 `.ts.net` Host/Origin。不会放行任意 `*.ts.net`。
- 旧的内嵌地址不会在网关启动时被当作永久可信 Origin。子进程退出、重连、身份变化或检测失败时都会撤回动态地址。
- 认证密钥不会出现在普通配置、状态 JSON、通知、日志或命令行参数中。配置、桌面快照和聊天 HTTP 也不返回明文密钥。
- 桌面 App 内嵌模式不退出用户账号，不执行系统 `tailscale down/logout`，也不调用 `serve reset`。
- Android 内置节点只在 App 进程内使用独立节点身份和回环代理；不声明 `BIND_VPN_SERVICE`，不接管系统 VPN 或手机路由。重置节点会删除手机上的节点身份与认证密钥，后端电脑和聊天记录不受影响。

### Serve、Funnel 与手机

**Funnel** 给普通浏览器提供公网入口，手机不必安装 Tailscale，但必须保留网关登录与扫码配对保护。

**Serve** 只允许 Tailnet 内设备访问。Android App 可直接连接 `.ts.net` 地址：首次使用会启动内置节点，可在应用设置中保存经 Android Keystore 加密的认证密钥，或在官方 Tailscale 授权页完成登录。App 只把 HTTPS `.ts.net` 请求交给内置节点，其他浏览和后台 HTTP 请求保持直连。该功能要求 Android 10 及以上，以及支持 `PROXY_OVERRIDE_REVERSE_BYPASS` 的当前 Android System WebView。

仍可使用手机上的官方 Tailscale 客户端访问私有 Serve。iOS App 尚未内嵌 `tsnet`；使用私有 Serve 时需在系统层接入同一 Tailnet，或使用 Funnel。

Tailscale 公网与 DERP 中继可能位于境外，速度受当前网络影响。内嵌模式省去系统客户端和 TUN，不保证比系统客户端或 Cloudflare 更快，也不保证一定能建立 P2P 直连；P2P 不可用时会回退到 Tailscale DERP。

## 系统 Tailscale 客户端

1. 安装 [Tailscale 官方客户端](https://tailscale.com/download)，登录并开启连接。版本需为 1.52 或更高。
2. 连接中选择 **系统 Tailscale 客户端**。
3. 检测并保存固定地址，启动网关并根据提示完成 Serve/Funnel 授权。
4. 本模式只创建前台 Serve/Funnel 会话；不会重置已有规则、关闭系统网络或注销账号。

macOS 建议使用官方独立安装包。Funnel 的平台和权限要求见其官方说明。

## 地址、端口和重启

- 地址通常为 `https://设备名.网络名.ts.net`，证书和 DNS 由 Tailscale 管理。
- 支持 HTTPS 端口 443、8443、10000。端口被其他服务占用时不会覆盖，改用另一个受支持端口并重新检测即可。
- DNSName、设备身份或 Funnel 状态可能变化。以当前运行状态和“检测固定入口”结果为准，不把上次保存的地址当成已连通。
- 删除设备、切换账号、清理节点状态或使用 ephemeral key 后，地址和授权可能需要重新处理。
- Tailscale 不会唤醒休眠电脑；电脑、网关和所需 Agent 客户端仍需运行。

## 排查

| 状态 | 处理 |
| --- | --- |
| 缺少 `codex-tsnet` | 使用包含内嵌节点的完整 App 构建；源码运行先执行 `python -B scripts/build-tsnet.py` |
| 等待登录 | 打开 **继续 Tailscale 授权**，或检查认证密钥是否有效、未过期且允许当前 Tailnet |
| HTTPS / MagicDNS 不可用 | 在 Tailscale 管理后台启用 HTTPS 与 MagicDNS |
| Funnel 不可用 | 启用 Funnel、确认账号/节点有权限，或先改用私有 Serve |
| Funnel 已在本机登记但公网 NODATA | 能力项和 `funnelRegistered` 为真时，问题在控制面公网发布；保留 App 的自动重登记，检查 Tailscale 状态和后台设备记录 |
| 正在验证但未就绪 | 只表示 Tailnet 内检查已完成；公网 DNS、TLS 或当前实例身份仍未全部通过，不要跳过这些校验 |
| 地址或身份变化 | 停止网关后重新检测并确认；旧地址会被动态撤回 |
| 私有 Serve 打不开 | Android 可在 App 内完成内置节点授权；其他设备需接入同一 Tailnet。再检查 Tailscale ACL 和设备授权 |

[tsnet 官方说明](https://tailscale.com/docs/features/tsnet) · [tsnet API](https://tailscale.com/docs/reference/tsnet-server-api) · [Serve](https://tailscale.com/docs/features/tailscale-serve) · [Funnel](https://tailscale.com/docs/features/tailscale-funnel)
