# 配置参考

适用于 GraMem 2.5.0 / schema 8（2026-10-14）；字段以 `gramem/config.py` 为准。下表是代码默认值，具体部署可以覆盖。

推荐配置示例：阿里 DashScope 的 Chat/Embedding，qwen3.8-flash、text-embedding-v4 / 1024 维，并设置 embedding_revision。OpenRouter 等其他兼容端点的接法见[迁移记录](openrouter-migration-20261006.md)。

[config-defaults.json](config-defaults.json)由 Config dataclass 生成，包含全部默认字段；默认模型为空，需自行配置。面板模型保存固定官方连接，直接 Config 可配置兼容端点。

文件：`<Hermes profile home>/gramem/config.json`。未知键会报错；未填写字段使用下表默认值。修改后重启该 profile 的 Hermes 实例、管理面板及独立知识 worker，使各进程一致。API 密钥放入 Hermes secrets；独立 CLI 使用同名环境变量。

配置必须是 JSON 对象；布尔开关必须为 true/false，整数不能用布尔值代替，阈值/超时/衰减必须是有限数字。permanent_access_count 为正整数，确认类型为合法小写类型名列表。Owner 与账号别名不能含内部分隔符或 NUL；凭据变量使用合法环境变量名，graph_name 前缀最多 81 字符，为 profile 后缀预留空间。错误时区统一作为配置错误报告。

| 字段 | 默认值 | 含义 |
|---|---|---|
| owner_id | owner | 已核实用户的稳定 ID |
| aliases | {} | transport:account → 稳定用户 ID；email 账号小写 |
| trusted_cli_owner | false | 将本机 CLI 映射到 Owner，须仅用于可信机器 |
| capture_owner_in_groups | false | 将已核实 Owner 的群/频道原话存入私人 Owner 记忆；不开放群中的私人召回，生产已启用 |
| chat_auto_archive | true | 自动归档主用户聊天，补齐可信私人历史并整理摘要；关闭停止新增，不删除已有档案 |
| knowledge_auto_archive | true | 自动保存已授权且绑定 Owner 的真实渠道附件；群采集仍受 capture_owner_in_groups 控制 |
| knowledge_ocr_languages | chi_sim+eng | Tesseract 语言组合；繁体可用 chi_tra+eng，须已安装对应语言包 |
| timezone | UTC | 来源时间及相对日期解析时区；生产为 Asia/Singapore |
| model | 空 | 提取/控制分类/画像模型；空时无法自动提取 |
| base_url | https://dashscope.aliyuncs.com/compatible-mode/v1 | OpenAI-compatible Chat Completions 与 embeddings 地址；按实际账号端点配置 |
| api_key_env | DASHSCOPE_API_KEY | 密钥变量名 |
| provider_preference | price | OpenRouter 文本路由：price / throughput，其他供应商不发送该参数 |
| embedding_provider_preference | throughput | OpenRouter 向量路由：price / throughput；向量召回影响前台回复 |
| embedding_model | 空 | 空表示全文检索；填写后启用远程语义检索 |
| embedding_dimensions | 0 | 非零则要求返回维度匹配 |
| embedding_revision | 1 | 向量空间版本，换模型/向量语义时修改，旧空间不会混算 |
| timeout | 30 | 单次 HTTP 请求秒数，范围 >0 且 ≤120 |
| graph_url | redis://127.0.0.1:6380/0 | 独立 FalkorDB 的 Redis 协议地址 |
| graph_name | gramem | 图前缀；实际附加 profile home 的 SHA256 前 12 位 |
| graph_password_env | GRAMEM_GRAPH_PASSWORD | 图密码变量名 |
| recall_tokens | 1024 | 自动注入与有界工具输出预算，正整数 |
| always_limit | 3 | Always 最大条数 |
| relevant_limit | 8 | Relevant 最大条数 |
| historical_limit | 4 | Historical 最大条数 |
| graph_recall_enabled | true | 自动按问句提及的实体补充关系图来源事实；不额外调用提取模型 |
| graph_recall_hops | 2 | 自动展开 1–3 跳，入边和出边均可遍历 |
| graph_recall_limit | 3 | 自动图补充最多事实条数，范围 1–10 |
| graph_recall_tokens | 256 | 图补充事实与关系的 token 子预算，范围 1–4096；包含在 recall_tokens 总预算内 |
| extraction_input_tokens | 4000 | 单任务证据预算；长消息拆分持久任务，逐块处理 |
| extraction_tokens | 1800 | 模型生成预算 |
| max_items | 5 | 每次提取最多接受条数 |
| min_confidence | 0.7 | 自动提取置信门槛 |
| min_future_use | 0.6 | 未来价值门槛 |
| min_stability | 0.55 | 稳定性门槛 |
| activate_threshold | 0.55 | 长期事实自动激活的重要性门槛 |
| temporary_activate_threshold | 0.35 | 传统确认模式下高置信临时情境的激活门槛；自动提取由 LLM 最终批准 |
| review_threshold | 0.35 | 低于此重要性的自动候选拒绝 |
| archive_threshold | 0.1 | 强度低于此值归档，不普通召回 |
| permanent_threshold | 0.85 | 永久生命周期强度门槛 |
| permanent_access_count | 20 | 达到永久还需的交付次数 |
| reinforcement | 0.02 | 每次实际交付强化值；同轮重试不重复 |
| auto_approve | true | LLM 自动审批；新提取和合并一次调用直接批准，现有/导入候选由持久后台审核，无人工批准要求 |
| confirmation_types | identity, occupation, current_location, health | 仅 auto_approve=false 的传统模式要求人工确认这些类型 |
| decay_rates | 见下表 | 按类每日指数衰减系数，非负 |

