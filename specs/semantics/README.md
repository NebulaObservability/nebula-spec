# Semantic Registry

此处维护 `attributes.yaml`、`events.yaml`、`metrics.yaml`、`spans.yaml` 和 `enums.yaml`，并生成各语言的属性常量和类型。自定义跨产品 RUM 字段使用 `rum.*`；单一厂商实现字段必须使用厂商命名空间，不能进入本注册表。

## Issue 分组规则（v1）

`rum.issue.fingerprint` 是错误事件分组的规范指纹：对以下换行分隔的 ASCII 字段
序列取 SHA-256（小写十六进制）：

1. 字面量 `rum-issue-fingerprint-v1`
2. 错误类型（`exception.type`，缺省取 `error.type`）
3. 顶帧：第一个 `in_app` 帧的 `function|filename`；无栈帧取空串
4. 发行版：资源属性 `service.version`，缺省取空串

服务端（Backend）计算该指纹并作为 Issue 的权威分组键；客户端的
`rum.error.fingerprint` 仅是分组提示，不参与计算。

## Issue 告警规则（v1）

告警规则在 Issue 聚合之上评估，规则类型为封闭集合：

1. `new_issue`：Issue 首次出现时即时告警一次，同一 Issue 生命周期内不重复。
2. `error_rate`：Issue 在滚动窗口（`error_rate_window`）内累计的错误事件达到阈值时告警。
3. `test`：操作者触发的测试通知，记录触发者身份。

每个（规则, Issue）对在告警后进入静默窗口（`silence_window`），窗口内的重复匹配被抑制；`new_issue` 的静默即 Issue 生命周期本身。抑制键 `dedup_key` 由规则类型、规则 ID 与主体（Issue，测试通知为项目）派生，客户端不可构造或覆盖。

投递可靠性上限（v1）：每个（firing, 通道）恰好一次投递尝试，带超时；不重试、不持久化队列、不跨重启保证。失败的尝试连同错误原因记录在告警历史中（上限 200 条），由 `GET /api/v1/alerts` 可查。通知载荷契约见 `schemas/alert.schema.json`。
