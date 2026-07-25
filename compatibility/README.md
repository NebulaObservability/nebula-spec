# Compatibility

`protocol-matrix.yaml` 和 `otel-schema-matrix.yaml` 固定协议与 OTel 兼容范围，`baselines/` 保存已发布语义快照和 RUTP Buf 描述符。兼容性报告是协议 PR 的必需检查。

快照用于发现字段/事件删除、字段类型或隐私分类变化、字段升级为必填和枚举值删除。仅新增可选字段、事件或枚举值属于兼容变更。

`rutp-v1.binpb` 用于检测 Proto 字段删除、字段号/类型变化和其他文件级不兼容。只有发布新的 Major 协议基线时才能替换。

RUTP Receiver 的认证主体绑定和 JSON 调试规则属于版本化运行时契约，不改变 v1 Protobuf 编码。`protocol-matrix.yaml` 固定其路由来源和未知 JSON 成员处理；对应的正反向用例位于 `fixtures/receiver/`。
