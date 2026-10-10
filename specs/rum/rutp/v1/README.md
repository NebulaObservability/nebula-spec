# RUTP v1

RUTP v1 包含：

- `common.proto`：属性值、Resource、Scope 和附件引用。
- `context.proto`：Trace、Session、Document、View、Action 上下文。
- `record.proto`：Span、Event、Metric、Diagnostic 统一记录。
- `batch.proto`：上传批次、客户端时钟、诊断和部分成功 ACK。
- `receiver.md`：认证主体到 tenant/project 的权威绑定及 JSON 调试接收边界。
- `config.proto`：能力协商、签名配置和 Kill Switch。
- `replay.proto`：Replay 索引与 Chunk 引用。

Replay 只定义兼容边界，首期产品不实现采集或播放。正式传输使用 Protobuf；`schemas/rum-batch.schema.json` 仅描述调试 JSON 格式。接收端必须从认证主体而不是客户端 `project_id` 推导 tenant/project，详见 [`receiver.md`](receiver.md)。
Go Collector 和 Backend 必须消费版本固定的
`github.com/NebulaObservability/nebula-spec/generated/go` module 中的
`rum/rutp/v1` 包，不得手写消息类型或将调试 JSON 作为正式线协议。

## 兼容性说明

### 1.0.0-draft.1 增补：结构化错误深度

向后兼容的可选字段新增（Minor 语义；draft 版本不承诺稳定性，本增补继续由
`1.0.0-draft.1` 载体发布，采用它的组件被后续平台 Manifest 冻结时再声明版本推进）：

- `RumEvent.stack`（`ErrorStack`）：结构化异常堆栈，镜像 `exception.*` 语义——
  `type` ↔ `exception.type`、`value` ↔ `exception.message`、`frames` ↔ 解析后的
  `exception.stacktrace`。帧数在 JSON 边界最多 64，帧内 `filename` 最长 1024。
- `RumEvent.breadcrumbs`（`repeated Breadcrumb`）：事件前的有序行为轨迹，最多 32 条，
  `category` 在 JSON 边界为封闭集合（`navigation`、`http`、`ui`、`error`、`custom`），
  线上以字符串承载以便前向兼容。

约束与隐私：

- 两个字段均可缺省；不能填充的生产者继续发送 `exception.*` 语义属性即可，
  接收端必须同时接受两种表示。
- `stack.value` 与 `breadcrumbs[].message` 的内容按 `exception.message` 同级处理，
  `stack.frames[].filename` 按 `url.full` 同级处理（脱敏由隐私策略强制，
  见 `specs/privacy/default-policy.yaml` 的分类语义）。
- 有界性是协议义务：超出帧数/条数上限的批次在 JSON 边界被拒绝
  （见 `fixtures/protocol/invalid-error-stack-frames.json`）。
