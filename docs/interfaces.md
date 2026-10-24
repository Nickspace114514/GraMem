# 接口使用手册

适用于 GraMem 2.5.0 / SQLite schema 8 / 面板 1.8.1，核对日期 2026-10-14；Hermes 提供五个工具。所有数据接口都限定当前 principal（Owner / Contact / Group）和 Hermes profile，不接受模型传入任意用户 ID。引擎不提供独立 HTTP 或 MCP 服务；Hermes 使用原生 MemoryProvider，管理脚本使用 CLI 或 Python。附属管理面板的认证 REST 接口见 [面板接口手册](control-panel.md)。

## 接口边界

模型工具返回 JSON 字符串、身份由宿主决定；CLI/Python 属可信本机管理边界；REST 属宿主管理员认证边界。三者的输出预算、分页及授权方式不同。

| 入口 | 主源码 | 契约 |
|---|---|---|
| 五个模型工具与回调 | `gramem/hermes.py` | 真实当前作者、profile 与 principal；禁止任意身份参数 |
| CLI | `gramem/cli.py` | `--home` 必填；除 status 外须 trusted_cli_owner |
| Python | `gramem/engine.py`、`knowledge.py`、`chats.py`、`chat_backfill.py`、`network.py` | 调用方验证 Principal；对象本身不提供网络认证 |
| 管理 REST | `integrations/control-panel/dashboard/api.py` | `/api/plugins/hermes-control`；[完整路由](control-panel.md) |

## Hermes 自动流程

初始化读取 `<hermes-home>/gramem/config.json`，事实保存在同目录 `memory.sqlite`。每轮先识别真实遗忘要求，再按当前问题召回。已完成用户轮次的原话进入持久任务；助手回复不作为事实证据。自动提取包含事实、冲突判断和关系，一次调用完成。默认开启 auto_approve，所有提取事实（含身份/当前位置）由同一次 LLM 调用最终审核并激活；现有及导入候选由后台自动审核，通过前不注入。

寒暄、空消息、重复轮次、机器人和非主代理不自动写入。群消息默认不写共享记忆；开启 capture_owner_in_groups 后，仅已核实 Owner 的原话写入私人 Owner 记忆，其他参与者、缺失作者和机器人仍不采集。群共享事实由已核实 Owner 显式保存。后台每日维护生命周期，按身份每周整理同槽位事实并生成有来源的画像；失败一小时后重试，新身份不会被空库的旧周调度延迟；压缩前保存证据 checkpoint。重新启动可以继续未完成任务。

压缩交接按本会话 `on_turn_start` 已核实的作者逐条分组，不把整段历史归给当前作者。未核实的历史消息、机器人消息及相同文本对应多个作者的歧义消息跳过；已完成轮次仍通过 sync_turn 的持久队列保存。切换会话会清空临时作者映射。

## Hermes 工具：gramem_recall

参数：`query` 必填字符串；`historical` 默认 false；`graph` 默认 false；`hops` 默认 1，范围 1–3，仅用于图查询。

```json
{"query":"GraMem 的架构决策是什么"}
```

普通召回返回 `{"context":"...","tokens":123}`。context 内每条事实包含 id/type/fact；历史版本增加 historical/valid_from/valid_until。tokens 是 cl100k_base 估算。没有匹配返回空 context 和 0 tokens。

默认自动调用关系图补充问句中明确提到的实体及其两跳邻近事实。图补充包含有来源的 relations（subject/predicate/object），与普通事实共用 1024 token 总预算，默认子预算 256 tokens、最多 3 条补充事实。候选、过期、已忘记、停用及经过无效来源的路径不交付。不会把间接连接自动推断为新事实；graph_recall_enabled=false 可恢复仅全文/向量召回。

```json
{"query":"GraMem","graph":true,"hops":2,"historical":true}
```

图查询返回 `{"items":[...],"truncated":false}`。每条关系包含 id、memory_id、subject、predicate、object、valid_from、valid_until、path_ids、distance；时间为 Unix 秒字符串，空 valid_until 表示图中尚未失效。查询可从关系两端进入，subject/object 始终保持原关系方向；distance 是有界候选中采用的最短有效路径跳数。path_ids 是遍历路径的来源记忆，返回前逐一校验；同一关系经不同路径出现时只返回一次，先校验后去重，可选择有效的绕行路径。每次最多读取 800 条路径候选，密集图可能仍有未展示的有效路径，不是全图穷举。历史图允许 superseded/archived 来源，不能绕过忘记或停用。图故障返回空集合；空结果不能单独证明图服务健康。

