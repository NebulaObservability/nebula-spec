# Golden Fixtures

跨语言实现必须消费同一批输入输出用例。`manifest.yaml` 中的协议、ACK、配置、Receiver 和 Control Plane Fixture 由 JSON Schema 自动验证；Session、Privacy 和 Trace 关联 Fixture 供 SDK、Agent、Collector 与 Backend 执行行为一致性测试。

消费方应使用 `generated/conformance/` 中的版本化 bundle，而不是复制本目录。`receiver/` 覆盖认证主体绑定、项目声明不匹配和 JSON 调试授权；其中的 `authenticated_principal` 是测试工具注入的已认证上下文，绝不是客户端正文格式。
执行前读取 `fixture-manifest.json` 并验证每个 Fixture 的 SHA-256。Bundle 的
版本必须与所依赖的 semantic registry 版本一致。

`minimal-batch-with-unknown-members.json` 故意使用兼容矩阵允许的未来 v1 wire
version，并保留未来的 `schema_url` 和未知成员，用于防止接收端把兼容范围错误
收紧为当前精确版本。
`invalid-batch-missing-session.json` 同样使用当前 wire version，使失败原因只来自
缺失的必填上下文；`invalid-batch-unsupported-major.json` 则故意保留 `2.0`，用于
验证不受支持的 Major 必须被拒绝。

`control-plane/` 同时覆盖服务端不可变修订、回滚到更高 revision，以及 SDK 投递
封套不携带客户端可控的 tenant/project scope。远程配置必须继续使用默认拒绝的
隐私策略，相关反例用于阻止配置升级为 `allow`。

## APM Metrics

`metrics/apm-metrics-mvp.json` 是包含完整 APM Resource、12 项受支持指标、累计
Histogram/Sum、Gauge 和 HTTP/JDBC Exemplar 的标准 OTLP Golden Fixture。Collector、
Backend、Agent 与 Dashboard 必须从版本化 conformance bundle 消费该 Fixture。
