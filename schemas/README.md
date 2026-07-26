# Schemas

此处发布调试 JSON Batch、ACK、配置、语义、隐私策略、控制面配置和 Release Manifest 校验规则。正式 RUTP 遥测传输仍以 Protobuf 为准。

RUTP JSON Batch 与 ACK 是容忍未知对象成员的调试投影：接收端必须丢弃未知成员，拒绝重复成员名，并保持已知必填字段和枚举的严格验证。认证、tenant/project 路由和隐私策略只能来自服务端解析的认证主体绑定，不能来自 JSON 字段。完整规则见 [`specs/rum/rutp/v1/receiver.md`](../specs/rum/rutp/v1/receiver.md)。

`control-plane-config-revision.schema.json` 是服务端保存的不可变修订记录，包含
仅供服务器使用的 scope、生命周期和审计元数据。
`control-plane-config-delivery.schema.json` 是 SDK 可接收的 active 配置封套，故意
不包含 tenant、project、principal 或审计字段，并内嵌受现有
`rum-config.schema.json` 约束的配置文档。完整边界见
[`specs/control-plane/v1/README.md`](../specs/control-plane/v1/README.md)。