## Hermes 工具：gramem_memory

`action` 必填。其余可用字段：id、content、evidence、type、slot、targets（ID 数组）、group_safe（默认 false）。未知字段不允许。模型工具返回 JSON 字符串；错误统一为 `{"error":"invalid_or_unauthorized_memory_operation"}`，未初始化为 memory_not_initialized；模型请求失败为 memory_processing_unavailable。

forget/suppress/reactivate/reauthorize/confirm/reject 自动核对当前用户的语义意图及目标，明确请求直接执行，不要求固定关键词或额外确认。evidence 如提供，必须来自当前原话；同轮已核实的遗忘/停用判断可复用。最近同身份上下文仅用于解析“那条”等指代，旧请求不能授权新的无关轮次。普通事实纠正、引用、翻译和假设不授权删除。真实请求范围含糊时返回 `{"error":"memory_control_scope_unclear","clarification_required":true}`；模型不可用时保留原记录并返回 memory_processing_unavailable。

| action | 必要参数 | 行为与返回 |
|---|---|---|
| remember | content | 保存明确事实；可设 type/slot。返回 id |
| update | content, targets | 替换具体旧 ID，旧版本进入历史；可设 type/slot。返回新 id |
| merge | content, targets | 合并同 scope 的兼容事实，保留派生来源；返回新 id |
| list | 无 | active 与 candidate 列表，items/truncated；每项 id/type/slot/fact/status |
| confirm | id | 激活候选，返回 success:true |
| reject | id | 拒绝候选，返回 success:true |
| forget | slot 或 id | 删除该槽位所有版本及派生内容，建立 deleted 排除 |
| suppress | slot 或 id | 临时禁止使用和写入该槽位；保留值 |
| reactivate | slot | 解除 suppressed；不能解除 deleted |
| reauthorize | slot | 当前用户必须明确说“重新记住”等；只允许新事实，旧值不恢复 |
| profile | 无 | 来源约束的画像 items/truncated |
| reflect | 无 | 立即生成画像并返回 items/truncated；有模型调用成本 |
| status | 无 | 当前读取身份 exclusions、active_count，capture_scope、processor_available、采集身份的 jobs（counts/recent）；不展示其他身份事实 |

remember/update/merge：content 为 1–2000 个字符，不接受检测到的密钥；type 默认为 knowledge，必须是小写类型名；slot 最长 200 字符。update/merge 的 targets 必须存在、同 scope、仍 active；remember 不接受 targets。省略 slot 时，单例类型使用类型名，其他内容使用类型与内容哈希生成槽位。evidence 可提供当前用户原话的准确片段；省略时使用当前用户消息。纯原文事实可直接保存，改写/归纳的内容需模型验证支持关系；不能无证据写入助手猜测。需要精确更新/遗忘时建议显式设稳定的语义槽位，并把项目名放入槽位，避免跨项目混用。

```json
{"action":"remember","content":"GraMem 的关系图使用独立 FalkorDB","type":"project","slot":"project.gramem.graph_database"}
```

```json
{"action":"update","content":"当前数据库配置的新值","type":"project","slot":"project.gramem.database","targets":["此前查询返回的真实ID"]}
```

```json
{"action":"forget","slot":"project.gramem.database"}
```

forget/suppress 返回 state、slot、live_records_redacted、physical_erasure_complete:false、external_history_erased:false、graph_erasure_pending、document_sources_erased。文档分块共用重叠原文，遗忘其中任一分块时以整份文档来源为清除范围：所有同来源分块、绑定事实及其派生内容一起失效；其他文档和身份不受影响。document_sources_erased 为清除的文档来源数量，普通事实为 0。图删除通过持久队列完成；当前召回立即阻断。reactivate/reauthorize 返回 allows_new_memory:true、restored_old_values:false；suppressed 原记录仍存在，解除后可再次使用。

