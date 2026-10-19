# Agent Note: Claude Desktop 退出只依据桌面任务清单

Status: implemented

## Problem

macOS 正常退出 Claude Desktop 的任务核验读取合并聊天列表。该列表还包含本机和 SSH Claude Code 历史；远端刷新期间 `complete` 为假，即使 Desktop 的 Code 和 Cowork 已完整返回且全部空闲，也会报“无法确认客户端所有任务均已结束”。独立的桌面退出预览同样使用合并列表，因此可能错误要求未知任务确认。

## Decision

Claude Desktop 正常启停、账号切换前的空闲核验，以及独立退出预览和确认，直接读取现有 `desktop_listing()` 的新鲜 Code/Cowork 清单。清单必须完整，且每条桌面会话都提供可核验的运行状态并处于空闲；进行中的任务或权限确认继续阻止退出。网关持有的本机或 SSH Claude Code 活跃任务仍由现有 `busy()` 检查阻止退出。原生进程身份快照及退出前复核保持不变。Windows 显式正常退出的限时原生确认路径继续使用原有读取和确认流程。

## Existing-note audit

已检索活跃笔记。[Claude 合并聊天列表](../optimization/2026-10-14-claude-unified-chat-list.md)决定展示合并列表，不要求用合并结果判断 Desktop 的退出安全；[客户端状态读取](2026-10-14-client-status-startup.md)约束展示缓存不可用于写操作，本次仍使用新鲜读取。这两篇无需改动。

## Alternatives considered

仅忽略合并列表的 `complete` 可以绕过远端刷新，但也会掩盖 Desktop 自身缺失 Code/Cowork 覆盖或未知运行状态。等待 SSH 刷新结束仍会让与 Desktop 进程无关的远端状态决定退出，且离线主机会一直阻塞。

## Consequences

SSH 历史或远端刷新不再造成 Desktop 的假未知状态。Desktop 连接中断、覆盖不完整、会话运行状态未知及实际活跃任务仍保留原有阻拦或显式未知确认。回归测试在守卫入口复现旧错误，并覆盖普通退出、独立预览与二次确认、桌面任务和权限等待、以及已接管 CLI 活跃任务。Mac 已安装 Test 使用正常退出入口关闭闲置 Claude，随后单独冷启动初始化成功；正式网关及当前 Codex 宿主进程保持不变。组合恢复多个客户端时有一次初始化被焦点保护中止，记录保留；恢复连接后，单独退出重开复测通过。
