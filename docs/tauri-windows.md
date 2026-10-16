# Windows Tauri 客户端

Windows 桌面壳改为 Tauri 2，复用现有设置页面和 Python 网关，不在安装包中携带 Electron/Node.js。Windows 使用系统 WebView2；安装器只在系统缺少运行环境时下载引导程序，因此首次安装所需网络下载不能算进应用自身安装包体积。

## 使用和数据

- 使用 `Tauri-Windows-x64-Setup` 构建产物中的安装程序。它与原 Electron 应用区分安装，迁移期间请一次只运行一个控制面板。
- 保持原 `%APPDATA%/Codex Mobile Bridge/bridge-location.json`、语言设置和默认 `gateway` 数据目录。不会自动复制或重写 Codex/Magpie 的认证。
- 关闭窗口隐藏到托盘；托盘可打开/复制当前手机地址、停止网关并退出，或只退出控制面板并保留网关。
- 手机页面、配对、通知、Windows/WSL 入口和 Magpie 处理仍由原 Python 业务层提供；不替换原 Codex 执行进程。
- 登录自启只在构建后的应用中启用。迁移前若已启用 Electron 自启，应先在旧应用中关闭，避免两个版本同时自启。Tauri 不自动删除旧版本的系统启动项。
- **当前 Tauri 版使用手动更新。** 设置页明确显示提示并链接到本 Fork 的 Tauri 构建下载页；拒绝应用内安装 Electron 更新包。原有签名校验、Electron 更新器和回滚测试保持原样，不使用缺少签名的替代更新流程。后续正式发布需要单独建立 Tauri 签名更新通道。

## 实现边界

`src-tauri/src/main.rs` 管理窗口、原生文件选择、剪贴板、托盘和登录自启。只接受本机主窗口的固定页面调用，阻止外部导航；不向页面开放任意文件、进程或插件权限。SSH 主机信任必须经过原生确认，确认后 Python 再即时核对指纹。

`src-tauri/src/worker.rs` 持有一个随附 Python 管理进程，使用受限 JSON 行协议；没有新增管理 HTTP 端口。写入排队、不合并。调用超时返回结果未知，但队列仍等待原响应；损坏的通道不重启、不重放。退出界面通过管道 EOF 让已接受操作完成，不终止网关或原客户端。

`bridge/app/tauri.py` 复用 `Desktop`，保留账号登录状态和内存凭据；快照不返回连接明文凭据。目录切换前核验本机管理操作是否空闲。配对二维码在 Rust 中本地生成，不向图片服务传送登录令牌。Cloudflared 使用原构建脚本校验并随包携带的固定版本，“安装”操作复制该版本；源码运行未构建随附程序时可在设置中选择手动下载的程序。

`scripts/prepare-tauri.py` 按现有桌面资源清单选取网页资源，保持相对地址和脚本顺序；只为 Tauri 私有 IPC 增加 CSP 连接范围，保留禁止远程脚本、框架和任意导航。未修改手机/Web 的公开 URL。

## 开发与构建

推荐 Windows MSVC Rust 工具链和 Visual Studio C++ Build Tools。Python 构建环境依赖 `requirements-desktop.txt`；最终用户不需要 Python、Node 或 Rust。

```powershell
npm ci --ignore-scripts
python -m pip install -r requirements-desktop.txt
python scripts/build-desktop.py
npm run desktop                 # Windows: Tauri 开发；其他系统: 原 Electron
npm run desktop:electron        # 对照运行
npm run build:tauri             # Windows NSIS 安装程序
```

源码开发可设置 `CMB_PYTHON` 指定解释器；已有 `.tmp/tauri-venv` 时开发入口优先使用它。`CMB_DATA_DIR` 指定独立数据目录，同时隔离 WebView2 页面缓存。构建配置位于 `src-tauri/tauri.conf.json`，依赖由 `src-tauri/Cargo.lock` 锁定。默认仅构建一个安装程序，不把重复的便携包和安装包合并上传。

GitHub Actions 的 `Tauri Windows build` 独立编译、测试并上传安装程序，原 `Desktop builds` 继续提供 Electron 对照构建。Tauri 流程只上传构建产物，不创建 Release、不自动安装或发布。

## 验证和体积

```powershell
python -B -m unittest discover -s tests -p test_tauri.py -v
npm run test:desktop
python scripts/smoke-tauri.py src-tauri/target/release/codex-mobile-bridge-tauri.exe
python scripts/measure-tauri.py src-tauri/target/release
```

真实烟测使用 `.tmp/tauri-smoke-*` 的独立 Codex 数据、命名管道、网关端口和 WebView2 配置。通过原生窗口的真实页面检查私有调用、设置保存、语言、禁止的命令/URL、网关启停、二维码扫描和撤销、控制面板退出后网关继续运行。配对保持原限制：必须绑定一个实际本机 IPv4 地址，不能用回环地址绕过手机扫码规则；测试结束仅通过原身份核验逻辑停止自己的网关。截图和凭据只留在忽略的 `.tmp/`，不提交。

烟测使用 WebView2 的进程级调试参数操作自己启动的测试窗口，不改变产品默认调试配置。文件对话框的人工选择、系统登录后的自启、真实用户聊天发送和 SSH 主机信任未计作烟测通过项目。

`measure-tauri.py` 分开报告安装程序、原生主程序、Python 网关及其中 cloudflared 的字节数，应用有效载荷不包含共享 WebView2、用户数据和安装器元数据。不要将 GitHub 上同时包含安装程序与 ZIP 的旧 Electron artifact 总大小与单个 Tauri 安装程序直接计算压缩比例。安装包真实大小应以目标架构和 Python 版本对应的构建报告为准。

2026-10-16 本机 Windows x64 实测：567 项 Node 测试通过；后端定向 53 项中 52 通过、1 跳过；3 项 Rust 私有队列测试通过，包含迟到响应排空、结果未知不重发、坏帧关闭通道和业务拒绝后保持原进程。真实 WebView2/随附网关的六组烟测通过，页面无未捕获错误，截图已人工检查。原 Electron 更新器的 32 项回归也通过。未把这些定向检查表述为全量后端通过。

本机采用 Python 3.9 和现有 GNU Rust 工具链构建，单个安装程序约 **29.95 MiB**，应用有效载荷约 **98.85 MiB**，其中 cloudflared 约 **52.80 MiB**。GitHub Windows 构建采用 Python 3.13/MSVC，大小可能不同。开发脚本针对已有 GNU 工具链仅在本次构建进程中选择 Rust 自带链接器，不修改系统默认工具链或代理。
