# Claude Code CLI 接入可行性核查（2026-10-14）

## v2.1.0 后续实施状态

本页下方保留初始探针的条件和结论，不作为当前功能清单。初始 `--bare` 探针之后，macOS 已另行验证所选认证与项目 `CLAUDE.md` 的隔离继承；这些合成/回环请求不代表真实付费或 OAuth 验收。后续候选已实现本机及 SSH Claude Code 的已关闭会话恢复、新建、发送、模型/权限、Skill、文件上传、审批和中断；账号管理可独立配置 CLI 接入。仍不接管其他终端中的活跃写入者。

Windows 10 x64 / Claude Code 2.1.168 与 Ubuntu 22.04.5 x64 / 2.1.287 已通过独立 Test 包安装、GUI 和已安装网关的 CLI HTTP 验收，包含完整回复、审批允许/拒绝及重启后历史；Linux SSH 控制另有真实服务器验收。以上跨平台运行使用隔离配置和模拟 API，不代表真实付费认证、所有项目配置或手机真机已验收。当前能力与限制以 [CLI 接入说明](codex-cli.md) 和 [验收总览](../VERIFICATION.md#v210-platform-status) 为准。

## 初始探针结论

**可验证的范围是由网关自己启动并持有的 CLI 进程，以及已退出会话的显式恢复。** 本机 Claude Code `2.1.287` 在隔离环境中通过了两轮 `--resume <session-id>` 续接和同一进程内两条 `stream-json` 输入。手机端若要提供实时消息与控制，需要持有该进程的输入/输出通道，或采用官方 Agent SDK 的流式会话接口。现有证据不足以支持“无侵入接管用户正在另一终端运行的任意 Claude Code 进程”。

这个结论只涉及接入机制。未使用用户的 Claude 登录、订阅额度、真实 API Key、真实会话或远程主机。Claude Desktop Code/Cowork 的现有连接器属于另一条执行通路，不能据此推断 CLI 进程可接管。

## 初始本机实测

安装的 `/opt/homebrew/bin/claude --version` 返回 `2.1.287 (Claude Code)`。探针位于项目的 `.tmp/cli-expansion-20261014/claude-probe-artifacts/`（`probe.py`、`control_probe.py`、`approval_probe.py`），其结果保留在同目录的独立运行文件夹中，不纳入提交。探针使用临时 `HOME` 与 `CLAUDE_CONFIG_DIR`、`--bare`、假 API Key、仅指向 `127.0.0.1` 的 `ANTHROPIC_BASE_URL`，并禁用非必要流量；本地 HTTP 服务只返回预设文本/工具调用，没有外部模型请求。

| 检查 | 观察 | 证据界限 |
| --- | --- | --- |
| 保存并冷恢复 | 第一进程输出 `LOCAL_MOCK_REPLY_1` 后退出；第二进程用同一 UUID `--resume` 输出 `LOCAL_MOCK_REPLY_2`，退出码均为 0。隔离目录仅有一份该 UUID 的 `.jsonl` 会话文件；第二次请求包含更多历史消息（2 → 4）。 | 证明这台机器的 2.1.287 能在假接口下按 ID 续接；不证明真实订阅/模型可用。 |
| 双向流输入 | `--input-format stream-json --output-format stream-json` 接受同一进程的两条用户消息，产生两次用户确认、两条成功结果及同一会话 ID。 | 证明消息与结果通路。 |
| 动态模型 | 同一进程的 `set_model: haiku` 控制请求返回 `success`；随后 `system/init.model` 和发往本地假接口的请求均为 `claude-haiku-4-5-20251001`。 | 证明下一轮生效；没有真实模型调用或订阅认证。 |
| 动态权限 | `set_permission_mode: plan` 和 `dontAsk` 均返回 `success` 和 `response.mode`；随后两条 `system/status.permissionMode` 依次报告 `plan`、`dontAsk`。 | 证明状态切换；真实用户策略、项目配置与工具集组合未验证。 |
| 运行中打断 | 假接口延迟响应时，`interrupt` 收到 `success` 回执；该轮随后出现 `[Request interrupted by user]` 和 `terminal_reason: aborted_streaming`，进程退出码为 1。 | 中断已发生；中断结果是错误终态，接入层不可将控制回执当作正常回答。 |
| 工具审批 | 假模型请求在隔离工作目录执行 `Bash: touch approval-marker`；CLI 发出 `can_use_tool`，包含输入、`tool_use_id`、`blocked_path` 和建议规则。宿主返回 `behavior: deny` 后工具结果为 `Synthetic host denial`，标记文件不存在。 | 验证拒绝回路；尚未验证允许后的执行、`AskUserQuestion` 或真实配置。简单 `printf` 被 CLI 自行放行，说明不是每个工具调用都会生成审批卡。 |
| 保存历史 | 隔离的 `.jsonl` 包含 user/assistant 等事件。 | 这些文件可供只读研究；未找到可承诺稳定格式的公开历史读取协议，不能直接把文件布局当成长期 API。 |

首次探针因假服务没有解析 `/v1/messages?beta=true` 的查询串而返回模拟模型错误；修正假服务路由后上述检查通过。该失败只属于探针，不是 Claude Code 的接入失败。

## 文档与控制协议

- [Claude Code 无头模式](https://code.claude.com/docs/en/headless) 规定 `-p`、`--output-format stream-json`、`--continue` 和 `--resume` 的行为；运行中停止可用 SIGINT 或 SDK 的 `interrupt()`。单次 `-p` 调用适合续接后的一轮任务；[SDK 流式输入](https://code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode) 面向持久、多轮、排队和打断。
- [SDK 审批与用户输入](https://code.claude.com/docs/en/agent-sdk/user-input) 使用 `canUseTool` 回调交回批准/拒绝及 `AskUserQuestion`。[官方 Python SDK 源码](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/query.py)给出 `control_request` / `control_response` 封装、`set_model`、`set_permission_mode`、`interrupt`、`can_use_tool` 的具体字段与回执；本次按该结构对本机 CLI 做了隔离实测。没有可答复的宿主通道或配置为 `dontAsk` 时，不能把手机端显示审批卡等同于真实挂起请求。
- [SDK 权限文档](https://code.claude.com/docs/en/agent-sdk/permissions)支持会话启动时指定模式及运行中 `setPermissionMode()`；本机 CLI 帮助也列出 `--permission-mode` 和 `--model`。本次动态模型、权限、打断及拒绝审批只证明本机假接口条件下的协议行为。
- [会话文档](https://code.claude.com/docs/en/agent-sdk/sessions) 将恢复定位为按 ID 从持久会话重新运行。安装的 CLI 帮助将 `claude attach <id>` 描述为附着由 `--bg` 管理的后台任务；没有发现可让第三方程序无侵入共享任意现有交互终端标准输入/输出和审批回调的公开接口。因此，任意活跃终端的实时接管保持**未证实**，设计不能以它为前提。

## 身份、配置与产品边界

探针的 `--bare` 有意绕开真实配置和登录。正式候选方案若要保留原用户的项目指令、Skills、hooks、MCP、供应商与权限规则，必须先审计正常 `-p` 的设置来源及当前工作目录，再验证原会话的配置继承。官方[无头模式文档](https://code.claude.com/docs/en/headless)指出：正常 `-p` 会加载用户/项目上下文，且对未信任目录也不会弹工作区信任框；`--bare` 则跳过许多上下文和 OAuth/钥匙串登录，要求 API Key 或指定密钥助手。不能用本次 `--bare` 成功声称已保留用户的日常 Claude Code 环境。

[Agent SDK 官方说明](https://code.claude.com/docs/en/agent-sdk/overview)明确表示，未经事先批准，第三方开发者不得在自己的产品中提供 claude.ai 登录或订阅限额，应使用 API Key 认证方式。SDK 能启动同类代理循环，并不意味着可将用户的 Claude 订阅登录移植到本产品。[Remote Control](https://code.claude.com/docs/en/remote-control) 面向 claude.ai/code 与官方 Claude 手机端；它要求合规订阅，API Key、自定义 `ANTHROPIC_BASE_URL` 和第三方上游均不支持该通路。它可作为用户已有的官方远控方案参考，不是本项目可复用的公开接入协议。

## 初始探针提出的后续验证要求（历史记录）

先以**网关持有的专用 CLI 进程**为候选形态，在明确可用的认证方式下，补验正常配置下的流式多轮、允许/拒绝审批及问题卡、打断后的续用、断线不重发。每项都需保持原 cwd、用户配置和供应商身份，且不能因只读打开聊天而启动进程。接入 SSH 时重新验证选中主机的二进制、配置路径、会话文件与进程归属。未取得合适认证授权和完整控制面证据前，不启用 Claude Code CLI 生产接入。
