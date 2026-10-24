# GraMem 管理面板与 REST 接口

现行面板 1.8.1 / GraMem 2.5.0 / schema 8，核对日期 2026-10-14。

附属组件源码与操作说明：[integrations/control-panel/README.md](../integrations/control-panel/README.md)。

只管理 GraMem 的事实记忆、文件知识库、关系图、画像与偏好、生命周期与召回行为、模型/图连接、身份映射、导入和维护。Hermes 的功能继续使用其官方面板，不在这里重复。

使用 Material 3 Expressive 风格，支持自定义主题色和明暗模式。关系网支持实体搜索、历史关系、1–3 跳、拖动、缩放和来源查看。

部署入口：[<宿主地址>:8500/control](http://<宿主地址>:8500/control)。使用实例管理员认证；登录凭据只保存在管理员的私有文件中，不写入项目文档。

## 管理 API

面板 1.8.1，配合 GraMem 2.5.0 / schema 8。请求路径前缀为 `/api/plugins/hermes-control`，所有路由使用 Hermes 原生管理员认证；统一带 `?profile=default`（或已有 profile 名）。未知 profile 拒绝，不由插件创建。`scope` 为 overview 返回的完整 principal 字符串，只允许库内已有身份；省略时为 Owner。模型工具不调用这些管理员 API。

| 方法与路径 | 参数或 JSON 请求体 | 返回与用途 |
|---|---|---|
| GET /overview | profile | home、owner、scopes、status、usage_note；全 profile 统计 |
| GET /settings | profile | values（全部 Config 字段）、revision（文件 SHA256） |
| PUT /settings | values 对象、revision | 校验、配置快照、原子保存；ok、restart_required、revision；冲突返回 409 |
| GET /models | profile | 当前 Chat/Embedding、官方连接、timeout、revision、推荐模型目录 |
| PUT /models | model、embedding_model、embedding_dimensions、embedding_revision、timeout、revision | 固定阿里官方连接，原子保存与备份，返回 restart_required/revision；冲突 409 |
| GET /credentials | profile | model/graph 的 env、is_set；不返回凭据值 |
| PUT /credentials | kind: model 或 graph、value: 新凭据 | 写入宿主保密存储；ok、restart_required |
| GET /memories | scope、q（最多 2000 字符）、status=active、page≥1、size=30（1–100） | items、total、page、size；完整分页，向量不返回，排除内容不显示 |
| GET /recall | q 必填、scope、historical=false | context、memories、tokens；返回内容移除向量 |
| GET /graph | scope、q、hops=1–3、historical=false、limit=1–199 | items、truncated、healthy；来源复核后的独立图查询 |
| GET /profile | scope | profile、exclusions；缓存会响应事实变更和来源衰减 |
| GET /queues | profile | 最近 100 条 sources 和最早 100 条 graph 同步诊断，不返回原文 |
| POST /operation | action 及下述字段 | 调用真实 Engine 管理操作 |
| POST /import | records 对象数组、exclusions 对象数组、activate=false、scope | imported、duplicate、skipped、quarantined；单次最多 10000 条，先应用排除 |
| POST /document | filename、data（Base64）、scope、可选 title/description | /knowledge/upload 的兼容入口；保存原件，返回文档信息与 queued |
| GET /chats/process | scope | job、pending、model_available、archive_enabled；当前身份的安全进度 |
| POST /chats/process | scope | 创建或复用历史聊天整理任务，后台补齐原话并处理全部未完成记录 |
| POST /chats/process/retry | scope | 重排未完成任务；不接管仍有效的租约 |
| GET /chats/overview | scope、platform、session、after/before（含边界 Unix 秒） | turns、audio、platforms、sessions、topics、timeline、jobs |
| GET /chats | q、scope、platform、session、after/before、start≥0、size=20（1–100） | items（含 audio_count）、total、next；同一可见范围搜索原话、合成文案与摘要 |
| GET /chats/{id} | scope | 原话与元数据；包含 sha256、original_export_filtered、audio 原件元数据及合成文案 |
| GET /chats/{id}/original | scope | JSON 下载；X-Content-SHA256、附件、Cache-Control:no-store |
| GET /chats/{id}/audio/{audio_id}/original | scope | 播放/下载关联音频；复核聊天/音频身份与 hash、真实 MIME、nosniff、no-store |
| GET /chats/{id}/bundle | scope | 聊天 JSON、音频、关联/hash 清单 ZIP；遵守净化/禁提与 no-store |
| GET /network | scope、q、id、hops=2（1–3）、historical=false | nodes、edges、total_nodes、truncated、as_of、historical、note；最多 80 节点 |

operation 可用 action：remember、update、merge、confirm、reject、forget、suppress、reactivate、reauthorize、reflect、consolidate、maintain、worker、sync_graph、backup。可用字段：scope、id、slot、content（最多 2000 字符）、type（默认 knowledge）、targets（最多 200 个 ID）、relations（最多 50 项 subject/predicate/object）、confirmed（默认 true）、authorization（默认 false）。未声明字段返回 422。

聊天档案的“一键处理全部未整理记录”固定处理当前身份在启动时刻之前的可信私人历史，页面搜索筛选不限制任务。进度每 3 秒刷新，关闭页面不影响后台；已完成记录跳过，失败可重试，禁提记录不展示内容。详细范围和 CLI 见[历史整理](chat-network.md)。

remember/update/merge 返回 id，含义与 [引擎接口](interfaces.md) 相同。管理员显式保存默认为已确认；confirmed=false 可创建后台 LLM 自动审核的候选。群保存仅允许 Owner 提交非个人共享类型。confirm/reject 返回 ok。forget/suppress 需要 authorization=true，并对整个 slot 生效；reauthorize 也需要该字段，其含义为操作者明确允许新事实。reactivate 不能解除 deleted。

文档的分块共享重叠原文，遗忘一个分块会清除整份文档来源及派生事实，响应的 document_sources_erased 表示清除的来源数。其他文档和身份不受影响；此范围与 CLI、Python 和 Agent 工具一致。

reflect 调用真实模型归纳，返回带 source_ids 的分类画像；模型未配置时返回当前事实画像。consolidate 调用同槽整理后再归纳，返回 consolidated、profile。maintain 返回 lifecycle_changes、graph_synced；worker 处理一项会话任务、一项知识解析和一项 embedding，返回 processed、review_processed、knowledge_processed、embedding_processed、graph_synced；sync_graph 返回 graph_synced。backup 是显式知识 ZIP 备份，返回 backup、documents、graph_backup_required:true，包含 SQLite/原件/manifest，不包含独立图。配置保存只快照配置，不自动备份记忆。

```json
{"action":"update","content":"GraMem 使用独立 FalkorDB","type":"project","slot":"project.gramem.graph","targets":["查询获得的真实ID"],"relations":[{"subject":"GraMem","predicate":"USES","object":"FalkorDB"}]}
```

记忆分页的 total 与内容共用 blocked 递归过滤：排除、聊天状态、策略 epoch、原生撤销以及派生链均生效，q/status/历史视图不能恢复无效内容。记忆网从当前 SQLite 可见子图重建后遍历，边端点始终在 nodes 中。原生撤销在后台扫描时同步，通常一分钟；GET 查询不是跨库同步屏障。

认证由宿主返回未登录 401；未知 profile 由宿主拒绝（本实例 404）。请求体未知字段或参数类型/范围违反 FastAPI schema 为 422，文件超 20,000,000 bytes 为 413。API 参数/范围错误为 400；未配置 profile 的 GraMem 为 409；未知身份为 404，跨 Owner 范围为 403；模型处理不可用为 503。配置和凭据变更需重启 gateway、dashboard 与独立知识 worker，使各进程采用同一配置。不要将这些全 profile 管理接口开放给普通联系人。

## GraMem 模型管理

“行为与模型”的模型卡片允许选择推荐项或填写阿里官方模型 ID，空模型表示停用。Chat 供提取、排除分类、画像和聊天整理共用；Embedding 供语义检索和知识库向量使用。连接固定为 `https://dashscope.aliyuncs.com/compatible-mode/v1`，凭据变量为 `DASHSCOPE_API_KEY`，密钥在单独的连接凭据表单中修改。

`PUT /models` 要求完整字段：`model`、`embedding_model`（≤200 字符，不含 `qwen/` 供应商前缀）、`embedding_dimensions`（非负严格整数，0 为模型默认）、`embedding_revision`（1–100 字符）、`timeout`（有限数值，0 < timeout ≤ 120 秒）、`revision`（GET 返回的文件 SHA256）。保存保留其他 Config 字段、自动快照、检查文件 revision。模型或维度变化且未另改空间版本时，自动生成新版本。与行为设置共用文件版本，冲突需重新加载。

配置保存后需重启 gateway、dashboard 与知识 worker。更换向量空间后旧向量不参与新空间检索，知识库向量由后台逐步重建；普通记忆旧向量不保证自动重建，关键词和图召回继续可用。

## 知识库接口

- `POST /knowledge/upload`（`/document` 兼容入口）：base64 文件、filename、scope、可选 title/description。保存原件后返回 queued，不代表解析完成。
- `GET /knowledge`：q（≤2000 字符）、page≥1、size=30（1–100）、historical、scope；默认列出每个同名文件的最新可见版本。
- `GET /knowledge/search`：q、historical、scope；全文与已完成 embedding 的语义检索，返回来源页码和分块。
- `GET /knowledge/{id}`：scope、start≥0；分页读取原文分块。
- `GET /knowledge/{id}/original`：scope；认证后的原件下载，强制附件和 no-store，X-Content-SHA256 对应实际下载字节。
- `POST /knowledge/control`：id、scope、action=retry/forget/suppress/reactivate。管理员认证即管理权限；该请求体不接受 authorization 字段（与 /operation 不同）。按指定 ID 遗忘一个版本并删除原件/关联记忆，不能把它解释为全部历史版本。
- `/operation` 的 worker 同时处理一个知识解析任务和一个 embedding；backup 改为包含 SQLite、原件、校验清单的 ZIP，FalkorDB 仍独立备份。

2.1.1：默认开启 LLM 自动审核，“候选”在界面显示“自动审核中”，移除逐条人工确认按钮；管理员仍可显式拒绝。confirmation_types 只作用于传统模式，身份等新提取事实不再进入人工等待。


## 请求示例与分页

使用原生登录后取得的 cookie；profile 为 query 参数，scope 在 GET query / POST body 中提供。principal 可能含控制分隔符，使用客户端 params 或 URL 编码，不手写拼接。

```http
GET /api/plugins/hermes-control/memories?profile=default&page=1&size=30&status=active
GET /api/plugins/hermes-control/chats?profile=default&start=0&size=20
GET /api/plugins/hermes-control/network?profile=default&hops=2
```

```json
{"scope":"overview 返回的现有 principal"}
```

以上 body 用于 POST /chats/process 或 /chats/process/retry；HTTP 只创建任务/查进度，模型及导入由 worker 执行。知识列表和记忆列表返回 page/size/total；聊天搜索返回 next 偏移，无下一页为 null。原件读取与下载各自复核当前 scope 和来源；净化聊天副本的下载 hash 对应副本，库内 original hash 仍保留，详见[聊天原件](chat-network.md)。
