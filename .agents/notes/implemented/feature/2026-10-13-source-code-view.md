# Agent Note: 只读源码预览保留原文和独立行号

Status: implemented

## Problem

工作台文件预览把文本直接放入 `pre/code`，常见源文件缺少语法颜色和行号。后续 HTML 源码切换也需要同一套只读渲染，不能让高亮生成的标记或行号改变复制内容。

## Decision

`BridgeSourceView.create({name, text})` 返回可嵌入预览的 DOM 节点。扩展名只决定 Prism 语法；未知类型显示原文。行号在独立、不可选中的栏内，代码节点中的文本保持服务端返回的原始字符串，复制按钮从该字符串复制。行号按 LF、CRLF 或单独 CR 计数；Tab 不替换。源码组件内可切换「自动换行」与「原始行宽」；默认保留原始行宽，以维持既有阅读方式。按钮按当前界面语言显示中英文，不增加全局设置。

每个原始行在代码节点里对应一个行元素，原始换行符保存在不可见的行尾文本中；Prism 词元跨行时只拆显示节点，不拆或规范化源码字符。代码行与独立行号栏进入同一 CSS Grid 行，所以软换行增加的高度同步给对应行号，超长无空格行也能在容器宽度内折行。选择代码触发的 `copy` 事件从原文和 DOM 选区边界重建文本，避免浏览器把 CRLF 规范化为 LF；已有「复制代码」按钮仍直接复制原文。

PrismJS 1.30.0 的 core 与首批必需语言组件一起作为本地脚本分发，MIT 许可在 `web/vendor/prism/LICENSE`。语言集合包括 markup、CSS、C-like、JavaScript、Python、TypeScript、JSX、TSX、JSON、YAML、TOML、Bash、PowerShell 和 Batch。脚本关闭全页自动高亮；源码视图只调用 `Prism.tokenize(text, grammar)`，把词元递归转为 DOM 文本节点和颜色 `span`。不经过 HTML 解析，CRLF、单独 CR 与 NBSP 等字符留在源码节点中。超过 65,536 个字符或 4,000 行时显示纯文本；超过 10,000 行时省略行号栏，避免生成庞大 DOM 和布局工作。工作区已有 512 KiB 预览上限，较大或非 UTF-8 文件显示原因并保留下载链接。

公开脚本 URL 在 `web/assets.json` 和 `bridge/api/assets.py` 同步，HTML 保证 Prism、源码视图、工作台依次加载。`scripts/gateway-resources.json` 纳入脚本和许可；SSH 注入仍只发送原有八个 Python 源模块，不依赖浏览器脚本。

## Existing-note audit

检索本仓库活跃笔记没有同一源码视图决定。已批准的本地提案还包含终端颜色和光标，源码部分由本笔记落实，终端部分保留待下一轮。

## Alternatives considered

- 保持普通 `pre/code`：资源少、渲染快，但缺少要求的语法颜色和行号。
- Prism 行号插件：可快速生成行号，但它把行号与代码块布局耦合；独立栏更容易保证选择和复制时不混入行号，并能单独限制大文件成本。
- 在两个并列 `pre` 上直接设 `pre-wrap`：改动少，但代码软换行后行号仍只占一行，会与原始行错位。
- `Prism.highlight` 的 HTML 字符串：调用简单，但写入 `innerHTML` 会经过 HTML 解析，可能规范化 CRLF 和 NBSP；直接使用词元与文本节点保存原字符。
- 从 CDN 加载 Prism：不增加本地资源清单，但离线和 SSH 网关页面会受外网影响。选用随网关分发的固定组件集。

## Consequences

常见源文件可辨识语法和行号，未知语言仍可阅读原文；窄屏可自行切换到自动换行。高亮脚本约 36 KB；超过阈值会失去颜色，超过 10,000 行仍省略行号，但仍能切换换行并查看、复制原文。按原始行建立显示节点增加 DOM 数量，因此继续保留大文件纯文本和极端多行省略行号的退化。此模块只负责只读源码显示，不处理终端 PTY 或 Markdown 预览。

官方依据：[Prism API](https://prismjs.com/docs/prism)、[PrismJS v1.30.0](https://github.com/PrismJS/prism/releases/tag/v1.30.0)。Context7 查询本轮返回配额耗尽，改用官方文档。组件从本机 npm 缓存的 `prismjs-1.30.0.tgz` 提取，缓存返回完整性标记 `sha512-DEvV2ZF2r2/63V+tK8hQvrR2ZGn10srHbXviTlcv7Kpzw8jWiNTqbVgjO3IY8RxrrOUF8VPMQQFysYYYv0YZxw==`。
