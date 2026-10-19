## v2.1.1 · 模型与账号体验、草稿保存及文件定位

v2.1.1 改善 Codex、Claude 和 DeepSeek Harness 的账号与模型操作，减少重复加载，并补齐手机与 Web 的草稿保存、文件定位和导航体验。

### 新增与优化

- **统一账号与模型界面**：三个客户端采用一致的账号卡片和模型选择布局。当前账号卡片底部提供“查看可用模型”、用量更新时间及刷新；模型列表单独显示上次成功更新时间。
- **模型目录缓存**：优先显示缓存；手动刷新、切换接入或网关运行期间每 12 小时更新。按电脑、客户端、账号和有效接入配置隔离；失败保留原目录，不把失败时间当成成功更新时间。
- **API 与 CLI 模型查询**：补齐可核验的环境变量接入及 SSH CLI 上游目录，保留上游或原生运行时提供的具体模型和思考强度。Claude 账号模型查询不再要求先连接 Desktop；不支持的能力会说明原因，不编造型号或推理选项。
- **保留未发送草稿**：手机与 Web 切换聊天、客户端或电脑后，恢复对应输入草稿；按网关、账号与会话隔离，确认发送后清除。
- **更快定位文件**：从聊天链接定位文件或文件夹时平滑滚动到目标，并高亮 3 秒；用户滚动可以中止自动定位。左上角返回直接回聊天列表，文件区的上级目录与系统返回继续保留层级导航。
- **工具截图**：可查看工具返回的截图，并通过显示设置控制预览；限制预览体积及缓存占用。
- **更新与绑定选择**：网关及手机 App 可跳过当前版本的自动提醒，手动检查仍可更新；修改网关密码时可选择保留仍有效的手机绑定。

### Bug 修复

- 修复 Windows 账号切换或恢复时，配置文件被短暂占用导致操作中断；持续占用仍会报错并保留原文件。

- 修复 Codex 当前账号模型列表长时间停留在读取中、Claude 模型设置重复请求，以及账号切换后旧模型结果覆盖新接入的问题。
- 降低账号面板无必要的高频刷新，修复模型列表滚动时自动回到顶部。
- 修复快速从 Codex 滑到 DeepSeek Harness 时被拉回 Claude；Claude/DSH 重进列表优先展示缓存，再同步最新内容；统一筛选框样式。
- 修复非图片附件的显示与上下文信息、ChatGPT 登录经过自定义网关路由时的身份保留，并限制工作台启动资源并发。
- 修复 iOS 场景生命周期及通知跳转重试，避免启动或恢复期间丢失待处理跳转。
- 加强模型目录缓存身份隔离，修复网关直接查询上游模型目录时的环境凭据误用。

### 贡献者