list/profile/reflect/graph 受召回预算限制，truncated:true 表示有未展示条目；当前接口没有分页游标，完整审计可使用 Python Engine.list 按状态读取（最多 200 条）或本机 SQLite 管理。status 是当前身份的轻量摘要。

开启私人采集后，Owner 在群中的 remember/update/merge/confirm/forget 等默认操作私人 Owner 记忆；返回写入结果，群中的 list/profile/recall 不开放私人事实。要操作共享槽位，传 group_safe:true。群共享工具只允许 Owner 显式提交 `group_safe:true` 的 project/project_state/decision/constraint；其他成员不能变更、读取画像或触发反思。群记忆不包含 Owner 私人记忆。机器人和子代理只允许只读操作。

## Hermes 工具：gramem_knowledge

字段：action 必填；query、id、path、title、description、start（零起始）、page（一起始）、historical 可选，未知字段禁止。所有动作使用当前 principal；群不读私人原件。

| action | 需要字段 | 返回/行为 |
|---|---|---|
| search | query | items、来源引用，受工具预算限制 |
| list | 可选 query/page/historical | items/total/page/size；每页最多 10，再受预算限制 |
| get | id | 文件信息与最多 20 个 locations |
| read | id，可选 start | document、单个来源分块、next；继续按 next 读取 |
| import | path，可选 title/description | 当前用户须明确请求该确切路径长期导入，模型核验并执行原生文件保护；defer 入队 |
| export | id | 私有 cache/documents/knowledge-UUID 内的新路径和 hash，供后续工具使用，不自动发送 |
| retry | id | 失败/缺组件/空解析的文件重试 |
| forget/suppress/reactivate | id | 核对当前控制意图，操作 document:ID 槽位 |

import/export/retry/控制要求主代理、非机器人和私人用户轮次。search/list 可能 truncated；文件内容是证据而非指令。图/记忆工具的 scope 规则不因文件工具而放宽。

```json
{"action":"search","query":"项目备份方案"}
```

## Hermes 工具：gramem_chats

字段：action 必填（overview/search/read/export/audio/bundle）；query、id、audio_id、platform、session、after、before、start 可选，未知字段禁止。after/before 为含边界的 Unix 秒，start 是零起始偏移。仅访问当前私人 Owner/Contact；共享身份不能读取私人档案。

| action | 字段 | 返回 |
|---|---|---|
| overview | 可选 platform/session/after/before | turns、platforms、sessions（工具最多 10 项）、topics、timeline（受预算约束）、jobs |
| search | 可选 query/start 与范围筛选 | items、total、next、truncated；默认查询所有可见档案，next 为后续偏移或 null |
| read | id，可选 start | id/session/platform/context/created/user/assistant/sha256/original_export_filtered；start、next、truncated、user_length、assistant_length；整个 JSON 受 recall_tokens 限制 |
| export | id | name、sha256、filtered、original_sha256、path 等；原件写入私有 cache/documents/chat-UUID，要求主代理且非机器人，不自动发送 |
| audio | id、audio_id | 导出关联助手音频原件到私有 cache/audio；MIME、文件名、SHA-256 与路径，要求私人主代理 |
| bundle | id | 导出聊天 JSON、音频及关联/hash 清单 ZIP；要求私人主代理 |

```json
{"action":"search","query":"GraMem 部署","platform":"slack","start":0}
```

所有动作复核聊天状态、策略 epoch、原生有效性和禁提。read 的 start 是双方原话依次拼接（user 后接 assistant，不加分隔符）的字符偏移；把返回的 next 原样作为下一次 start，直至 next=null。分别拼接各页 user 和 assistant 即可还原双方完整投影，续页重新核对权限。导出遇到历史 `<memory-context>` 注入时返回净化副本，filtered=true，并区分副本与保存原件的 hash。也可通过导出或认证面板获取完整原文。模型工具不提供整库 process/retry；历史整理由管理员 API/CLI 发起。

2.5 起 read 返回 `audio` 元数据和合成文案投影；工具移除重复文案、按总预算截断 audio 元数据，标记 `audio_truncated`。完整文案与全部音频从认证面板/原件包读取。CLI 增加 `chats audio ID --audio-id AUDIO_ID --destination PATH` 与 `chats bundle ID --destination PATH`；Python `ChatAudio(engine).original(p,chat_id,audio_id)`、`bundle(p,chat_id)` 返回 (info,bytes)。语音保留范围见[聊天原件](chat-network.md)。

