# Nebula Specification

Nebula Observability 协议、语义、隐私规则和跨语言一致性测试的唯一事实来源。

## 范围

- APM 和 RUM 协议定义。
- OpenTelemetry Semantic Conventions 映射。
- 属性、事件、指标和枚举注册表。
- 隐私分类及默认策略。
- 兼容性矩阵、Golden Fixtures 和 Release Manifest。
- TypeScript、Java、Go、Rust 等语言的生成代码。

本仓库不实现 Agent、SDK、Collector、Backend 或 Dashboard 业务逻辑。

## 目录

```text
specs/          协议和语义源文件
schemas/        可独立校验的 JSON Schema
compatibility/  协议及 OTel 版本兼容矩阵
fixtures/       跨语言一致性测试数据
generated/      Codegen 生成物
releases/       平台 Release Manifest
tools/          Lint、Diff 和生成工具
```

当前为 Phase 0 目录基线。Phase 1 将提交首批 Proto、Semantic YAML、JSON Schema、Codegen 和 Fixture。

## 版本

当前仓库版本见 [`VERSION`](VERSION)。版本和兼容规则见 [`VERSIONING.md`](VERSIONING.md)。