| class | identity | preference | skill | project | relationship | episodic | knowledge | temporary |
|---|---|---|---|---|---|---|---|---|
| 系数 | .001 | .003 | .005 | .01 | .003 | .03 | .01 | .2 |

自动提取的事件/临时情境不要求长期稳定性；临时情境置信须 ≥0.8，普通长期事实仍使用稳定性和未来价值门槛。

强度 `importance × confidence`，随后乘 `exp(-rate × days)`；permanent 不衰减。重要性 = .3 future_use + .3 stability + .2 personalization + .2 uniqueness。召回评分 = .4 similarity + .25 strength + .15 importance + .1 confidence + .1 recency。时间、新旧版本、排除状态先过滤，再评分。

自动图召回把自然问句中的实体名称作为起点（完整名称匹配，不做自动别名合并），从邻近关系中补充来源事实。图提供的相关度下限为 `.65 / 路径跳数`；图补充与全文/向量命中的事实按 ID 去重、统一评分，共享总预算，实际交付后才强化。只通过图找到的事实标记 tier=graph；历史事实仍标记 historical。图查询失败时保留普通召回，并在同一引擎内暂停自动图请求 30 秒，手动图查询可立即重试。

可用类型包括 identity/occupation、preference/interests、skill/capability/technical_environment、relationship、project/active_project/project_goal/project_stage/project_state/decision/project_question/project_next_step/project_risk/constraint、current_location/current_activity/current_goal/current_constraint/current_status、episodic、knowledge。未知合法小写类型按 knowledge 类衰减；project_ 前缀按 project，current_ 按 temporary。

身份不可从显示名、邮件正文或模型判断绑定。未核实平台账号进入独立 Contact，群独立 Group；CLI 信任开关不影响 Email/Teams。每个 Hermes profile 应有各自配置；移动 home 会改变图 namespace，需要显式迁移。

聊天记录、来源事实与记忆网还复核策略 epoch 和原生撤销状态；这些是固定有效性检查，没有关闭开关。Context 的 `smart_context` 位于 Hermes 配置中，不属于本 Config。
