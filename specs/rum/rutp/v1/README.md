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