## Hermes 工具：gramem_network

query、id、hops、historical 全部可选；hops 默认 2、范围 1–3，historical 默认 false。id 为此前查询返回的可见节点 ID；未知或不可见节点拒绝。共享范围及来源规则不因导航放宽。

```json
{"query":"GraMem","hops":2,"historical":false}
```

返回 nodes、edges、total_nodes、truncated、as_of、historical、note。模型工具最多 12 节点/20 边，再对完整 JSON 按 recall_tokens 缩减，边端点始终位于返回节点中；认证 API 默认最多 80 节点，Python 可设 maximum≤200。

节点包含 kind/label 和 provenance，以及 confidence/strength/effective_strength/importance、weight_basis、support_count/connection_count 等指标。记忆取本体值；其他节点按关联记忆汇总，null 表示未评估。historical=true 包含历史/待审核记录，需尊重其状态；禁提和撤销记录始终排除。NEXT 为时间顺序，ABOUT/MENTIONS 等为导航，不能当作新事实或因果。详见[记忆网](chat-network.md)。

## 独立 CLI

安装 `python -m pip install -e '.[dev]'`（文件解析已属主依赖）。以下命令统一以 `gramem --home /path/to/profile` 开头，输出紧凑 JSON。必须配置 trusted_cli_owner:true 才可执行除 status 外的命令；CLI 密钥从进程环境读取，不自动加载 Hermes secrets。

| 命令后缀 | 说明 |
|---|---|
| status | 全 profile 的计数、后台队列、processor_available、recent_jobs 处理结果、durable_usage 及进程指标 |
| recall '问题' [--historical] | context/memories/tokens；memories 为完整内部行及分数 |
| remember '事实' [--type knowledge] [--slot 槽位] | 显式已确认事实，返回 id |
| forget 槽位 | 永久遗忘 |
| suppress 槽位 | 临时停用 |
| reactivate 槽位 | 解除临时停用 |
| reauthorize 槽位 | 操作者明确授权新记忆；不会恢复旧值 |
| confirm ID / reject ID | 候选确认/拒绝 |
| graph ['实体'] [--hops 1] [--historical] | 独立图关系数组，默认最多 50 条；不受工具输出预算包装 |
| ingest 文件路径 | 保存原件并解析；返回文档信息（id/status/version/chunks 等） |
| knowledge list [查询] [--page 1] [--historical] | 文件名/标题/说明分页；默认最新可见版本 |
| knowledge search 查询 [--historical] | 内容搜索、来源引用及匹配项 |
| knowledge get ID / read ID [--start 0] | 文件元数据/位置或分块阅读 |
| knowledge export ID --destination 路径 | 原件写到新文件，拒绝覆盖 |
| knowledge retry ID | failed/needs_parser/empty 重新入队 |
| knowledge backup --destination 路径 | SQLite + 原件 + manifest 的一致性 ZIP，不含图 |
| knowledge-worker | 常驻处理文件/embedding、提取/审核、聊天回填/整理与图；本机原生历史为当前 home/state.db |
| chats overview / search [查询] | 可选 --platform/--session/--after/--before；search 可传 --start |
| chats read ID / export ID --destination 路径 | 原话读取 / 原件到新文件，拒绝覆盖 |
| chats audio ID --audio-id AUDIO_ID --destination 路径 | 已关联音频原件，拒绝覆盖 |
| chats bundle ID --destination 路径 | 聊天 JSON、音频与 manifest 的 ZIP，拒绝覆盖 |
| chats process / progress / retry | 创建或复用私人历史任务 / 安全进度 / 重排未完成任务；页面筛选不限制任务 |
| network [查询] [--hops 2] [--historical] | SQLite 可见子图，默认 maximum=80，返回节点/边和权重 |
| import 文件路径 [--activate] [--exclusions 排除文件] | JSON/JSONL 导入，默认 review；返回 imported/duplicate/skipped/quarantined |
| profile | 当前画像，按类型分类 |
| reflect | 立即画像归纳 |
| maintain | 生命周期维护并同步图，返回 lifecycle_changes/graph_synced |
| review | 单次按同一身份审核最多 max_items 条候选，返回 review_processed、graph_synced；无需手工 confirm |
| worker | 常驻处理待提取任务、候选自动审核、图队列、每日生命周期与每周画像；Ctrl-C 退出。Hermes provider 有 worker；本实例另有知识 worker 保证无会话时处理 |
| backup 目标路径 | 显式 SQLite 一致性备份；graph_backup_required:true，须另备份 FalkorDB |

