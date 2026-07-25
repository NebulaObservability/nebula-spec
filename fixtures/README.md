# Golden Fixtures

跨语言实现必须消费同一批输入输出用例。`manifest.yaml` 中的协议、ACK 和配置 Fixture 由 JSON Schema 自动验证；Session、Privacy 和 Trace 关联 Fixture 供 SDK、Agent、Collector 与 Backend 执行行为一致性测试。

消费方应使用 `generated/conformance/` 中的版本化 bundle，而不是复制本目录。
执行前读取 `fixture-manifest.json` 并验证每个 Fixture 的 SHA-256。Bundle 的
版本必须与所依赖的 semantic registry 版本一致。
