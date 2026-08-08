# Release Manifests

每个 YAML 文件描述一次平台发行版的兼容组件组合。`CURRENT` 指向用于生成制品和 conformance bundle 的当前草案；已发布的历史 Manifest 必须保留，不能就地改写。

## Platform Manifest v2

`schema_version: 2` 将可运行 MVP 的组件身份冻结为结构化记录。每个实现组件必须声明完整源码 revision、不可变发布包或 OCI digest，以及它实际消费的 Spec Release 和依赖方式。Go Agent、RUM Web SDK、Collector、RUTP ingress、Backend 与 Dashboard 是完整集合；Collector 与 RUTP ingress 必须来自同一源码 revision 并作为双镜像组合审计。

平台允许经验证的混合 Spec 组合。Manifest 必须记录真实的逐组件依赖，不能为了形成一个全局版本而改写组件事实。`direct` 表示源码直接锁定 Spec，`transitive` 表示通过冻结的组件版本消费，`vendored` 表示构建输入已将依赖制品纳入仓库。`evidence` 是相对于组件源码 revision 的审计路径。

发布工作流把 `CURRENT` 指向的 YAML 复制为 `platform-release-manifest-<VERSION>.yaml` Release asset，并纳入 `SHA256SUMS`。历史 v1 Manifest 继续由同一 Schema 验证，但不得补写或改写已发布身份。

## APM Metrics

Metrics 发布在 `protocols.apm_metrics` 中声明独立 contract 版本，并与
`protocols.apm_extension`、`otel_schema` 和 `components.spec` 一起固定。RUTP 与 Control
Plane 版本不会因 APM Metrics profile 发布而隐式变化。

## APM Agent

Go Agent 契约分别通过 `protocols.apm_agent`、`protocols.apm_agent_config` 和
`protocols.apm_agent_diagnostics` 固定，并与当前 APM extension、Metrics 和 Spec 版本一起
发布。Spec Release 只声明协议和可消费制品；在 Agent 仓库的对应 Go module tag 实际发布前，
历史 v1 Manifest 的 `components.apm_agent_go` 必须保持 `null`，不得提前宣称实现已交付。v2
平台 Manifest 只能冻结已经存在的 Go module tag、完整源码 revision 和它实际消费的 Spec Release。