- [@qybgh](https://github.com/qybgh) — [PR #38](https://github.com/try2love/codex-mobile-bridge/pull/38)：非图片附件显示与上下文修复。
- [@heiqiu47](https://github.com/heiqiu47) — 采纳 [PR #40](https://github.com/try2love/codex-mobile-bridge/pull/40) 中的账号卡片、模型选择和模型目录兼容改进，并适配到当前多客户端界面；不包含重置预测功能。
- [@Lovest20018](https://github.com/Lovest20018) — [PR #42](https://github.com/try2love/codex-mobile-bridge/pull/42) 的启动资源并发控制，以及 [PR #43](https://github.com/try2love/codex-mobile-bridge/pull/43) 的 ChatGPT 路由身份修复。
- [@RigerWu](https://github.com/RigerWu) — [PR #44](https://github.com/try2love/codex-mobile-bridge/pull/44)：工具截图预览、显示控制与缓存限制，以及 iOS 场景生命周期和通知跳转改进。

### 升级

网关与手机 App 均为 **2.1.1**，Android/iOS 构建号 **33**。支持 macOS Apple Silicon / Intel、Windows x64、实验性 Linux x64 / ARM64、Android，以及需自行签名的 iOS IPA/源码包。Linux 的 Claude 接入使用 Claude Code CLI；Claude Desktop 自动连接支持 macOS / Windows。

覆盖安装并保留原数据目录，避免先卸载或清除数据；Android 沿用原签名，iOS 请使用相同签名身份和 Bundle ID。浏览器在网关升级后刷新，共享中继部署同步更新服务。使用 `SHA256SUMS.txt` 校验下载。

### English

v2.1.1 improves account and model controls across Codex, Claude and DeepSeek Harness, reduces repeated loading, and preserves drafts while making files easier to locate on mobile and Web.

#### Features and improvements

- **Consistent accounts and models:** matching account cards and model pickers across clients. The current account footer contains available models, quota update time and refresh; model catalogs show their own last successful update time.
- **Cached model catalogs:** show cached results first, update on manual refresh or access changes, and refresh every 12 hours while the gateway runs. Keep computers, clients, accounts and effective access configurations separate; retain the last successful catalog after a failed refresh.
- **API and CLI discovery:** query upstream catalogs for verifiable environment-based access and SSH CLI, preserving model IDs and reasoning options supplied by the upstream or native runtime. Claude account catalogs no longer require Desktop to be connected. Unsupported capabilities are explained rather than guessed.
- **Saved drafts:** restore unsent text when switching chats, clients or computers, scoped to gateway, account and conversation. Clear drafts after confirmed sends.
- **File location and navigation:** smoothly reveal a linked file or folder and highlight it for three seconds; user scrolling can interrupt. The top-left Back button returns directly to the chat list; folder-parent controls and system Back retain hierarchical navigation.
- **Tool screenshots:** display tool-returned screenshots with preview controls and bounded preview/cache sizes.
- **Update and pairing choices:** skip automatic reminders for an exact release on desktop and mobile while retaining manual updates. Choose whether valid phone bindings survive a gateway password change.

#### Fixes

- Retry brief Windows file-sharing conflicts during account changes or recovery; persistent failures still report an error and preserve the original file.

- Fix stuck Codex account model loading, repeated Claude model requests and stale catalog responses after switching access.
- Remove unnecessary frequent account refreshes and preserve model-list scroll position.
- Prevent fast client swipes from jumping back to Claude; restore cached Claude/DSH lists before background updates and unify filter styles.
- Fix non-image attachment visibility/context and ChatGPT identity behind custom gateway routing; bound workspace startup resource concurrency.
- Handle iOS scene lifecycle and retry pending notification navigation during startup or resume.
- Strengthen model cache identity isolation and fix gateway environment credentials being used for direct upstream model-catalog HTTP requests.

#### Contributors

- [@qybgh](https://github.com/qybgh), [#38](https://github.com/try2love/codex-mobile-bridge/pull/38): non-image attachment visibility and context.
- [@heiqiu47](https://github.com/heiqiu47), selected work from [#40](https://github.com/try2love/codex-mobile-bridge/pull/40): account cards, model selection and catalog compatibility, adapted to the current multi-client UI. Reset predictions are not included.
- [@Lovest20018](https://github.com/Lovest20018), [#42](https://github.com/try2love/codex-mobile-bridge/pull/42) and [#43](https://github.com/try2love/codex-mobile-bridge/pull/43): bounded startup resource loading and ChatGPT routing identity.
- [@RigerWu](https://github.com/RigerWu), [#44](https://github.com/try2love/codex-mobile-bridge/pull/44): tool screenshots, display controls, bounded caches, iOS scenes and pending notification navigation.

#### Updating

Desktop and mobile version **2.1.1**, Android/iOS build **33**. Packages cover Apple Silicon/Intel macOS, Windows x64, experimental Linux x64/ARM64, Android and self-signed iOS. Linux uses Claude Code CLI; automatic Claude Desktop connection supports macOS and Windows.

Install over the existing app and retain its data directory. Android keeps its signing identity; iOS requires the same signing identity and Bundle ID to retain data. Reload Web pages and update shared-relay deployments. Verify downloads with `SHA256SUMS.txt`.

---

## v2.1.0 · CLI 接入、文件阅读与连接体验

v2.1.0 将 Codex CLI 与 Claude Code CLI 纳入手机和网页工作台，并改善已有 HTTPS 入口、文件阅读与多客户端连接。感谢通过 Issues 反馈使用体验。

### 新增功能

- **Codex CLI 会话**：发现并阅读本机或 SSH 上已有聊天；原终端关闭后，可显式点击“继续会话”恢复。支持从已知项目目录新建聊天、读取后续回复，并在原生运行时提供的范围内操作模型、推理强度、Skill、权限、计划模式、审批和 Goal。
- **Claude Code CLI 会话**：在本机或 SSH 上阅读历史、恢复已关闭的聊天，从已有项目新建聊天，并使用模型、权限、Skill、上传、审批和中断。各会话沿用执行端配置和工作目录，不接管其他终端中仍在运行的 Claude 进程。
- **独立 CLI 账号配置**：Codex 与 Claude 分别管理 CLI 接入、模型查询与连通性检查；桌面账号切换可选择同步本机 CLI，并分别显示结果。SSH 保留远端配置。
- **已有 HTTPS 入口**：可接入已有穿透或反向代理的 HTTPS 根地址，包括自定义端口；提供固定入口检测和配置引导。详见[配置说明](https://github.com/try2love/codex-mobile-bridge/blob/v2.1.0/docs/external-tunnel.md)。
- **文件阅读**：源码高亮、行号、复制和换行；PDF 连续滑动、缩放、文字选择与全屏；自包含 HTML 的隔离预览和源码切换。

### 体验优化

- Codex 列表按本机与各 SSH 主机逐步呈现，较慢的主机不阻塞已经读到的聊天；失败主机保留已有列表。Claude Desktop 与 CLI 混合列表按实际时间排序，来源标签持续显示在日期上方；客户端切换滑动时列表与标签布局更稳定。
- iOS Safari 保留原有页面布局，修复输入时的大面积空白及滚动抖动。弹窗可点击外部背景关闭。
- Claude 初始化在已确认提交后更早显示连接进度；Windows 与 macOS 的 Console 初始化减少多余等待。Claude 的额度改为手动查询，保留上次成功结果与时间。
- SSH 连接诊断可复制摘要或导出脱敏报告；文件目录逐级返回、全屏先退出，PDF 切换标签后保留阅读位置。所有客户端停用后，网关仍可独立启动和管理。

### Bug 修复

- 修复 Windows 连续终端子进程输出与 Ctrl+C，保留扩展路径中的项目工作目录；CMD 跨盘切换说明给出完整 `cd /d` 示例。
- 修复当前 DeepSeek Harness 主机记录在不同换行格式下的识别；修复 Claude Desktop 普通退出的会话归属判断、首次 Windows 初始化时的错误交接，以及重连与初始化期间的请求状态。
- 修复 Claude Desktop / CLI 混合日期排序，以及 Claude Code CLI 恢复时合成模型名覆盖真实模型的问题；已退出的旧版 Claude Code 写入者可在确认退出后恢复，身份不明的进程仍受保护。
- 修复固定 HTTPS 入口检测后的旧错误残留，并减少 PDF 快速翻阅、缩放时的闪烁。

### 升级说明

提供 macOS Apple Silicon / Intel、Windows x64、实验性 Linux x64 / ARM64、Android APK、iOS 未签名 IPA 和源码包。建议网关与手机 App 一起更新；浏览器用户更新网关后刷新页面，共享中继部署也需同步更新中继服务。Android 请覆盖安装以保留电脑列表和绑定，不要先卸载；iOS 需自行签名，并以相同签名身份覆盖安装以保留 App 数据。可用 `SHA256SUMS.txt` 校验下载。

CLI 需要执行端已安装并配置对应原生程序。Linux 支持 Claude Code CLI，Claude Desktop 自动连接仍只支持 macOS / Windows。PDF 在线预览上限 **20 MiB**，还受普通点击下载限额约束；源码与 HTML 预览支持 **512 KiB 以内 UTF-8 文本**。HTML 预览面向自包含文件，不访问外部网络或网关登录信息。

### English

v2.1.0 brings Codex CLI and Claude Code CLI chats to mobile and Web, together with existing HTTPS entry support, file reading, and more reliable multi-client connections.

#### Features

- **Codex CLI chats:** discover and read local or SSH history, explicitly resume after the original terminal closes, and create chats in known project folders. Supported native runtimes provide model/effort, Skills, permissions, plan mode, approvals and Goals.
- **Claude Code CLI chats:** read history, resume closed chats, create chats in known local or SSH projects, and use available models, permissions, Skills, uploads, approvals and interrupt. The execution host retains its configuration and working directory; live writers in other terminals are not taken over.
- **Separate CLI account settings:** manage Codex and Claude CLI access independently, query available models, test connectivity, and optionally sync a desktop account switch to the local CLI with separate results. SSH hosts retain their own settings.
- **Existing HTTPS tunnels and proxies:** add a managed HTTPS root URL, including a custom port, and check the fixed entry. See the [setup guide](https://github.com/try2love/codex-mobile-bridge/blob/v2.1.0/docs/external-tunnel.md).
- **File reading:** highlighted source with line numbers, copy and wrapping; continuous PDF scrolling, zoom, text selection and fullscreen; isolated preview and source mode for self-contained HTML.

#### Improvements

- Render Codex chat rows progressively as local and SSH hosts respond. Sort mixed Claude Desktop/CLI chats by actual recency and keep source labels visible above dates. Stabilize badges and the client-swipe layout.
- Preserve the original iOS Safari layout and fix large blank areas and scroll jitter while typing. Dismiss dialogs by tapping their backdrop.
- Show Claude connection progress after verified initialization submission and avoid redundant Console waits on Windows and macOS. Query Claude quota on demand while retaining the last successful result.
- Add copy/export SSH diagnostics, preserve file and PDF reading position, and keep the gateway manageable when every client integration is disabled.

#### Fixes

- Restore Windows continuous-terminal child output and Ctrl+C, preserve project cwd for extended local paths, and document a complete `cd /d` drive-switch example.
- Recognize the current DeepSeek Harness host across LF/CRLF records. Correct Claude Desktop quit ownership checks, first-time Windows initialization handoff, and request state during reconnect and initialization.
- Correct mixed Claude Desktop/CLI date sorting and prevent a synthetic model name from replacing the real Claude CLI model on resume. Resume legacy Claude writers only after their exit is confirmed.
- Clear stale fixed-HTTPS check errors and reduce flashes during rapid PDF navigation and zoom.

#### Updating

Packages cover Apple Silicon/Intel macOS, Windows x64, experimental Linux x64/ARM64, Android APK, unsigned iOS IPA and source. Update the gateway and mobile apps together; reload browser pages and update shared-relay deployments. Install Android over the existing app to retain saved computers and pairing. Sign and install iOS with the same signing identity to retain app data. Verify downloads with `SHA256SUMS.txt`.

The execution host needs its native CLI installed and configured. Linux supports Claude Code CLI; Claude Desktop automatic connection remains limited to macOS and Windows. PDF previews are capped at **20 MiB** and the ordinary-download limit; source/HTML previews accept **UTF-8 text up to 512 KiB**. HTML previews are self-contained and cannot access external networks or gateway sign-in data.

---

## v2.1.0-preview.1 · CLI 接入、已有 HTTPS 入口与阅读体验

这是 v2.1.0 的首个预览版，欢迎体验并通过 [Issues](https://github.com/try2love/codex-mobile-bridge/issues) 反馈问题和建议。稳定版继续保留 v2.0.3。

### 新增功能

- **Codex CLI 会话**：在手机与 Web 发现和阅读已有 CLI 聊天，原终端关闭后也可点击“继续会话”恢复；支持从已有本机或 SSH 项目目录新建 CLI 聊天。终端后续回复可持续同步阅读，每轮回复按原始记录显示模型。
- **CLI 完整操作**：Codex CLI 支持模型与推理强度、Skill、普通/计划模式、权限切换、审批与中断；兼容的本机和 SSH 原生 CLI 支持 Goal 的创建、暂停、修改、恢复与关闭。
- **Claude Code 本机与 SSH 接入**：支持历史阅读、已关闭会话恢复、新建聊天、发送消息、模型与权限切换、Skill、文件上传、审批及中断，沿用执行端的配置与工作目录。
- **独立 CLI 账号配置**：Codex 与 Claude 在各自账号管理中配置 CLI，支持查询上游模型和测试连通性，不依赖 Cockpit Tools。桌面账号切换可选“同时应用到本机 CLI”，分别显示生效结果；SSH 保留各服务器自己的配置。
- **已有穿透 / 反向代理入口**：填写已有 HTTPS 根地址即可接入，支持自定义端口；网络连接方式默认展开，并提供固定入口检测和更清晰的配置引导。详见[配置说明](https://github.com/try2love/codex-mobile-bridge/blob/v2.1.0-preview.1/docs/external-tunnel.md)。
- **文件阅读**：源码增加高亮、行号、复制与自动换行；PDF 支持连续滑动、双指缩放、文字选择和全屏，电脑保留翻页与缩放按钮；自包含 HTML 可预览内联交互、动画并切换源码。

### 体验优化

- 根据实际会话类型显示筛选与日期上方的类型标签；对齐 Codex 与 Claude 列表高度，Claude 上下文使用可点击查看详情的圆环。
- 客户端状态在后台更新，保留已有列表；CLI 短暂断线保留草稿与 Skill 选择。
- 设置中提供“SSH 连接诊断”，支持复制摘要和导出脱敏报告；顶部同一 SSH 故障可关闭。
- Claude 额度改为主动点击查询，显示上次成功查询时间，查询失败保留原结果。
- 文件描述与下载、复制、全屏操作并排；目录返回先回上一级，全屏返回先退出预览。PDF 切换标签与全屏时保留阅读位置。

### Bug 修复

- 修复 Windows Codex 保存历史与冷恢复中的长路径识别问题，以及已退出的旧版 Claude Code 会话被误判占用的问题；改善 Windows UTF-8 读取与 Linux 进程识别。
- 修复 CLI 后台读取短暂超时导致有效连接丢失的问题，改善 Goal 运行后的连接恢复。
- 修复固定 HTTPS 入口检测成功后仍显示上一次错误的问题；切换入口后清除旧结果。
- 减少 PDF 快速翻阅、缩放和邻页回看时的黑屏与闪烁，保留已渲染画面直到替换完成。

### 安装与使用

本次提供 macOS Apple Silicon / Intel、Windows x64、Linux x64 / ARM64、Android APK、iOS 未签名 IPA 和源码包。建议网关与手机 App 一起更新，浏览器用户更新网关后刷新页面；共享中继部署也需同步更新中继服务。Android 覆盖安装以保留数据，iOS 需自行签名。下载可用 `SHA256SUMS.txt` 校验。

CLI 需要执行端已安装并配置相应原生程序；不会接管其他终端仍在运行的 Claude 会话。PDF 在线预览上限为 **20 MiB**，同时受当前普通点击下载限额约束；源码与 HTML 预览支持 **512 KiB 以内 UTF-8 文本**，更大文件可下载打开。HTML 预览面向自包含文件，不开放外部网络与网关登录信息。

### English

This is the first v2.1.0 preview. Try the new features and share feedback through [Issues](https://github.com/try2love/codex-mobile-bridge/issues). v2.0.3 remains the stable release.

#### New features

- **Codex CLI chats:** discover and read saved CLI chats on mobile and Web, resume after the original terminal closes, and create chats in known local or SSH project folders. Follow later terminal-written replies and show each reply's recorded model.
- **CLI controls:** model/effort, Skills, default/plan modes, permissions, approvals and interrupt. Compatible local and SSH native Codex CLI runtimes support creating, pausing, editing, resuming and clearing Goals.
- **Local and SSH Claude Code:** read history, resume closed chats, create chats, send messages, select models and permissions, use Skills, upload files, handle approvals and interrupt, preserving the execution environment's configuration and directory.
- **Separate CLI account settings:** configure Codex and Claude independently, list upstream models and test connectivity without Cockpit Tools. Desktop account changes can optionally apply to local CLI, with separate results; SSH hosts keep their own configuration.
- **Existing tunnels / reverse proxies:** enter an existing HTTPS root URL, including a custom port. Connection options open by default, with fixed-entry checks and clearer guidance. See the [setup guide](https://github.com/try2love/codex-mobile-bridge/blob/v2.1.0-preview.1/docs/external-tunnel.md).
- **File reading:** syntax highlighting, line numbers, copying and wrapping for source; continuous scrolling, pinch zoom, text selection and fullscreen for PDFs, with page/zoom buttons on desktop; inline interactions and source view for self-contained HTML.

#### Improvements

- Show chat-type filters and labels above dates when relevant; align Codex/Claude lists and use a tappable context ring for Claude.
- Refresh client status in the background while retaining the list; preserve CLI drafts and selected Skills across brief disconnects.
- Add **SSH diagnostics** with copy/export and dismissible recurring SSH errors.
- Query Claude quota on demand, displaying the last successful query time and retaining results if a refresh fails.
- Place file actions beside the description, navigate Back through parent folders, exit fullscreen first and retain PDF reading position across tabs and fullscreen.

#### Fixes

- Fix Windows Codex extended paths in saved history and cold resume, and false occupied-state detection for exited legacy Claude Code sessions; improve Windows UTF-8 reading and Linux process identification.
- Retain valid CLI connections across brief history-read timeouts, including after Goal execution.
- Replace stale fixed-HTTPS errors after successful checks and clear old results when the entry changes.
- Reduce PDF flashes during rapid navigation and zoom by retaining rendered pages until replacements are ready.

#### Installation and usage

Packages cover Apple Silicon/Intel macOS, Windows x64, Linux x64/ARM64, Android APK, unsigned iOS IPA and iOS source. Update the gateway and mobile apps together; browser users reload after updating the gateway. Update shared-relay deployments as well. Install Android over the existing app to retain data; iOS requires your own signing. Verify downloads with `SHA256SUMS.txt`.

The execution host needs its native CLI installed and configured. Live Claude chats in another terminal are not taken over. PDF previews are capped at **20 MiB** and the ordinary-download limit; source/HTML previews accept **UTF-8 text up to 512 KiB**. Download larger files to open elsewhere. HTML previews are self-contained, without external network access or access to gateway sign-in data.

---

## v2.0.3 · 手机更新、第三方通知与界面优化

- **Android 应用内更新**：检查新版、查看更新说明，在 App 内下载 APK 并交给系统安装器。安装前校验大小和 SHA-256；完成下载后，即使离开 App 授予安装权限或重新打开 App，也可继续安装或保存 APK。
- **更新下载方式自己选**：可选「手机下载」或「电脑下载」。手机无法查询 GitHub 时可通过当前已登录网关查询；选择电脑下载后，由电脑下载并校验，再传给手机安装。下载失败可重新选择方式，或通过「GitHub ↗」在浏览器下载对应 APK，不会自动替换用户选定的下载方式。
- **手机与 Web 配置第三方通知**：从设置或聊天列表进入「第三方通知」，选择 **Bark（iPhone）、ntfy（Android）或 PushPlus（微信）**，分别配置、保存和测试；与电脑网关共用配置，也可修改通知跳转地址、标题显示及网关入口通知。该配置入口用于直连网关，共享中继保留原有权限范围。
- **搜索与筛选更紧凑**：搜索框始终可见，显示「搜索 / Search」；各选择框按当前内容分配宽度，其余空间留给搜索。精简英文按钮，改善手机横屏、平板和展开折叠屏上的 Claude、Codex、DSH 列表布局。
- **聊天列表减少干扰**：Claude 与 DSH 支持手动下拉刷新，保留搜索、筛选和阅读位置；移除常驻的读取与连接成功提示，恢复成功后清除过期错误，连接失败仍提供说明和重试入口。修复刷新失败提示持续停留的问题。
- **设置与工作台更清楚**：底部 App 图标开关、应用管理与第三方通知入口并列，兼顾中英文窄屏显示；文件传输保存按钮明确说明用途，修复未打开设置时遗留「请登录」提示的问题。关闭当前工具标签时切换到可用标签，避免不必要地退出分屏。
- **手机连接恢复**：Android/iOS 安全保存仍有效的扫码绑定凭据，WebView 登录状态丢失时尝试恢复；不保存网关密码，退出、移除电脑或撤销绑定后不再恢复。改善网关登录会话隔离、Claude 已初始化连接的重连入口，以及 macOS Claude 初始化时长 Console 输入的核验与连接效率。

### 致谢

感谢 [@SevenPwZ（des1re）](https://github.com/SevenPwZ) 在 [PR #32](https://github.com/try2love/codex-mobile-bridge/pull/32) 中贡献 Android 应用内更新。本版在该贡献基础上整合电脑协助下载、下载方式选择与安装恢复优化。

### 升级说明

建议电脑网关与 Android/iOS App 一起更新至 v2.0.3，以使用完整的通知配置、绑定恢复和更新改进。网页用户更新网关后重新加载页面即可。旧 Android 版本首次升级可下载 APK 覆盖安装，不要先卸载；后续更新可使用新版应用内更新。电脑协助下载需要配套网关，电脑仍须能访问 GitHub；仅更新手机时也可继续使用手机直连下载。iOS IPA 仍需自行签名，另附 Xcode 源码包；Linux 仍为实验性支持，使用安装包手动升级。正式下载文件可用 `SHA256SUMS.txt` 校验。

### English

- **Android in-app updates:** check releases, read notes, download the APK and open the system installer. Verify size and SHA-256 before installation. Keep a completed download available for installation or export after granting install permission or reopening the app.
- **Choose the download route:** download on the phone or let the signed-in computer gateway download, verify and transfer the APK. Release lookup can use the gateway if the phone cannot reach GitHub. Failed downloads offer route selection and a browser link to the matching APK; they do not silently switch the chosen route.
- **Third-party notifications on mobile and Web:** open **Push alerts**, select **Bark for iPhone, ntfy for Android or PushPlus for WeChat**, then configure, save and test that channel. Settings are shared with the desktop gateway, including notification links, title visibility and gateway address notifications. Configuration is available through direct gateway connections; shared-relay permissions are unchanged.
- **Compact search and filters:** keep Search visible, size selectors to their selected text and give the remaining width to search. Shorter English labels and consistent list layouts improve landscape phones, tablets and unfolded devices.
- **Quieter chat lists:** add manual pull-to-refresh to Claude and DSH, retain filters and reading position, remove persistent loading/connected messages and clear stale errors after recovery. Connection failures still show actionable messages and retry controls.
- **Clearer settings and workbench behavior:** place app-icon visibility, Apps and Push alerts together with narrow-screen English support. Clarify the file-transfer save action and prevent stale sign-in messages in unopened settings. Closing the active tool tab selects an available tab without unnecessarily leaving split view.
- **Connection recovery:** securely retain valid scanned-device credentials on Android/iOS and try to restore lost WebView sign-in state without storing the gateway password. Sign-out, removal and revocation stop recovery. Improve gateway session isolation, reconnection to initialized Claude sessions and long Console input verification during macOS Claude setup.

Thanks to [@SevenPwZ (des1re)](https://github.com/SevenPwZ) for Android in-app updates in [PR #32](https://github.com/try2love/codex-mobile-bridge/pull/32). This release builds on that contribution with gateway-assisted downloads, explicit download choices and installation recovery improvements.

Update both the gateway and mobile app for all improvements; reload browser pages after the gateway update. Older Android versions can install the APK over the existing app once, then use in-app updates. Computer-assisted downloads require a compatible gateway and computer access to GitHub. The unsigned iOS IPA requires your own signing; Linux remains experimental with manual package upgrades. Verify published downloads with `SHA256SUMS.txt`.

---

## v2.0.2 · 文件兼容与聊天列表体验优化

- **聊天列表更连贯**：Codex 列表滚动接近底部时自动加载后续聊天，移除常驻“加载更多”按钮。下拉刷新提示不再挤压列表，手势跟随与回弹更顺滑，成功提示更快收起；内容未变化时保留已有列表节点和阅读位置。
- **Windows 文件链接更可靠**：兼容盘符、反斜杠、file URL 和长路径前缀；同一文件的不同引用共用下载入口。继续使用现有工作区授权与可配置下载上限。
- **手机下载后直接打开**：Android 和 iOS 可通过系统支持的应用打开已下载文件，同时保留保存入口；系统区域颜色随当前页面变化。
- **跨平台登录自启**：Windows、macOS 和已安装的 Linux 桌面包可在高级设置中启用。Windows/macOS 登录后收起控制面板，macOS 可从菜单栏或 Dock 恢复；Linux 保持窗口可见，AppImage 使用原文件路径。
- 保留 v2.0.1 的 macOS 异常应用 plist 扫描修复。

感谢 [@heiqiu47](https://github.com/heiqiu47) 在 [PR #24](https://github.com/try2love/codex-mobile-bridge/pull/24) 中贡献的文件兼容、手机文件打开、系统栏与登录自启改进。本版按现有 main 的文件与认证边界整合，并扩展跨平台适配。

**升级**：建议网关与手机 App 一起更新至 v2.0.2，以使用完整改进。聊天列表优化由网关提供，升级后重新加载页面即可。Android 覆盖安装以保留已保存电脑与登录；iOS IPA 仍需自行签名，另附 Xcode 源码包。Linux 仍为实验性支持，请保留数据目录后手动安装。下载文件可用 `SHA256SUMS.txt` 校验。

### English

- Load more Codex chats automatically near the bottom, remove the persistent load-more button, and make pull-to-refresh smoother with a shorter success notice. Keep unchanged list nodes and reading position.
- Improve Windows drive paths, backslashes, file URLs and long-path aliases while retaining workspace authorization and configurable download limits.
- Open downloaded files through supported system apps on Android and iOS, retain Save, and match system-area colors to the current page.
- Add opt-in login startup for Windows, macOS and installed Linux desktop packages. Windows/macOS hide the control panel on login; Linux keeps it visible. macOS provides a menu-bar entry, and AppImage startup uses its original file path.
- Retain the v2.0.1 macOS malformed-plist discovery fix.

Thanks to [@heiqiu47](https://github.com/heiqiu47) for [PR #24](https://github.com/try2love/codex-mobile-bridge/pull/24). Update both the gateway and mobile app for all improvements. Install Android over the existing app; the unsigned iOS IPA requires your own signing. Linux remains experimental. Verify downloads with `SHA256SUMS.txt`.

---

## v2.0.1 · 修复 macOS 客户端扫描中断

- 修复 macOS 扫描应用时，某个应用的 `Info.plist` 存在 XML 格式错误，导致整轮客户端发现中断、已启用客户端无法继续自动接入的问题。
- 遇到这类异常应用时跳过该候选，继续发现其他客户端，并在网关日志中记录具体文件路径和解析原因，便于定位。
- 受影响的 macOS 用户建议更新电脑端网关；已有账号、会话与连接配置无需重新设置。

## v2.0.0 · 从手机聊天到多客户端远程工作台

v2.0.0 将 v1.4.0 的 Codex 手机网关扩展为 **Codex、Claude Desktop、DeepSeek Harness 的统一远程入口**。这次正式版汇总整个 v2 预览周期的工作台、手机 App、多客户端、网络连接和平台适配改进。任务继续在原电脑或对应 SSH 服务器运行，已有会话的提供商、认证与工作目录保持归属。

### 三个客户端，各自的会话与配置

- **自动发现与接入**：网关扫描本机已安装的 Codex、Claude Desktop 和 DeepSeek Harness。无需先启动网关，即可检查安装与登录状态、管理接入；后续安装客户端后可重新扫描。只有配置就绪的应用才能启用，网关启动后再连接已启用的应用。
- **独立聊天列表**：按应用切换聊天，创建会话时直接归属当前应用；Claude Code 与 Cowork 分组并可折叠。网页和手机共用会话状态标识、重连入口及可用能力提示。
- **受保护的启停**：桌面、Web 和手机可管理已配置客户端。正常退出前检查运行任务、等待授权与待发送内容；任务状态不明时保留明确的恢复指引。退出选项区分仅停用手机接入、正常退出与二次确认的强制退出。
- **恢复已有连接**：改善 Claude 断线重连、隐藏窗口恢复、中文路径与目录信任提示；核验并恢复旧 Harness 接入，处理插件更新和残留实例。发送或授权结果未知时，不自动重放操作。

### 聊天与项目工作台

- **文件标签**：浏览本机或 Codex SSH 会话的项目文件，预览文本、Markdown 和图片，上传文件，在聊天文件链接与目录之间定位。普通点击先选择定位或下载，默认下载阈值为 20 MiB，可从网关、Web 或手机即时调整。
- **大文件与目录下载**：文件列表长按、右键或键盘菜单可明确下载文件及目录，不受普通点击阈值限制；目录打包为 ZIP。下载浮窗显示进度、速度和总量，支持暂停、继续、取消；原生手机使用磁盘下载，浏览器仍受站点存储和设备空间限制。
- **图片缩放**：聊天图片、发送前附件和工作区图片共用查看器。手机双指缩放、放大后拖动；电脑滚轮缩放与拖动；双击切换适应屏幕与两倍，支持 1–8 倍及恢复适应。关闭图片后保留草稿、阅读位置和文件标签。
- **连续终端**：终端保留工作目录、环境和交互状态，支持多行命令、停止、清屏与尺寸变化。macOS/Linux 使用 PTY，Windows 使用 ConPTY，并补齐跨盘 `cd` 的处理；关闭刚创建的终端时也回收其所属进程树，避免后台残留。
- **Git 面板**：查看变更、差异、提交历史图和分支；暂存、提交、切换分支、本地合并与中止合并。保留工作区检查与确认，不提供远程推送或历史重写。
- **Codex 侧边聊天与子智能体**：在工作台查看子智能体历史，创建临时侧边聊天，独立选择模型、推理、Skill、权限和附件；支持排队、补充任务、普通/计划模式与同网关多设备同步。侧边聊天在结束或网关重启后清除，暂不支持 SSH。
- **宽屏分屏**：电脑浏览器、平板与折叠屏可将工具标签放到右侧并调整宽度；窄屏恢复单栏，保留标签、草稿和阅读位置。Claude/DSH 按自身协议提供工具能力，不把 Codex 专属功能伪装成全部客户端可用。
- **上下文与权限**：Codex、Claude Code 和 DSH 在权限附近展示上游提供的上下文用量，点击查看已用量、容量及说明；未提供的数据显示未知。权限按钮显示当前模式，模型与推理选项依照客户端能力。Codex 支持不选择项目创建会话。

### 账号、API、额度与模型

- **按客户端管理**：桌面网关管理 Codex、Claude、DSH 各自的已保存账号或支持的 API 接入，提供导入、修改、重命名和删除。Web/手机展示当前应用的账号信息，可切换已保存接入；凭据的新增与编辑仍留在电脑端。
- **当前接入更清晰**：当前账号置顶并标记，额度和重置卡紧邻账号；切换前核验任务，必要时重启对应客户端，并保留恢复信息。
- **API 使用自己的模型**：Codex 模型选择器与账号页共用当前 API 上游目录，支持主动刷新及手动填写；修复切换 API 后仍用官方地址或旧 GPT 列表的问题，兼容 CC Switch 模型目录。能列出模型不代表第三方协议一定兼容。
- **查询节奏可控**：进入账号页自动查询，可见时每五分钟更新，手动查询立即执行并重新计时；保留上次成功值和时间，失败不把未知余额显示成零。
- **官方额度与重置卡**：查看官方账号额度、恢复时间及服务返回的订阅周期；可为任一已保存的 Codex 官方账号使用重置卡，无需先切换接入。确认页核对账号与到期时间，等待五秒后才可消费，结果不明时复用原请求标识。
- **客户端能力有别**：Claude 支持已登录配置及第三方网关配置，DSH 支持保存当前账号、管理官方 API Key 与查询可用余额，任意第三方提供商需在 Harness 配置；模型、推理和额度以客户端/上游实际返回为准。Codex Fast、重置卡及 Skills 不扩展为其他客户端的通用能力。

### Android、iOS 与手机网页

- **多台电脑与扫码保持登录**：App 保存多台电脑，支持重命名、删除、按最近访问排序和手动刷新在线状态。扫码建立可撤销的可信设备绑定，普通网页登录过期不再迫使手机反复输入密码。
- **更紧凑的聊天列表**：搜索、排序与归档入口收拢；功能栏位于应用切换栏上方。只有一个已启用应用时隐藏切换栏；更多菜单可隐藏底部图标。左右滑动切换应用默认开启，带拖动预览，也可关闭。
- **电脑卡片上的应用通知**：显示已启用应用的原始图标，网关按用户通知选择维护各应用未读数；点击图标直接进入该应用列表。列表加载成功后标记已读，其他应用及新到达提醒保留；已读不等于批准权限请求。
- **通知权限与来源**：首次打开申请通知权限，允许后默认使用横幅和声音，保留用户后续选择。Android 大图标与 iOS 图片附件标明来源应用；iOS 系统小图标仍属于 Bridge，不能逐条替换成其他 App。
- **原生交互修复**：修复 Android 应用图标跳转地址校验、重复更多菜单、输入换行、剪贴板、附件和返回导航等问题；iOS 与 Android 共用页面宿主适配，同时保留各自原生扫码、下载与系统返回逻辑。

### 远程连接与网关设置

- **固定 HTTPS · Tailscale**：检测官方客户端、读取固定 `.ts.net` 地址，支持公网 Funnel 与私有 Serve，连接随网关启停。Funnel 下手机无需安装 Tailscale；Serve 需要同一私有网络权限。首次登录、网络权限及 Funnel 授权由用户在官方界面完成。
- **自有服务器 + SSH**：保留普通用户 SSH 反向转发、主机指纹核验及固定入口检测。手机访问地址可留空并使用服务器公网 IP 的 HTTPS 地址，但服务器仍需已有 HTTPS 反代和与 IP 匹配的受信任证书；不会自动降级 HTTP。
- **保留多种入口**：局域网、内置 Cloudflare 临时 HTTPS、固定 Cloudflare Tunnel、Tailscale、自有服务器与 NAS/已有反代可按需配置。移除桌面端“自建中继 · 内测”邀请码入口，减少普通用户配置负担。
- **网络提示更准确**：Cloudflare 和 Tailscale 公网转发/中继可能经过境外节点，中国大陆直连可能较慢或超时；固定域名不保证国内速度。首次配置后应在实际 Wi-Fi 与蜂窝网络验证。
- **设置重新分区**：概览、客户端与接入、网络访问、登录与设备、消息通知、应用与维护各司其职；概览和客户端页均可启停网关。修复网关实际已启动却被界面误报超时的情况；文件传输设置独立保存，异步加载不再误报网关配置未保存并阻止启动。

### 安全、效率与平台维护

- **请求与文件边界**：加固 DSH 带认证请求的重定向限制；限制中继压缩请求，避免解压后体积绕过；保留登录、CSRF、同源图片入口和受控文件访问。Windows 补齐 junction/reparse point、`.git` 大小写及 Win32 路径别名检查。
- **减少重复工作**：同轮状态刷新共用进程扫描，相同只读请求合并；发送、授权、停止保持独立。后台暂停终端读取并保留 shell，回前台按游标补读；手机通知使用增量游标，离开前台停止巡检。
- **Windows 与 Ubuntu 实测分支整合**：吸纳 Windows 安装发现、进程退出、终端和路径边界调整；改进 Ubuntu 启动器识别、权限能力查询与侧边聊天权限确认。Linux 仍为实验性支持，Claude 自动连接仅限 macOS/Windows。
- **更清晰的源码结构**：共享业务、客户端协议、操作系统实现分别归入 `features`、`clients`、`platforms`；Web 宿主与宽窄布局独立，Android/iOS 保留各自原生入口，共用注入脚本只有一份。便于在目标系统上定向维护。
- **保留 v1.4.0 的基础能力**：登录保护、会话归属、原生 Fast、模型/Skill 独立加载、已安装 Skill 链接、图片路径规范化、临时隧道重试和签名更新检查继续保留。

### 安装、升级与能力边界

- **电脑端**：提供 macOS arm64/x64 DMG 与 ZIP、Windows x64 Setup 与 ZIP，以及实验性 Ubuntu x64/ARM64 DEB 与 AppImage。macOS 使用 ad-hoc 完整性签名、未公证；Windows 无发布者证书签名。没有 Windows ARM64 专用包。
- **升级网关**：macOS/Windows 可在“应用更新”查看正式版，或停止旧网关并退出后手动安装；保留原数据目录。Linux 手动升级。不要让两个网关同时操作同一套客户端与数据。
- **Android**：覆盖安装 APK 以保留电脑列表和登录，不要先卸载。**iOS IPA 未签名**，需自行签名；源码包包含 Xcode 工程，暂无 App Store/TestFlight 分发。使用 `SHA256SUMS.txt` 校验下载。
- **Claude**：接入 Code/Cowork，不包含普通 Chat。首次初始化或丢失连接后的重新初始化可能需要电脑解锁、辅助功能/开发者模式及目录信任确认；已有连接优先在后台复用。不能承诺从锁屏状态完成冷启动。Cowork 未提供可靠上下文用量时显示未知。
- **通知与在线状态**：普通手机包依靠前台同步，不保证后台、锁屏或被系统终止后的送达；可使用 Bark、ntfy、PushPlus。灵动岛在后台可能显示最后状态。电脑睡眠或离线时无法继续远程操作。
- **原版 Codex 更新**：Bridge 可查询支持渠道的版本并引导原生更新器/商店；安装资格与确认仍由原应用处理，不承诺完全无人值守升级。此入口与 Bridge 自身更新独立。
- 客户端内部接口可能随上游更新变化。平台打包、模拟协议检查与真实账号/模型执行是不同验证范围；没有设备耗电测量，不宣称具体续航提升。

### 致谢

感谢参与跨平台真机测试、反馈和贡献的用户。保留 [@qybgh](https://github.com/qybgh) 在 [#15](https://github.com/try2love/codex-mobile-bridge/pull/15) 中的更新交接贡献、[@702165405](https://github.com/702165405) 在 [#16](https://github.com/try2love/codex-mobile-bridge/pull/16) 中的模型目录兼容贡献，以及 MIT 项目 [coding-mobile](https://github.com/2389859005/coding-mobile) 对 Claude/Harness 接入的参考；相关许可与归属随源码保留。

---

### English · v2.0.0

v2.0.0 expands the v1.4.0 Codex mobile gateway into **one remote entry for Codex, Claude Desktop and DeepSeek Harness**. It brings the v2 preview workbench, mobile apps, client management, networking and platform improvements into the stable release. Tasks continue on their original computer or SSH host with their session ownership, provider, authentication and working directory preserved.

#### Clients and sessions

- Discover installed clients, inspect login/setup readiness and manage connections before starting the gateway. Rescan after installing a client. Starting the gateway connects enabled, configured applications.
- Keep separate application chat lists; create chats under the selected client. Claude Code and Cowork have collapsible groups. Share activity indicators, reconnect controls and capability-aware messages across Web and mobile.
- Manage configured clients from desktop, Web and mobile. Check running tasks, approvals and queued input before quitting. Distinguish disconnecting mobile access, a normal quit and an explicitly confirmed force quit.
- Improve Claude reconnection, hidden-window recovery, Unicode paths and trust guidance. Verify and restore existing Harness integrations, including plugin updates and stale processes. Never automatically replay an operation whose outcome is unknown.

#### Chat and workbench

- Browse project files, preview text/Markdown/images, upload and locate chat-linked files in their folder. Ordinary downloads use a live configurable threshold, 20 MiB by default; larger links offer location first.
- Explicit long-press/right-click downloads allow files and ZIP folders above that threshold. A floating panel shows progress, speed and size with pause, resume and cancel. Native apps stream to disk; browser downloads remain subject to browser storage and device space.
- Zoom chat images, pending attachments and workspace images with pinch, wheel, drag or double-click. Scale from fit-to-screen to 8× and retain drafts, reading position and tabs when closing.
- Use persistent terminals with interactive shell state, multi-line input and resizing. macOS/Linux use PTY; Windows uses ConPTY with cross-drive `cd` handling; closing a newly created terminal also reaps its owned process tree.
- Review Git changes, diffs, commit graphs and branches; stage, commit, switch and locally merge branches. Dirty-worktree checks remain; remote push and history rewriting are not exposed.
- Codex temporary side chats support independent model/reasoning/Skills/permissions, attachments, queued input and Default/Plan modes. View saved subagent history. Side chats are cleared on end or gateway restart and do not support SSH.
- Move tool tabs into resizable split panes on wide browsers, tablets and unfolded phones. Smaller layouts retain drafts, tabs and reading position. Claude/DSH expose capabilities their protocols actually support, rather than claiming all Codex-specific tools.
- Show upstream context usage beside permissions for Codex, Claude Code and DSH, with a detail popover; unavailable usage remains unknown. Show current permission mode and supported model/reasoning choices. Create a Codex chat without selecting a project.

#### Accounts, models and usage

- Desktop manages each client's saved accounts or supported API connections, including import, editing, renaming and removal. Web/mobile show the selected client's information and can switch saved connections; credential creation/editing stays on desktop.
- Keep the active connection first with quota/reset credits beside the account. Verify tasks before switching, restart the appropriate client when needed and retain recovery information.
- Codex's model picker follows the active API provider. Refresh the upstream catalog or enter models manually; fix stale official API routing and GPT lists after switching, and retain CC Switch catalog compatibility. Listing a model does not prove third-party protocol compatibility.
- Fetch account data on opening, then every five minutes while visible; manual refresh runs immediately and resets the timer. Preserve successful values/timestamps on errors instead of showing unknown balances as zero.
- Use reset credits for any saved Codex official account without switching it active. Review the account/expiry and wait five seconds before confirmation; reuse the operation ID after an uncertain result. Subscription dates and balances reflect available upstream data.
- Claude supports saved login and third-party gateway configurations; DSH supports saved sign-ins, official API keys and queryable balances; arbitrary third-party providers must be configured in Harness. Quota, model and reasoning availability vary. Codex Fast, reset credits and Skills are not advertised as universal client features.

#### Mobile experience and notifications

- Save multiple computers, rename/remove them, sort by recent access and refresh reachability. QR pairing creates a revocable trusted-device binding that outlives ordinary browser login expiry.
- Compact search/sort/archive controls and application navigation. Hide the app bar when only one client is enabled, or collapse it from More. Swipe switching is enabled by default, has a visual drag preview and can be disabled.
- Computer cards show enabled app icons and gateway-maintained unread counts filtered by notification preferences. Open an application's list directly from its icon; acknowledge loaded notifications without clearing other apps, newly arriving events or pending approvals.
- Request notification permission on first launch and default to banners/sound after approval, while retaining user preferences. Android large icons and iOS attachments identify the source app; iOS retains Bridge's system app icon.
- Fix Android app-icon navigation URL validation, duplicate native menus, newlines, clipboard actions, attachments and back navigation. iOS/Android share host adaptation while retaining native scanning, downloads and navigation.

#### Networking and desktop organization

- **Tailscale HTTPS:** discover the official client and fixed `.ts.net` address, select public Funnel or private Serve, and run the entry with the gateway. Public Funnel needs no phone-side Tailscale installation; Serve requires authorized tailnet access. Login, system permissions and first authorization remain with Tailscale.
- **Own server + SSH:** retain ordinary-user reverse forwarding, host-key checks and endpoint verification. A blank phone address may use the server's public IP over HTTPS, provided the server already has HTTPS reverse proxying and a trusted certificate for that IP. No automatic HTTP downgrade.
- Keep LAN, bundled Cloudflare temporary HTTPS, fixed Cloudflare Tunnel, Tailscale, SSH servers and existing NAS/reverse proxies. Remove the invitation-based experimental relay entry from the desktop UI.
- Explain that Cloudflare and Tailscale public relay paths may cross overseas nodes and may be slow or time out in mainland China. A fixed hostname is not a performance guarantee; test actual Wi-Fi and cellular networks.
- Organize the gateway into Overview, Clients and access, Network access, Login and devices, Notifications, and App and maintenance. Both Overview and Clients control gateway start/stop. Fix false startup timeout reporting when the gateway is already reachable. Independently saved transfer settings no longer create a false gateway draft during asynchronous loading and block startup.

#### Security, efficiency and platforms

- Prevent authenticated DSH requests from following redirects; reject compressed relay requests that could bypass body limits. Retain authentication, CSRF, same-origin image and workspace boundaries. Harden Windows junction/reparse, `.git` case and Win32 alias handling.
- Reuse one process inventory per status refresh and merge identical concurrent read-only requests. Writes remain independent. Pause hidden terminal reads while keeping the shell and catch up by cursor on return. Use incremental mobile notification cursors and stop foreground polling in the background.
- Integrate Windows and Ubuntu validation branches covering discovery, shutdown, terminals and path safety; improve Ubuntu launchers and permission capability/confirmation handling. Linux remains experimental; Claude automatic connection supports macOS/Windows only.
- Separate shared business features, client protocols and OS integration, with independent Web host/layout modules and shared mobile injection sources. Preserve v1.4.0's login protection, native Fast, independent model/Skill loading, installed Skill links, image path normalization, tunnel retries and signed-update checks.

#### Downloads, upgrades and limits

- Desktop targets: macOS arm64/x64 DMG/ZIP, Windows x64 Setup/ZIP, experimental Ubuntu x64/ARM64 DEB/AppImage. Mac builds are ad-hoc signed, not notarized; Windows builds have no publisher certificate. No Windows ARM64 package.
- Update Bridge from the macOS/Windows app or stop the old gateway and manually install, retaining the data directory. Linux updates are manual. Avoid simultaneous gateways sharing client state.
- Install Android over the existing app to retain data. **The iOS IPA is unsigned** and needs your own signing; the source ZIP includes the Xcode project. No App Store/TestFlight distribution. Verify downloads with `SHA256SUMS.txt`.
- Claude integrates Code/Cowork, not regular Chat. Cold initialization or recovery may require an unlocked desktop, accessibility/developer permissions and directory trust. Existing connections are reused in the background; cold startup while locked is not guaranteed. Cowork context usage remains unknown where unsupported.
- Standard mobile builds synchronize in the foreground and do not guarantee background/locked/killed-app delivery. Use Bark, ntfy or PushPlus as needed; Live Activities may show the last state. Sleeping/offline computers cannot continue remote interaction.
- Original Codex update checks and handoff to its updater/store are separate from Bridge updates. Native eligibility and installation confirmation still apply; fully unattended Codex upgrades are not promised.
- Internal client APIs can change. Packaging checks, simulated protocol tests and real account/model execution are distinct. No battery-life gains are claimed without device power measurements.

Thanks to contributors and cross-platform testers, including [@qybgh](https://github.com/qybgh) ([#15](https://github.com/try2love/codex-mobile-bridge/pull/15)), [@702165405](https://github.com/702165405) ([#16](https://github.com/try2love/codex-mobile-bridge/pull/16)), and the MIT-licensed [coding-mobile](https://github.com/2389859005/coding-mobile) reference implementation. Attribution and licenses are retained.

---

## v2.0.0-preview.3 · 账号、模型与移动端体验改进

- **账号与重置卡**：整理“账号与接入”布局，当前接入置顶，刷新时保留上次成功的额度与更新时间。每个已保存的官方账号均可手动使用重置卡，无需先切换登录，也不依赖 Codex 的代理用量重置开关；确认页展示账号和卡片到期时间，等待五秒后才可使用，结果不明时重试同一请求。
- **模型与旧聊天**：模型选择器与账号页共用当前接入的模型来源，可主动刷新上游列表；官方模型的推理选项按能力匹配。切换接入后，兼容的旧聊天可继续使用新接入，修复旧供应商检查误拦发送的问题。回复旁展示该轮模型与推理强度，缺少记录的历史回复不补猜标签。
- **更轻的账号切换**：切换时只更新认证与接入配置，不再批量加载旧聊天或访问其项目目录；取消网关启动时的文稿目录探测。主动打开文件树、预览或下载附件等文件功能仍可能需要对应的系统权限。
- **手机连接与附件**：电脑列表支持重命名、移除连接及入口在线状态；聊天顶部可在保存的连接名称与真实设备名称之间切换。改进扫码后的登录保持，修复手机选完文件后附件名称、预览及上传状态缺失的问题，Android 与 iOS 同步相关界面和功能。
- **更紧凑的界面**：调整聊天列表顶部及底部按钮布局，将账号页刷新按钮放在标题旁；完善中英文操作提示、网关默认语言和手机弹窗样式。共享中继入口暂时隐藏。
- **桌面程序与更新**：新增桌面程序扫描，macOS 支持直接填写 `.app` 路径。“在电脑上检查 Codex 更新”打开原版 Codex 的“检查更新 / Check for Updates…”菜单，后续检查、下载与安装由 Codex 自身处理；网关仍使用独立的更新入口。

### 已知限制

- 订阅日期接口可能受限或无法返回日期，此时显示暂未确认，不据此判断订阅过期。真实账号查询仍存在被上游拒绝的情况。
- 已知 GPT-Load v2.0.0-rc.45 的 Antigravity → Gemini 协议转换路径可能返回 `422 protocol_conversion_unsupported`；能列出模型不代表该模型已能正常对话。
- 旧 API 聊天切回官方接入后，部分聊天可能暂不显示 Fast 开关。原版 Codex 的实际退出、启动和更新菜单、macOS 系统权限弹窗及手机真机仍需进一步验证；隔离运行时与模拟上游测试不等于这些场景已经实测通过。

这是主动选择体验的 **Pre-release**，不设为 Latest，不向 v1.4.0 正式版用户推送。Android 请覆盖安装以保留数据；**iOS IPA 未签名**，需自行签名，源码包提供 Xcode 工程，暂无 App Store / TestFlight 分发。使用 `SHA256SUMS.txt` 校验下载文件。

### English

- **Accounts and usage resets:** Improve the Accounts and access layout, keep the active connection first, and retain the last successful usage reading while refreshing. Use reset credits for any saved ChatGPT account without switching sign-in or enabling Codex's agent usage-reset setting. Review the account and credit expiry, wait five seconds to confirm, and retry the same request if its outcome is unknown.
- **Models and existing chats:** The model picker and account panel share the active connection's model source and support refreshing the upstream list. Official models show supported reasoning levels. Compatible existing chats can continue through the new connection after switching, without the stale-provider warning blocking messages. Replies show the model and reasoning level recorded for that turn; missing historical metadata is left unset.
- **Lighter account switching:** Switching updates authentication and connection configuration without loading all old chats or accessing their project folders. Remove the Documents-folder probe at gateway startup. Explicit file browsing and attachment previews or downloads may still require system file permissions.
- **Mobile connections and attachments:** Rename or remove saved computers, see connection availability, and toggle the chat header between the saved name and device name. Improve sign-in persistence after QR pairing and fix missing attachment names, previews and upload status after file selection. Android and iOS share these interface and feature updates.
- **Interface refinements:** Tighten chat-list controls, place account refresh beside the heading, and improve English/Chinese operation messages, default language selection and mobile dialogs. The shared-relay entry is temporarily hidden.
- **Desktop discovery and updates:** Scan for the desktop application and accept macOS `.app` paths directly. “Check for Codex updates on the computer” opens the original Codex app's “Check for Updates…” menu; Codex handles checking, downloading and installation. Gateway updates remain separate.

### Known limitations

- Subscription-date queries may be blocked or return no date. The interface reports an unconfirmed date rather than treating the subscription as expired; real-account queries can still be rejected by the upstream service.
- The Antigravity-to-Gemini conversion path in GPT-Load v2.0.0-rc.45 may return `422 protocol_conversion_unsupported`. A model appearing in the list does not establish that conversation requests work.
- Some former API chats may hide the Fast toggle after switching back to official sign-in. Original Codex app quit/launch and update-menu behavior, macOS permission dialogs and physical mobile devices still need further validation. Isolated runtime and mock-upstream checks do not establish that those scenarios have passed.

This is an opt-in **Pre-release**, not Latest, and is excluded from stable v1.4.0 updates. Install Android over the existing app to retain data. The **iOS IPA is unsigned** and requires your own signing; the source ZIP includes the Xcode project. There is no App Store or TestFlight distribution. Verify downloads with `SHA256SUMS.txt`.

---

## v2.0.0-preview.2 · 更新与模型兼容改进

- 优化应用更新流程，修复更新时可能卡住的问题。
- 改善第三方 API 模型列表兼容性，支持 CC Switch 模型目录。
- 保留现有 Android、iOS 和 Web 界面及操作方式，三端共用模型兼容改进。

### 感谢贡献者

- 感谢 [@qybgh](https://github.com/qybgh) 在 [#15](https://github.com/try2love/codex-mobile-bridge/pull/15) 中贡献的更新交接修复与测试，本版在确认更新助手就绪后执行交接。
- 感谢 [@702165405](https://github.com/702165405) 在 [#16](https://github.com/try2love/codex-mobile-bridge/pull/16) 中贡献的模型目录兼容改进。本次接纳该共用补丁，独立原生 Android 客户端未纳入本版。

这是主动选择体验的预发布版本，不设为 Latest；v1.4.0 正式版用户的更新通道保持不变。Android 可覆盖安装并保留数据；iOS 未签名 IPA 仍需自行签名，源码包提供 Xcode 工程。使用 SHA256SUMS.txt 校验下载文件。

### English

- Improve app update handoff reliability and third-party API model catalog compatibility, including CC Switch.
- Keep the existing Android, iOS and Web experience; all clients share the model catalog improvement.
- Thanks to [@qybgh](https://github.com/qybgh) for the update handoff work in [#15](https://github.com/try2love/codex-mobile-bridge/pull/15), and [@702165405](https://github.com/702165405) for the shared model catalog contribution in [#16](https://github.com/try2love/codex-mobile-bridge/pull/16). The standalone native Android client is not included.

This is an opt-in prerelease, not Latest. Stable v1.4.0 users remain on the stable channel. Install the Android APK over the previous preview; the unsigned iOS IPA requires your own signing.

---

## v2.0.0-preview.1 · 网页与手机远程工作台

这是主动选择体验的 **Pre-release**，不会设为 Latest，也不会向 v1.4.0 正式版用户推送更新。正式版继续保留。请先停止旧网关再试用预览，保留配置备份；体验后可重新安装正式版。

- **工作台标签**：在聊天旁浏览和传输文件，预览文本与图片，按类型区分图标，选择是否显示缩略图。
- **连续终端**：保留目录和 shell 状态，支持交互、停止与尺寸适配；手机可编写多行后再发送。
- **Git 面板**：变更与提交历史图、差异、暂存、提交、分支切换与本地合并。暂不提供远程推送或历史重写。
- **临时侧边聊天**：继承创建时的上下文，独立设置模型、思考程度、Skill 与权限，支持附件、排队和补充任务；普通／计划模式，同一网关的多设备可同步。结束或重启网关后清除，不会显示为 Codex 原生侧边标签；暂不支持 SSH 侧边聊天。
- **宽屏分屏**：拖动工具标签到右侧，调整两栏宽度。手机与窄屏保持单栏，输入区更紧凑。
- **Android 与 iOS App**：扫码保存多台电脑、直接复制、文件预览与下载、清空通知、设置中检查新版。安卓电脑列表双击返回退出，应用图标与项目 Logo 一致。

### 下载与更新

电脑端提供 macOS arm64/x64、Windows x64 和实验性 Ubuntu x64/ARM64 包。先安装本版网关，Web 打开其地址，手机 App 扫码连接。移动端使用预览通道，只有用户主动检查并选择后才打开下载或安装指引。

- **Android APK**：下载后覆盖安装，不要先卸载，以保留已保存电脑与登录状态。与本地 preview.10 使用同一签名。
- **iOS 未签名 IPA**：必须使用自己的 Apple 账号签名后安装；不能直接点开安装。`iOS-source.zip` 提供 Xcode 工程，可连接手机后签名运行。免费开发签名可能需要定期重新安装；尚无 App Store / TestFlight 发布。
- **通知**：App 前台可提醒新任务；不保证后台或锁屏送达。Bark、ntfy、PushPlus 仍可作为外部通知通道。灵动岛在后台可能显示旧状态。

使用 `SHA256SUMS.txt` 校验产物。macOS 为 ad-hoc 签名、未公证；Windows 无证书签名。预览功能仍可能存在兼容性问题。

### English

**An opt-in Web and mobile workbench preview.** This pre-release is not Latest and is excluded from stable v1.4.0 update checks.

Open project files, a continuous terminal, Git changes/history/branches, temporary side chats and saved subagent history in tabs. Wide browsers support resizable split panes. Side chats share state across clients and support models, reasoning, Skills, permissions, attachments, queued messages and Default/Plan modes. They are temporary Bridge chats, not native desktop side tabs; ending them or restarting the gateway clears them. SSH side chats are not supported.

Install the preview desktop gateway for the Web workbench. Android and iOS apps save multiple computers, copy directly, preview/download attachments and check for new releases from settings. Android can update by downloading the APK and installing over the existing App. The unsigned iOS IPA requires your own signing; the source ZIP includes the Xcode project. There is no App Store or TestFlight distribution yet.

**Notifications work primarily while the App is active; background/lock-screen delivery is not guaranteed.** Use external Bark, ntfy or PushPlus where needed. Live Activities may show an older state in the background.

Stop the old gateway before trying another build on the same port, and retain a configuration backup. Stable downloads remain available. Verify assets with `SHA256SUMS.txt`.

---

## v1.4.0 · 连接更简单，远程使用更顺畅

- **开箱即用的外网连接**：App 内置 cloudflared，临时 HTTPS 无需额外安装；完善固定 Cloudflare 域名、普通用户 SSH 和 NAS / 已有反代方案。
- **更清晰的配置体验**：每种连接均可折叠并直接打开对应在线指引；地址框自动补入 HTTPS 前缀，错误字段自动展开定位，短期通知显示 5 秒。保存的凭据可遮罩查看，SSH 私钥选择器支持隐藏目录。
- **更完整的登录保护**：支持记住登录 7 天、密码尝试次数提示、IP 封禁及电脑端解除，可选发送安全通知。
- **模型和 Skill 更易用**：保留原生 Fast 和自定义 API 模型目录，模型与 Skill 独立加载；Skill 支持缓存、搜索分页和完整描述，兼容正常安装的符号链接。
- **聊天与更新更稳定**：改善图片预览、临时隧道重试和更新交接；修复过期接入记录误拦发送。App 和网页均可忽略未确认发送提示，不会自动重发消息。
- **更直观的教程**：临时 HTTPS 标注“推荐”，固定域名、服务器和 NAS 标注“进阶”，提供分步图示及参考命令的适用条件说明。服务器管理员操作由用户自行完成，App 不执行 sudo。

合并 PR #11，并包含 Preview 测试期间的兼容性与体验修复。

**升级**：在正式版 App 的“应用更新”中检查更新，或先停止网关并退出，再安装对应平台的新包；保留原数据目录。Preview 用户请手动安装正式版并确认使用原数据目录。更新后重新加载手机页面。临时 HTTPS 地址可能因重启变化，请提前开启入口变化通知。

**English**

**v1.4.0 makes remote setup and everyday access easier.** The App bundles cloudflared and provides guided Cloudflare domains, regular-user SSH and NAS/reverse-proxy setups. Connection cards collapse, link directly to online guides, and expand when a field needs attention. Saved credentials remain masked and revealable.

Remember sign-in for seven days, see remaining password attempts, and manage blocked IPs from the desktop. Native Fast and provider-specific model discovery are preserved. Skills load independently with caching, search, pagination, full descriptions and support for installed symlinks. Image previews, tunnel retries and update handoff improve. Stale account records no longer block existing chats; both interfaces can dismiss unconfirmed send records without resending messages.

Includes PR #11 and fixes validated during Preview testing. Update through the stable App or stop the gateway and install manually, retaining the data directory. Preview users should install the stable App manually and select their existing data directory. Reload the phone page after upgrading. Mac packages are ad-hoc signed and not notarized; Windows packages have no certificate signature. Linux remains experimental.

---

## v1.3.3 · 能耗与通知优化

- **按需监控会话**：持续监听运行中和等待处理的会话，结束后解除通知订阅；通过实时事件和每 30 秒的变更元数据检查发现新任务，减少反复读取历史会话。
- **通知重试更独立**：完成通知发送失败时保留重试记录，不必持续订阅已结束会话。补齐会话再次运行、断线恢复、通知开关变化及完成状态先后到达的处理。
- **优化能耗**：状态查询复用进程；窗口隐藏时暂停刷新，状态不变时不重绘界面。
- **稳定窗口标题**：统一管理原生窗口标题，避免页面标题反复覆盖；切换语言时按需更新。

Mac / Windows v1.1.0 及后续版本可在“应用更新”选择“更新并重启”。保留数据目录即可保留登录、网络和通知设置。通过临时 HTTPS 远程升级前，请确认 v1.3.2 引入的“网关启动与入口通知”已开启且手机能够收到。Linux 仍为实验性支持，请停止网关并退出 App 后手动安装新版。

提供 Mac Apple Silicon / Intel 的 DMG、ZIP，Windows x64 的 Setup.exe、ZIP，以及 Ubuntu x64 / ARM64 的 DEB、AppImage。使用 `SHA256SUMS.txt` 校验下载；Mac / Windows 应用内更新使用签名的 `bridge-update.json`。Mac 仍为 ad-hoc 签名、未公证；Windows 无证书签名。

---

## English

**v1.3.3 reduces notification monitoring and desktop refresh overhead.**

- Monitor running chats and pending requests, then release notification subscriptions when idle. Live events and a metadata check every 30 seconds discover new activity without repeatedly loading historical chats.
- Retry failed completion alerts independently of subscriptions. Handle resumed chats, reconnection, notification preference changes, and completion updates arriving in separate steps.
- Reuse the desktop status worker, pause refreshes while the window is hidden, and skip unchanged UI renders.
- Keep the native window title stable and update it only when the language changes.

**Upgrade:** Mac / Windows v1.1.0 and later support App updates → Update and restart. Retain the data directory to preserve settings. Before a remote update over temporary HTTPS, enable and test the startup and entry notifications introduced in v1.3.2. Linux remains experimental and requires a manual upgrade after stopping the gateway and quitting the App.

Packages include Mac arm64/x64 DMG and ZIP, Windows x64 installer and ZIP, and Ubuntu x64/ARM64 DEB and AppImage. Verify downloads with `SHA256SUMS.txt`; Mac/Windows in-app updates use the signed manifest. Mac builds are ad-hoc signed, not notarized; Windows builds have no certificate signature.