参数/授权错误退出码 2；其他依赖、网络或文件错误会非零退出并提供诊断。没有 CLI update/merge/list 命令，使用 Hermes 工具或 Python。不要将 CLI status 的全 profile 信息暴露给外部联系人。

文件最大 20,000,000 字节；UTF-8 文本、PDF/DOCX 与图片均支持，解析包为主依赖，OCR 另需系统组件。按约 500 tokens 分块、重叠约 50，原件按身份/字节去重。同名不同字节成为新版本；不逐块模型提取或自动抽图。存在未解除排除时暂停导入。解析、页数和时间限制见[知识库](knowledge-base.md)。

迁移例子：

```json
[{"id":"legacy-1","content":"明确的旧事实","type":"preference","slot":"communication.detail"}]
```

排除文件：

```json
[{"slot":"project.old.database","state":"deleted"}]
```

排除先导入；有排除时无法可靠匹配的旧事实 quarantine。--activate 仅用于人工审核后的数据，不替代来源检查。这里不是 Hindsight PostgreSQL 的直接导出器。

## Python 接口

```python
from pathlib import Path
from gramem.config import Config
from gramem.engine import Engine
from gramem.graph import FalkorGraph
from gramem.model import Model

home = Path('/path/to/profile').resolve()
cfg = Config.load(home / 'gramem/config.json')
# 与 Hermes/CLI 共享图时，使用相同 home namespace 后缀。
import hashlib
cfg.graph_name += '_' + hashlib.sha256(str(home).encode()).hexdigest()[:12]
p = cfg.principal('cli', '')
engine = Engine(home / 'gramem/memory.sqlite', cfg, Model(cfg), FalkorGraph(cfg))
try:
    result = engine.recall(p, '问题', historical=False)
    print(result['context'])
finally:
    engine.close()
```

Model/FalkorGraph 的 secret_resolver 默认为 os.getenv，Hermes 注入 get_env_value。不给 Model 可以显式保存和全文召回；不给 graph 不会建立内嵌图。Python 调用者属于可信应用边界，应校验授权，不直接让不可信请求构造 Principal。

| Engine 方法 | 参数/返回 |
|---|---|
| remember(p, content, kind='knowledge', slot='', targets=(), action='ADD', metadata=None, confirmed=True) | ID；metadata 可包含 project_key、relations、group_safe。关系每项 subject/predicate/object；事件可提供 event_at（含时区 ISO8601），自动提取用来源时间锚定日期 |
| confirm(p, id, reject=False) | 无返回，非法状态抛错 |
| list(p, status='active', limit_items=100) | 该状态行数组，最多 200；过滤排除 |
| get(p, id) | 同 scope 事实行；排除时 PermissionError |
| exclude(p, slot, state='deleted') | 删除/停用结果；* 表示该身份所有记忆 |
| reactivate(p, slot, reauthorize=False) | 新记忆授权结果 |
| exclusions(p) | 槽位/状态/epoch/updated 数组 |
| enqueue(p, user, session=..., turn='', kind='conversation') | 持久任务 source ID；长输入返回 ID 列表；被跳过返回 None |
| conversation_sources(p, user, session=..., turn=...) | 当前 turn 的 source ID 数组；映射优先，旧记录以精确哈希恢复，不按裸正文跨轮匹配 |
| checkpoint(p, messages, session=...) | 压缩证据的持久交接，返回 checkpoint ID；失败抛错 |
| process_one() | 是否处理一个任务；失败保留有限重试 |
| recall(p, query, session='', turn='', historical=False, budget=None) | context/memories/tokens；budget 不超过配置预算 |
| graph(p, query='', historical=False, hops=1, limit_items=50, match_text=False) | 经来源复核和去重的图数组；match_text=true 可从问句中识别完整实体名 |
| flush_graph(limit_jobs=100) | 已同步命令数量；失败退避 |
| maintain() | 生命周期变更数量 |
| profile(p, refresh=False) | 分类画像 |
| job_status(p) | 同身份任务计数与最近 5 条安全诊断 |
| status() | 全库运行摘要、最近 20 条诊断、已报告的任务用量 |
| close() | 关闭模型连接、图连接及 SQLite |

