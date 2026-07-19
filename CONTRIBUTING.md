# Contributing

## 契约变更流程

1. 修改 `specs/` 或 `schemas/` 中的源定义。
2. 增加或更新 `fixtures/` 中的测试向量。
3. 运行协议 Lint、兼容性 Diff 和 Codegen。
4. 在 PR 中声明变更级别：Patch、Minor 或 Major。
5. 说明受影响的生产者、消费者和迁移顺序。

禁止在实现仓库先引入私有字段，再回填本仓库。

Phase 0 期间可提交目录和规则；实际字段必须在 Phase 1 的独立 PR 中评审。
