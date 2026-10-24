# 原记忆设计保留依据

以下为重构前 ARCHITECTURE.md 的记忆引擎设计；新实现及差异见新架构文档。

### 记忆引擎

记忆范围：

```text
OWNER    仅 Owner 私聊可检索
CONTACT  仅对应联系人私聊可检索
GROUP    仅对应群组会话可检索
```

群组记忆采用默认拒绝策略：

```text
群消息默认不自动提升为长期记忆
只有 Owner 显式创建的 project / decision / constraint 类共享事实可进入群记忆
创建时必须确认不包含个人资料，并写入 group_safe=true
上下文仅注入 group_safe=true 的同群记忆
旧群记忆和群会话摘要默认不再注入后续群聊
```

自动记忆流程：

```text
用户消息 + agent 最终回复
  -> Mneme Extractor（native；LangMem 可选）
  -> 四维重要性 future_use / stability / personalization / uniqueness
  -> Importance = 0.3 / 0.3 / 0.2 / 0.2 加权
  -> Conflict Detector（同范围、相关记忆）
  -> ADD / UPDATE / MERGE / SUPERSEDE / IGNORE / FORGET
  -> 高风险或中等重要性进入 REVIEW / AWAITING_CONFIRM
  -> Owner 确认后 ACTIVE
  -> PostgreSQL MemoryDecision + MemoryLifecycleEvent 审计
  -> FalkorDB 派生图；Graphiti 可选投影
```

记忆类与生命周期是两个独立维度：

```text
Memory class:
identity / preference / skill / project / relationship / episodic / knowledge / temporary

Lifecycle:
candidate / review / awaiting_confirm / active / reinforced / decaying / permanent / archived
```

`memory_items.status` 保留数据库工作流兼容状态；`lifecycle` 表达记忆实体的长期生命阶段。
所有状态、强度和版本变化写入 `memory_lifecycle_events`，不会物理删除历史记忆。

初始强度：

```text
strength = importance * confidence
```

每日按类型衰减：

```text
effective_strength = strength * exp(-decay_rate * days)
identity 0.001    preference 0.003    skill 0.005
project 0.01      episodic 0.03       temporary 0.2
```

低于 `archive_threshold` 时转为 `ARCHIVED`，但不删除。高强度且达到配置的访问次数后转为
`PERMANENT`。实际注入上下文的活动记忆每次强化 `0.02`；候选集、Webhook 重试和历史记忆不强化。

召回分三层：

```text
Always       identity / preference / skill / relationship 的高强度活动记忆
Relevant     每轮全文 + pgvector 候选，综合评分后取 Top K
Historical   仅用户明确询问过去时读取 superseded / archived
```

Relevant 评分：

```text
0.40 * similarity
+ 0.25 * effective_strength
+ 0.15 * importance
+ 0.10 * confidence
+ 0.10 * recency
```

Historical 层沿用全文和向量相关性候选，不能仅按归档时间返回旧事实。所有检索都按
`owner_id + scope + conversation/person` 过滤。画像在注入前会校验所有 `source_memory_ids` 仍为活动
记忆；任一来源被替代、遗忘或归档时，当前画像和受影响快照立即红化，避免失效事实绕过记忆状态。

每周从已确认稳定记忆生成 `user_profiles`，每个版本另存 `user_profile_snapshots`，并保留
`source_memory_ids`。画像是物化摘要，不是新的事实源。

Owner 私聊还会每轮构建一个最多 4,000 字符的连续性摘要，独立于关键词召回：

```text
active_project
  -> 同 project_key 的 project_goal / project_stage / decision
  -> project_question / project_next_step / project_risk
  -> 最新 current_location / current_activity / current_goal / current_constraint / current_status
  -> continuity packet
```

`continuity packet` 只在 Owner 私聊查询和注入。联系人私聊与群聊在读取数据库前即返回空值。
项目 key 由 Worker 归一化；新的 `active_project` 会替换旧活动项目，但旧项目状态仍保留在
PostgreSQL，用户明确恢复该项目后可再次成为活动项目。只保存用户明确陈述或确认的目标、
决定和状态，不保存原始专家输出。

显式 Owner 记忆由 `/remember` 直接创建为 `ACTIVE`。用户可使用：

```text
/remember
/memories
/forget
/link_identity
```

