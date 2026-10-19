# markdown-it

- 固定版本：15.0.2（MIT，见 `markdown-it.LICENSE`）
- 上游：https://github.com/markdown-it/markdown-it
- 分发包：https://registry.npmjs.org/markdown-it/-/markdown-it-15.0.2.tgz
- 文件：`dist/browser/markdown-it.umd.min.js`，原样保存为 `markdown-it.min.js`
- SHA-256：`635972b985228e8af9f0143647c68616b7a3bb09f6946e7e4a52e43dcf5e7be5`

浏览器从网关本机加载，无需 CDN 或前端构建步骤。升级时同时更新版本、许可证和校验值，并运行 `tests/browser/markdown.browser.js` 的浏览器检查。

## KaTeX

- 固定版本：0.18.9（MIT，见 `katex/LICENSE`）
- 上游：https://github.com/KaTeX/KaTeX
- 分发包：https://registry.npmjs.org/katex/-/katex-0.18.9.tgz
- 包完整性：`sha512-8ad9RyoKsb/g8/yLFE+KAlP+DhbCTRUNi/V9XGsxn0R+trJJltNwzcDNo0q/DEkOy5fQUQTAQyCXCYSE+OakTQ==`
- `katex/katex.min.js` SHA-256：`155f6c2d673c5912e3b48f45d8830eaad18ae1953915939ceb648ea8b9c3e7e2`

## markdown-it-texmath

- 固定版本：1.0.0（MIT，见 `texmath.LICENSE`）
- 上游：https://github.com/goessner/markdown-it-texmath
- 分发包：https://registry.npmjs.org/markdown-it-texmath/-/markdown-it-texmath-1.0.0.tgz
- 包完整性：`sha512-4hhkiX8/gus+6e53PLCUmUrsa6ZWGgJW2XCW6O0ASvZUiezIK900ZicinTDtG3kAO2kon7oUA/ReWmpW2FByxg==`
- `texmath.js` SHA-256：`926e075a1745e1019813b8418b90183feea0c7b3782c85dceb4f246da999edc6`

KaTeX 脚本、样式和字体原样保存到 `katex/`；texmath 原样保存为 `texmath.js`。所有资源由本机网关提供，运行时不访问 CDN。公式升级后运行 `tests/browser/math.browser.js`，检查代码隔离、危险 TeX、流式输入和窄屏公式滚动。

## PrismJS

- 固定版本：1.30.0（MIT，见 `prism/LICENSE`）。
- 文件：`prism/source-view.min.js`，包含 core、markup、CSS、C-like、JavaScript、Python、TypeScript、JSX、TSX、JSON、YAML、TOML、Bash、PowerShell、Batch。
- 仅由源码阅读器调用词元接口，不启用全页自动高亮；未知语言或超出高亮预算时显示原文。详见[源码约定](../../.agents/notes/implemented/feature/2026-10-13-source-code-view.md)。

## PDF.js

- 固定版本：5.6.205（Apache-2.0，见 `pdfjs/LICENSE`）。
- 文件：legacy `pdfjs/pdf.min.mjs`、同版本 `pdfjs/pdf.worker.min.mjs`、`pdfjs/cmaps/` 和 `pdfjs/standard_fonts/`。
- CMap 与标准字体分别保留目录内的许可证；所有资源随网关分发，不使用 CDN。模块与 worker 必须同步更新，并检查中文、扫描页、混合页尺寸、文字选择与手机 WebView 兼容性。详见[PDF/HTML 约定](../../.agents/notes/implemented/feature/2026-10-13-pdf-html-preview-and-source-mode.md)。