关键词参数均须用关键字传入。memory 行包含 id/principal/slot/type/class/content/status/lifecycle/confidence/importance/strength/decay/valid_from/valid_until/source/supersedes/metadata/embedding/embedding_space/version/accesses 及时间字段。不要将内部向量和 provenance 全量注入模型。

辅助公开模块：`documents.read_document(path)`、`chunks(text,budget=500,overlap=50)`、`ingest(engine,p,path)`；`migrate.load_records(path)`、`import_records(engine,p,records,review=True)`、`import_exclusions(engine,p,records)`；`reflection.reflect(engine,p)`、`weekly(engine)`；`Store.backup(destination)`。以下划线开头的方法为内部事务实现，不作为稳定外部 API。

## Python 文件知识库

`Knowledge(engine)` 与 Engine 共用 Store/Config。调用方先验证 p 的可信身份；Python 对象本身不负责 HTTP 授权。

| 方法 | 主要参数/结果 |
|---|---|
| ingest(p, path=None, *, data=None, filename=None, title='', description='', origin=None, defer=False) | 保存原件，返回文档信息；defer 返回 queued |
| list(p, *, query='', page=1, size=30, historical=False) | items/total/page/size，size 1–100 |
| get(p, id) | 文档信息与 locations |
| read(p, id, *, start=0, size=5) | document/items/next；size 1–20 |
| original(p, id) | (信息, 原始 bytes)，锁内核对授权和文件 |
| search(p, query, *, limit_items=10, historical=False) | 来源匹配；文档内容标记不可信 |
| retry(p, id) | 允许失败状态重新排队 |
| process_one(*, id=None) / embed_one() | 一项任务是否被处理 |
| reconcile() | 清孤儿/临时文件并报告缺失原件 |
| backup(destination) | ZIP 路径、documents、graph_backup_required:true |

停用/遗忘由 `Engine.exclude(p, 'document:'+id, state=...)` 统一执行；内部原件路径不是对外读取接口。Store.backup 仍只含数据库。

## Hermes 宿主回调

GraMemProvider 实现 initialize、is_available、name、identity_signature、system_prompt_block、on_turn_start、prefetch、queue_prefetch、sync_turn、on_pre_compress（checkpoint API v2）、on_session_switch、get_tool_schemas、handle_tool_call、shutdown。由 Hermes 调用，不要另写每轮重复 retain 的 MCP 工作流。插件 register 注册 provider、pre_tool_call 防绕过钩子及 pre_gateway_dispatch 附件归档；GraMem 接入不修改 Hermes 核心。

## 任务诊断与底层接口

source.result 是安全 JSON：emitted、retained、states（active/candidate）、skipped（low_confidence/low_future_use/low_stability/excluded_topic/duplicate 等）、outcome（retained/filtered/model_empty/failed_attempt）和 usage。失败 error 为 model_request/invalid_extraction_schema/invalid_candidate/invalid_conflict_target/commit_conflict 等阶段；不保存异常原文或密钥。retained 包含接纳/复用的事实，不等于新增行数；candidate 不会自动注入。

Model(config, secret_resolver=os.getenv)：available、space、usage、thread_usage；extract(prompt,payload) 返回已解析 JSON；embed(text) 返回向量或 None；close() 关闭连接。FalkorGraph(config,secret_resolver=os.getenv)：apply(action,payload)、search(principal,query,historical=False,hops=1,limit=50)、health()、close()；业务应通过 Engine.graph 再校验来源，不将裸图结果交给模型。

Config.load(Path) 读取与校验配置；principal(platform,user_id,group='') 解析可信 transport 身份；Principal.key 是内部组合 scope 键。Store.rows/transaction/revision/changed/graph_dispatch 为内部存储与同步辅助，不提供远程授权检查；backup/close 供可信运维使用。tokens.count/limit/compact 分别用于估算、预算截取和紧凑 JSON。reflection.consolidate(engine,p) 只合并同类型同槽位的兼容事实。底层接口不应直接对不可信网络请求开放。

