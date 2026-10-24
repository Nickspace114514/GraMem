# Context Engine / GraMem 审查修复

2026-10-04，Asia/Singapore。版本：GraMem 2.4.1 / schema 7、控制面板 1.6.1、Context 插件 2.0.1。**代码修复及生产部署均已完成。** 详见部署与线上验收（部署记录，未随仓库发布）。

| 审查问题 | 修复结果 |
| --- | --- |
| P1 面板绕过聊天来源规则 | `/memories` 把聊天状态、策略 epoch、原生可见性以及 `source`/`metadata.source_ids` 纳入 blocked 集合，递归传播到 targets；总数、分页、搜索和历史状态使用同一 SQL 规则。 |
| P1 来源正文清理后无法关联 | `source_turns` 持久保存身份/session/原始 turn/source ID，不保存正文。分块挂到原始 turn，后续预算改变不丢链接。旧档案按确切来源哈希恢复及合并链接，原件/hash 保持不变。多模态原生内容先解码并沿用 provider 的 evidence 规范化。 |
| P2 回填复活 rewind 消息 | 用户、助手及下一轮用户边界统一过滤 `active=1 OR compacted=1`。扫描同步已有档案；任一已归档原生行停用或移除时隐藏整个档案单元。所有投影及来源事实遵守该状态，撤销会使在途分类租约失效。回填任务将停用条目计为受保护完成。 |
| P2 工作集摘要过期 | 编辑/移除证据时清理相关工作集及冻结摘要，保留话题以便短延续重新选择；顺序变化更新 ordinal。旧索引首次升级清理未带版本的工作集。路由和增量分类提交复核证据版本。 |
| P2 provider 回放字段丢失 | 消息深拷贝并沿用 Hermes `without_persistence_fields`，清除内部副本字段；保留 `reasoning_content`、`reasoning_details`、`codex_reasoning_items` 及 provider 扩展。 |
| P2 总预算被忽略 | 完整候选（系统提示、额外摘要、历史及当前工具轮）按宿主估算与 CJK 估算下限核对 `budget_tokens`。超限返回 `None`，由宿主保留原请求，不截断受保护消息。 |

## 验证

- GraMem 全套：225 passed、4 skipped。新增 16 项用例覆盖面板直接/metadata 来源及两层派生、分页/搜索/历史状态、旧来源正文清理、既有档案链接修复、分块/身份隔离、多模态、原生撤销/压缩归档、在途分类及 schema 6 → 7。
- Context：19 项通过，使用服务器当前 Hermes 的实际依赖和基类、临时 home/index、假分类器。新增 6 项测试覆盖证据失效、旧索引升级、provider 字段及深拷贝、元数据过滤、总预算和过期分类结果。
- Ruff：所有改动的 GraMem 源码、面板 API、回归测试及升级验证脚本通过。
- 生产数据的临时副本：schema 6 → 7，67 条已有聊天中 45 条修复来源链接，67 条建立原生状态映射，本次副本没有已撤销档案。原件/hash、事实表、排除规则、原生历史及配置均保持不变，SQLite integrity/foreign key 检查通过。验证使用无模型、无图引擎，未调用真实 provider。

升级副本验证脚本：[verify_review_upgrade.py](../scripts/verify_review_upgrade.py)。只接受含 `.disposable-review-snapshot` 标记的副本目录，输出汇总计数，不输出聊天正文。

## 生效及边界

生产已静默部署上述三个版本，schema 6 → 7 及 45 条来源链接修复完成。67 份原件、事实与排除规则保留，31 个会话与 918 条原生消息逐字段和哈希一致；`smart_context.mode=shadow` 保持不变。本地 Hermes 面板副本同步主仓库，现有未提交的其他工作未清理或覆盖。

已统一更新 GraMem（包含新 `evidence.py`）、面板及 Context，并保存完整相关快照 `<HERMES_HOME>/backups/context-gramem-fixes-20261004T062618Z`。schema 7 为增量建表，旧版 Store 会拒绝版本 7，回滚须在停写窗口同时恢复备份数据库和代码。此次使用独立的统一部署脚本；原有仅部署 GraMem/面板的实例脚本本轮未运行。

历史恢复只关联可以验证确切 source ID 的记录，不按裸正文猜测身份或不同轮次；无法由保留标识和规范证据恢复的旧链接不会凭空建立。原生撤销同步在后台扫描发生时生效，通常间隔一分钟，跨库可见性不保证即时一致。

4 项完整 FalkorDB 路径集成仍需要一次性测试服务，本轮未运行；线上现有图健康及认证 API 已通过。未执行真实模型推理回放、负载测试或生产逐条语义审核。Context 总预算检查是估算保护，不是 provider 的精确账单计数。
