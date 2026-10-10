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