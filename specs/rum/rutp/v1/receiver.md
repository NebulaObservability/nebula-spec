# RUTP v1 Receiver Contract

本文定义 RUTP 接收端的认证、租户/项目绑定和调试 JSON 边界。它不规定
凭据的具体形态；实现可以使用签名 Ingest Key、短期访问令牌或 mTLS，但必须在
读取或路由遥测正文前完成可信认证。

## 认证主体与绑定

接收端必须从已验证的传输凭据解析一个单一的有效绑定：

```text
authenticated principal -> tenant_id + project_id + permissions
```

绑定由服务端控制面维护，至少包含不可用于路由的 `principal_id`、权威
`tenant_id`、权威 `project_id`、权限、过期时间和撤销状态。接收端必须验证
签发方、受众、有效期和撤销状态，并要求 `rum.ingest` 权限。一个请求只能使用
一个绑定；能访问多个项目的主体必须在服务端先选择一个绑定，或使用不同的
项目凭据。

`RumBatch.project_id` 是客户端声明值，不是授权或路由输入。接收端必须：

1. 先认证并解析绑定，再选择配额、隐私策略、加密密钥、存储分区和限流桶。
2. 要求非空 `RumBatch.project_id` 与绑定的 `project_id` 完全相等。
3. 在不匹配时拒绝整个批次，返回机器码 `project_binding_mismatch`；不得静默
   覆盖、接受或按客户端字段重新路由。
4. 只用服务端解析的 `(tenant_id, project_id, batch_id)` 作为幂等键和写入分区。

客户端正文、Resource 属性、查询参数和非认证请求头中的 `tenant_id`、
`project_id` 或同义提示都不得影响上述绑定。接收端可以记录它们用于受限诊断，
但不得把它们传给授权、路由、配额、隐私或存储逻辑。认证或授权失败时不得在
响应中泄露绑定的租户或项目标识。

## 接收顺序与错误

接收端必须在有限的压缩/解压缩大小预算内按以下顺序处理请求：

1. 验证请求方法、精确媒体类型和压缩编码；不得根据正文猜测格式或回退格式。
2. 认证传输凭据并解析有效绑定；缺失或无效凭据为 `401`，缺少
   `rum.ingest` 为 `403`。
3. 应用绑定的请求大小、速率和并发限制，然后解压、解析和验证正文。
4. 比较声明的 `project_id`；不匹配为 `403 project_binding_mismatch`，且不返回
   `BatchAck`。
5. 对通过批次级校验的记录返回 `BatchAck`，使用现有的部分成功语义。

批次级失败不应被伪装成单条记录失败。接收端可使用其平台统一的错误封套，
但错误码必须稳定，且不能包含绑定后的租户、项目或凭据材料。

## 媒体类型

上传地址来自已签名的 `UploadConfig.endpoint`；示例地址为
`POST /rum/v1/batches`。

- 正式传输使用 `Content-Type: application/x-protobuf`，正文为 `RumBatch`，响应为
  `BatchAck` 的 Protobuf 编码。
- 调试 JSON 仅在显式启用时使用媒体类型 `application/json`（唯一允许的参数为
  `charset=utf-8`），
  并要求请求头 `X-Nebula-RUTP-Debug: 1`。接收端必须同时确认该绑定具有
  `rum.ingest.debug`，且该入口已由服务端启用。
- JSON 调试响应使用 `application/json` 和
  `schemas/batch-ack.schema.json`；它不是正式线协议，也不能因 Protobuf 失败而
  自动回退。

`Content-Encoding: gzip` 可以由部署启用，但接收端必须先执行压缩大小和解压后
大小限制。未声明的编码、`text/json`、JSONP、正文嗅探和按客户端握手自动启用
JSON 都不允许。

## JSON 调试前向兼容

`schemas/rum-batch.schema.json` 与 `schemas/batch-ack.schema.json` 是 JSON 调试
投影。v1 接收端必须接受已知必填字段完整的 `1.x` JSON 批次，并按以下规则处理
未来扩展：

- 忽略并丢弃任意对象层级的未知成员；未知成员不得改变认证、绑定、路由、隐私、
  采样或配额决策，也不得被原样持久化或转发。
- 拒绝具有重复成员名的 JSON 对象，避免不同解析器对 `project_id` 或其他安全字段
  采用不一致的“第一个/最后一个”语义。
- 保持已知必填字段、已知枚举和已知 signal 类型的严格校验。未知 signal 类型或
  无法解释的必填语义不得被重解释；接收端必须以稳定的非重试错误拒绝对应记录，
  或在无法安全分帧时拒绝整个批次。
- 只接受兼容矩阵允许的 v1 主版本；未知主版本必须以
  `unsupported_protocol_version` 拒绝，不能尝试降级解析。

这些规则允许新增可选字段，同时不会使客户端控制租户或项目归属。

## 兼容性与迁移

本契约不改变 RUTP v1 的 Protobuf 字段或编码，现有生产者继续发送
`project_id`。接收端升级后，已部署 SDK 的已签名项目配置必须与其 Ingest Key
绑定一致；不一致的旧配置会得到 `project_binding_mismatch`，应刷新配置或轮换到
正确项目凭据。跨语言实现必须运行 `fixtures/receiver/` 和调试 JSON Fixture，
并消费版本化 conformance bundle，而不是复制这些文件。
