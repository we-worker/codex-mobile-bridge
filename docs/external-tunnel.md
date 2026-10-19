# 已有穿透 / 反向代理接入（v2.1.0）

此方式适合已自行配置好 SakuraFrp、其他 HTTPS 穿透服务，或运行在**本机**的 HTTPS 反向代理。Bridge 只保存手机访问的公开地址；穿透客户端、域名、证书和代理由你在原服务中管理。此连接选项已在 [v2.1.0 正式版](https://github.com/try2love/codex-mobile-bridge/releases/tag/v2.1.0)中提供。

1. 在穿透或代理服务中，把 HTTP 上游设为运行 Bridge 的这台电脑的回环地址，例如 `http://127.0.0.1:8787`。`8787` 仅是示例，须使用桌面 App 当前显示的**实际网关端口**。若服务运行在容器中，容器内的 `127.0.0.1` 不一定指向电脑，请先确认网络路径；这类跨设备代理应使用下方的 NAS 进阶方式。
2. 确保公开入口有电脑与手机都信任的有效 HTTPS 证书。手机地址必须是完整的 HTTPS 根地址，例如 `https://bridge.example.com` 或 `https://bridge.example.com:8443`。不接受公开 HTTP、`/codex/` 等子路径、账号、查询参数或重定向目标；不要关闭 TLS 证书校验。
3. 在桌面 App 的“网络访问 → 添加连接”选择“已有穿透 / 反向代理”，填入该手机地址，保存并启动网关。此模式可以同时关闭局域网访问和本机网页访问；Bridge 仍仅为已配置的 HTTPS 入口保留本机回环上游。
4. 在 App 中点击“检测固定入口”。检查会从电脑对已保存的 HTTPS 地址请求无凭据的 `/api/auth`，验证证书和当前网关实例，不跟随重定向。检查成功后，卡片中的旧错误会被本次成功结果替换；修改入口地址后旧检测结果失效。再用手机蜂窝网络测试登录、聊天读取、发送和文件访问。扫码登录只在该地址真正连到当前网关时签发。

代理须将**原始公开 Host（含非标准端口）**、Origin、Cookie 与 `X-CSRF-Token` 传给网关。Nginx 可用 `$http_host` 保留 `:8443`；`$host` 可能丢失端口。不要把上游 Host 改为 `127.0.0.1`；网关会按公开 Host 和 Origin 检查请求。关闭代理缓存和响应缓冲，允许长时间请求、流式回复与应用所需的上传/下载大小。Bridge 主要使用 HTTP 长轮询或 SSE；若代理支持 WebSocket，也应保留升级请求，但不能用 WebSocket 支持替代流式响应与请求体限制检查。外部服务自身的上传限制、空闲超时和带宽仍可能限制附件与大文件。

如果反代运行在另一台 NAS / 服务器上，并且它通过电脑的局域网地址访问网关，在同一连接卡展开 **高级：目标所在位置**，将“穿透或反向代理运行在”选为 **NAS 或另一台设备**：保持局域网访问开启，填写 NAS 可达的电脑 HTTP 上游，端口须与网关一致，不能填 NAS 自己的回环地址。详见 [NAS 配置](../deploy/nas/README.md)。仅有公网地址而没有到电脑的上游通路，仍无法连接。

交互形式参考 [DSH Remote Web UI 的 `publicBaseUrl` 配置](https://github.com/DamonKoy/dsh-web-ui/blob/main/packages/dsh-remote-web-ui/README.md)；Bridge 独立实现了自己的连接配置与安全校验，没有复用其源码。

### 出现“此访问地址未在网关配置中允许”

这条提示表示请求已到达 Bridge，但请求中的 Host 不在允许列表中。先确认已在 Bridge 保存并启用该公开 HTTPS 地址，再检查代理是否保留了公开域名及端口，例如 `bridge.example.com:8443`。只有穿透端口映射、没有在 Bridge 登记公开地址，仍会被拒绝；代理改写 Host 或丢失非标准端口，也可能触发该提示。参见 [issue #35](https://github.com/try2love/codex-mobile-bridge/issues/35)。请按上述步骤配置，不要关闭 Host/Origin 校验。

## English

Use **Existing tunnel / reverse proxy** when you manage a trusted HTTPS tunnel or a proxy running on the gateway computer. Point its HTTP upstream to that computer's actual loopback gateway address, such as `http://127.0.0.1:8787` with your real port. Save only the phone's HTTPS root URL in Bridge, optionally with a port. Public HTTP, subpaths, redirects and disabled TLS verification are unsupported. The gateway can keep LAN and local browser access off while this configured HTTPS entry uses the loopback upstream.

Preserve the public Host (including a custom port), Origin, Cookie and `X-CSRF-Token`; disable proxy caching and response buffering, and allow long requests, streaming and the file sizes you need. Bridge uses long polling or SSE; WebSocket support alone does not establish compatibility. **Check fixed entry** verifies TLS and the current instance without credentials. Success replaces the previous error in the card; editing the entry clears the stale result. Then test sign-in, chat and files from your phone's mobile network. A proxy on another device must instead use the advanced [NAS setup](../deploy/nas/README.md) with a reachable computer LAN address. This option is available in the [v2.1.0 release](https://github.com/try2love/codex-mobile-bridge/releases/tag/v2.1.0).

If Bridge reports that the access address is not allowed, the request reached the gateway but its Host is not registered. Save and enable the public HTTPS URL, and ensure the proxy preserves the public hostname and any custom port. Port forwarding alone does not register an allowed address; do not disable Host/Origin validation. See [issue #35](https://github.com/try2love/codex-mobile-bridge/issues/35).