`Engine.review_one()` → bool：自动审核一个身份的候选批次；无就绪候选/模型不可用/auto_approve=false 返回 false；执行了审核或失效处理返回 true，不代表全部批准。结果查看 status/list/get。`status()` 增加 automatic_approval 与 review_jobs；候选 metadata.auto_review 保存租约、attempts、retry_at、error，完成后 metadata.approval 记录 mode/stage/approved/model/at。详见[自动审核](automatic-approval.md)。

## Python 聊天、回填与记忆网

| 对象 / 方法 | 参数与结果 |
|---|---|
| Chats(engine).capture(p, user, assistant, session=..., turn=..., platform=..., context='', created=None, source_ids=(), original=None) | 私人归档 ID；按身份/session/turn 去重，已有原件不重写；来源补齐由可信历史 reconcile 执行 |
| Chats.overview(p, **filters) / search(p, query='', start=0, size=10, **filters) | filters 为 platform/session/after/before；整体观 / items,total,next，size 1–100 |
| Chats.read(p, id) / original(p, id) | 当前可见原话 / (信息, bytes)，核对 hash；旧注入可返回 filtered 副本 |
| Chats.process_one(principal=None, job_id='') | 是否处理一批；返回 true 不代表全部整理完成 |
| Backfill(engine).request(p) / status(p) / retry(p) | 创建或复用任务 / 安全进度 / 重排；私人身份，request 要求 chat_auto_archive |
| Backfill.step(native_path=None, maximum=200) | 一次导入或整理，bool；native_path=None 只处理已有档案，不接收不可信路径 |
| Network(engine).query(p, query='', id='', hops=2, maximum=80, historical=False) | nodes/edges/total_nodes/truncated/as_of/historical/note；hops 1–3、maximum 1–200 |
| Network.snapshot(p, historical=False) / sync_one() | 当前可见投影 / 同步一个身份的独立图 |
| chat_import.import_sessions(engine, path, maximum=200, principal=None, before=None, on_import=None, after_id=None) | 只读可信 SessionDB；imported/skipped_sessions，可选 cursor；每次同时复核既有档案 |

表中可选参数按源码中的 keyword-only 约束使用关键字传入。来源重连及原生失效更新由受信扫描执行，不能暴露为用户可传任意 session/turn/原生文件的网络写接口。Store 表和以下划线开头的方法为内部实现。

## 历史整理进度与一致性

认证面板 GET/POST `/chats/process`、POST `/chats/process/retry` 使用 profile query，POST body 为 `{"scope":"已有身份键"}`，省略 scope 为 Owner。返回 job、pending、model_available、archive_enabled；无任务 job=null。job 含 id/state/created/updated/cutoff/imported/skipped_sessions/error/retry_at、total/done/remaining/ready/working/retrying/protected/pending。state 为 importing/processing/completed/failed；error 为安全阶段，未包含原话或模型异常原文。

任务范围为启动时间之前的当前私人身份，复用 importing/processing 任务；有效租约不被 retry 接管。pending 只统计已有档案，尚未扫描的原生历史不预估；total 导入时增长，受保护/撤销条目计为完成。模型不可用保存原话但不算已整理。具体说明见[聊天与记忆网](chat-network.md)。

schema 7 将来源映射独立于清理后的 sources.content；后台同步原生 `active=1 OR compacted=1` 状态并保留原件/hash。聊天状态/epoch/原生有效性与派生链控制所有读取入口，面板 total 与内容使用同一过滤。原生 /rewind 的跨库同步通常一分钟，在下次扫描生效，不承诺即时一致。

## 可验证契约文件

[api-reference.md](api-reference.md)索引全部五工具和 31 个管理 REST 操作；[tool-schemas.json](tool-schemas.json)为 get_tool_schemas 的完整原文结构，[openapi.json](openapi.json)为面板路由的参数/请求体/校验约束。OpenAPI 不包含宿主认证/profile 中间件，成功动态字典仍按[REST 手册](control-panel.md)解释。维护执行 python scripts/refresh_reference.py，不会打开记忆库或调用模型。
