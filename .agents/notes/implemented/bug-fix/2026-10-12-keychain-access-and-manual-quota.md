# Agent Note: Claude 额度只在明确请求时查询

Status: implemented

## Problem

Claude 账号面板打开及可见时的五分钟刷新会逐个请求 `details`。旧后端在额度缓存过期后自动解密 Cookie，macOS 上因此读取 Claude Safe Storage；用户没有点击额度按钮也可能遇到钥匙串授权。旧失败结果还会用失败发生时间覆盖上次成功查询时间。

## Decision

Claude 的面板打开、返回、切换后的列表刷新及定时刷新只请求账号公开快照。Claude `details(refresh=False)` 也只返回快照，作为服务端边界；仅明确的 `details(refresh=True)` 查询额度。DeepSeek Harness 和 Codex 的既有刷新行为不变。

成功解析出可识别额度后才替换快照并保存 `checkedAt`；失败保留已有成功额度及其 `checkedAt`，将状态与脱敏错误改为失败。没有成功快照时不写入成功查询时间。界面以本地 `YYYY-MM-DD HH:mm` 显示 Claude 的成功查询时间，并把失败与旧数据同时显示。查询期间按钮显示“查询中”并禁用，同一面板不重复提交。每次明确查询仅在该调用的局部字典内复用 Claude Safe Storage 派生密钥；调用结束后不保留进程级明文密钥缓存。

## Existing-note audit

已按 Claude、quota、额度、keychain、钥匙串检索活跃 `.agents/notes/`。现有笔记涉及客户端列表刷新、列表状态和其他功能，与账号额度查询无重叠。已批准的同名提案存于本地忽略目录 `.local/reviews/`，其交互选择和边界在此实施；不将本地评审材料提交。

## Alternatives considered

保留五分钟自动额度查询并只合并钥匙串读取，可以减少单次授权次数且保持数据较新；它仍会在用户未主动查看额度时访问受保护项，不符合手动查询选择。延长缓存时间同样只会延迟自动访问。

## Consequences

Claude 快照可能较旧，界面始终展示原成功查询时间。模拟回归覆盖被动路径不解密、不联网、显式查询、失败保留及双语状态。此改动只处理账号额度这条访问路径；连接凭据、客户端自身访问钥匙串、应用签名及跨版本授权仍需按实际弹窗来源分别验证。
