# Compatibility

`protocol-matrix.yaml` 和 `otel-schema-matrix.yaml` 固定协议与 OTel 兼容范围，`baselines/` 保存已发布语义快照和 RUTP Buf 描述符。兼容性报告是协议 PR 的必需检查。

快照用于发现字段/事件删除、字段类型或隐私分类变化、字段升级为必填和枚举值删除。仅新增可选字段、事件或枚举值属于兼容变更。

`rutp-v1.binpb` 用于检测 Proto 字段删除、字段号/类型变化和其他文件级不兼容。只有发布新的 Major 协议基线时才能替换。
