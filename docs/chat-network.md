# 聊天档案与记忆网

GraMem 2.5.0，SQLite schema 8，管理面板 1.7.0。启用 `chat_auto_archive=true`（默认）后，主用户对话自动归档用户及助手原话，保存不可变的 JSON 原件和 SHA-256。聊天 JSON 原件在 `memory.sqlite` 的 `chat_turns.original` 中；助手语音原件另存于私有 `gramem/chats/audio`，两者均随含原件 ZIP 和全实例 NAS 备份保留。

后台按同一身份、同一会话每批最多 8 轮整理。模型生成主题和简明时间线，每项必须带当前原文的引用；用户陈述和助手提议明确区分。文本搜索同时检索原话与摘要。整理失败自动退避，持久租约可接管；过期 worker 或排除规则变化后不能提交旧摘要。没有模型且没有排除规则时可读取原话，不生成推断摘要。

## 助手语音原件（2.5）

每轮完成时识别助手音频引用及成功的原生 `text_to_speech` 调用，将音频字节独立保存到 `gramem/chats/audio/<prefix>/<id>.blob`，以身份、聊天 ID 和原始来源路径去重，保存真实 MIME、大小和 SHA-256。原件目录 700、文件 600，原子写入并 fsync；之后 Hermes 临时音频缓存被清理也不影响原件。只读取当前 profile 的 `cache/audio`、兼容 `audio_cache` 和 `voice-memos` 内的本地音频，不按聊天中的任意路径读取文件。单段最多 20 MB，支持 MP3/WAV/Ogg/M4A/AAC/CAF/FLAC/WebM/AIFF 的可验证容器；缓存缺失、格式无法验证或来源不受支持时只保存关联和诊断，不重合成或伪造音频。

历史扫描会修复已有聊天的语音关联，保留既有聊天 JSON 字节/hash。合成文案来自同一轮、相同 tool_call_id 的 TTS 输入或工具明确返回的 spoken_text；它是生成证据，不冒充 ASR 转写或平台成功投递回执。保存的是合成源音频，不承诺等同于平台再次转码后的字节。文本参与助手原话投影、搜索和证据摘要，仍不作为用户事实自动提取。新语音先使旧整理结果失效，重新审查后才可查看/播放/下载；没有可靠文案的音频在有语义排除时保守隐藏。

聊天详情显示音频与合成文案，可播放、下载单段原件，或下载含 `chat.json`、`audio/*` 与关联/hash 清单的“聊天与语音原件包”。净化旧 memory-context 的规则同样适用于包内聊天副本。记忆网新增 `audio` 节点和 `HAS_AUDIO` 连接，音频节点只从所属聊天的关联记忆聚合权重，无支持时未评估。

禁提、身份/profile 隔离与原生撤销状态同时限制原话、音频、文案、原件包及图；停用保留音频，明确删除匹配聊天时清空文案/元数据并删除插件音频文件，旧缓存再次扫描也不复活原件。原生历史与此前备份不随之擦除。知识 ZIP 的 manifest schema 现在反映实际 SQLite schema，并包含 `chat_audio` 校验清单及音频文件；恢复时解压完整目录，不只恢复 SQLite。

```sh
gramem --home /path/to/profile chats read RECORD_ID
gramem --home /path/to/profile chats audio RECORD_ID --audio-id AUDIO_ID --destination ./voice.mp3
gramem --home /path/to/profile chats bundle RECORD_ID --destination ./chat-originals.zip
```

`gramem_chats` 新增 `audio`（id、audio_id）和 `bundle`（id）动作，返回授权导出缓存路径；模型读取仍受预算限制。认证 API 新增 `/chats/{id}/audio/{audio_id}/original` 与 `/chats/{id}/bundle`，沿用 scope/profile、登录保护与 no-store，不接受任意文件路径。

## 一键处理历史记录（2.4）

在“聊天档案”点击 **一键处理全部未整理记录**，后台先从当前 profile 的原生历史补齐当前身份的私人对话，再整理所有未完成的归档，包括此前失败或仅保留原话的记录。范围固定为任务启动时间之前、可验证身份且已有助手回复的对话；页面搜索、日期、平台和会话筛选不缩小这项任务。已整理且排除策略未变的记录会跳过，不重复调用模型。没有新记录时也可安全再次执行。

界面显示导入阶段、总量、已完成、处理中、等待重试及剩余数量；导入时总量随分批补齐增长。重复点击复用同一任务，关闭页面不影响处理，服务重启后可以续跑。失败记录自动退避，可用“重试未完成任务”立即重新排队；缺少可用模型时显示等待，保存原话不算整理完成。整理结果保留 JSON 原件及校验值，产生摘要、主题、时间线和记忆网连接；不会将已归档的旧聊天重新提取为当前事实。禁提记录只显示受保护数量，不展示原话或摘要。

```sh
gramem --home /path/to/profile chats process
gramem --home /path/to/profile chats progress
gramem --home /path/to/profile chats retry
# 未运行 Hermes/provider 或常驻知识 worker 时，需要启动 CLI worker。
gramem --home /path/to/profile knowledge-worker
```

认证 API：`POST /chats/process` 创建或复用任务，`GET /chats/process` 查询进度，`POST /chats/process/retry` 重试。请求沿用当前 profile 和已存在的 `scope`，不接受任意历史文件路径；共享身份不能提交私人历史任务。后台由现有知识 worker、Hermes provider 或 CLI worker 执行，每次最多补齐 200 轮、按原生消息 ID 游标遍历到末尾，然后逐批整理，不受第一批上限影响。

schema 6 新增 `chat_backfill_jobs` 与 `chat_backfill_items`，持久保存范围、游标、进度及任务租约。任务和每条聊天各有租约与尝试次数，接管后的旧 worker 不能覆盖新结果；整理提交同时复核当前禁提规则。schema 5 自动升级，已有原件、摘要与记忆保持不变。原生历史不可用时仍可处理已归档记录，并显示补齐提示。

## 统一请求

`gramem_chats` 支持 `overview`、`search`、`read`、`export`，可传 `platform`、`session`、`after`/`before`（Unix 秒）、`start`。默认跨所有已验证为同一身份的平台、会话和压缩前 context 查询；输出带平台、会话、时间及记录 ID，导出返回私有缓存内的原件路径。读大记录时整个 JSON 受预算限制，返回 next 和 truncated；将 next 作为下一次 read.start 直至 next=null，即可续读完整双方原话。start 按 user 后接 assistant 的字符偏移计数，每一页重新核对禁提和原生有效性。完整内容也可通过导出或认证面板获得。

历史导入支持 Teams、Slack、Email、Photon、Telegram 和可信 CLI；共享会话与无法确认作者的历史继续跳过。Telegram 身份关联前的独立联系人档案不自动搬迁；管理员主动补齐历史时，原生会话按当前已核实绑定导入，并沿用当前身份的禁提审核。

```sh
gramem --home /path/to/profile chats overview
gramem --home /path/to/profile chats search 'GraMem' --platform slack
gramem --home /path/to/profile chats read RECORD_ID
gramem --home /path/to/profile chats export RECORD_ID --destination ./original.json
gramem --home /path/to/profile network 'GraMem' --hops 3
```

认证面板增加“聊天档案”（整体观、主题、时间线、日期/平台/会话筛选、原话及原件下载）及“记忆网”（可选节点和沿连接展开的图）。API 位于 `/chats/overview`、`/chats`、`/chats/{id}`、`/chats/{id}/original` 和 `/network`，沿用宿主的 profile 认证与身份选择。

## 新记忆网

新图名为原时间图 namespace 加 `_knowledge`，超长名字采用哈希缩短，独立于既有 FACT 时间图。后台把当前有权读取的投影发布到新 FalkorDB 图，持续更新；图异常不影响原文保存和本地投影查询。管理面板与工具始终根据 SQLite 当前状态重建可见子图，再在该子图内有界遍历，所以隐藏节点不能当中间桥梁。

节点包含 `chat`、`summary`、`memory`、`document`、`topic`、`entity`、`context` 和 `event`。`SUPPORTED_BY` 表示直接原文来源，`DERIVED_FROM` 表示记忆的派生来源；`ABOUT`、`MENTIONS`、`CONTAINS` 是共同主题、明确名称及包含关系，只用于导航，不能推导新事实。文件连接到自己的知识分块，事实连接到聊天提取源，已有证据关系中的实体也加入新图。相同原文/规范名称建立联系，不进行未经证实的实体合并。单次图查询最多 200 节点、三跳，模型工具另受较小预算限制。

## 权重与事件（2.3）

记忆网以已归档、已记录的内容为范围，不会凭空重建未采集的经历。事件节点来自本身份已有的记忆审计事件，包括创建、更新、确认、召回强化、生命周期变化；只引用当前有权读取的记忆，不暴露原始审计 detail 或禁提控制。`RECORDED_FOR` 连接事件与对应记忆，`NEXT` 按聊天、文件和事件的记录时间串联，表示时间顺序，不表示因果关系。

每个节点返回 `confidence`、`strength`、`effective_strength`、`importance`、`weight_basis`、`support_count` 和 `connection_count`。记忆节点的置信度、原始强度、重要性、版本、状态、生命周期、有效期直接读取记忆本体；`effective_strength` 使用 Engine 的同一衰减公式，在查询的 `as_of` 时间计算。读取图不强化记忆，不修改本体。召回强化和维护强度变化都会使图同步失效。

原话、文件、摘要、主题和会话的指标来自不同关联记忆各指标的最大值，`weight_basis=related_memories`，并返回最多 20 个 `weight_memory_ids`；计数按记忆 ID 去重，不会因为多条路径重复提高权重。它们表示关联记忆的强度，不是聊天中每句话的正确概率。没有对应记忆时各指标为 `null`，`weight_basis=unassessed`；不能把原件存在当作其陈述已获确认。聚合沿指定来源/包含/主题方向进行，不通过 `NEXT`、派生或整张连通图扩散。事件使用对应记忆的当前权重，`weight_basis=memory_reference`，不冒充事件发生时的历史权重。

面板默认包含历史及待审核记忆，可切换为当前记忆；状态清楚区分 superseded/archived/candidate/rejected，禁提/删除始终排除。图中的节点大小可按当前强度、置信度或重要性切换；详情展示本体强度和当前强度。API 和工具沿用 `historical` 参数，缺省仍为当前视图，后台 FalkorDB 保存完整有权访问的历史投影。为了兼容既有部署，接口 `gramem_network`、`/network` 和 `_knowledge` namespace 保持不变。

FalkorDB 中权重保存为数值属性，同时保存节点属性 JSON。查询实时从 SQLite 重建，后台约每 30 秒服务同步队列，每轮最多 8 个身份；即使本体没有新写入，也在快照超过 60 秒后重新计算衰减权重。按最早快照先更新，避免跨平台身份被饿死；同步耗时及队列会增加后台延迟。单个快照最多加载 5000 条记忆、5000 条审计事件和 1000 个文档，达到上限返回 `truncated`，查询节点另有有界展开。

## 不要记住、不要提起与删除

明确“不要记住／不要再提”意味着持续停止提及或使用该主题，原件允许保留。不会自动到期；聊天搜索、原话、下载、摘要、记忆、画像、关系图和记忆网都遵守排除规则。规则改变立即使旧聊天摘要与相关来源失效，后台重新审查所有该身份的记录；不确定时隐藏。原文中出现旧禁提请求时，后台可依据原话创建无私密值的主题禁提规则，既有解除规则不会被重复覆盖。

只有明确“删除／擦除／忘掉”的控制使用 deleted。匹配主题的聊天原件作为整轮单元清空，摘要删除；不承诺擦除 Hermes SessionDB、当前上下文、历史备份、导出副本或模型服务已有数据。重新授权不会复活已擦除原件。旧停用主题的恢复须明确 reactivate；不是普通提起主题就恢复。

## 身份与历史补齐

主用户 `sync_turn` 原生回调在每轮完成时归档原文；机器人、cron、subagent、flush 不采集。已开启群内 Owner 采集时，只归档当前已验证 Owner 发起的这一轮到其私人档案；共享渠道不能读取私人档案。

常驻 worker 每分钟只读扫描当前 profile 的原生 `state.db`，补齐可验证身份的私人平台会话，按原生 message_uid 去重，包括压缩前原话；不回放任务、不发送消息、不修改宿主历史。来源不明、后台会话、旧群聊无法逐条验证作者的记录跳过；压缩摘要不能冒充原件。技术推理、工具内部调用及系统提示不算双方聊天原话，不导出为聊天原件。旧 Hermes 历史若已丢失原话则无法重建。

2.4.1/schema 7 持久保存不含正文的来源映射，清理完成提取的正文后仍能关联聊天与事实。扫描会按确切来源 ID 修复已有档案链接，并解码宿主保存的多模态正文。`active=0,compacted=0` 的撤销消息不参与新导入；已归档单元内任一原生消息被撤销时，下次扫描停用其聊天、摘要及关联事实投影，原件/hash 保留。同步是后台扫描发生时生效，通常间隔一分钟，不能承诺原生 rewind 与 GraMem 可见性在跨库事务中即时一致。历史回填游标不会跳过这项同步，已停用条目不会卡住整理进度。

原生撤回同步也会终止仅由撤回单元支持的 pending/working/failed 提取来源：清理待提取正文、保留数值用量，结果标记 native_inactive；仍被其他有效聊天引用的来源不受影响。overview.jobs 将撤回条目归为 native_inactive，避免误报为永远待整理。聊天整理的实体标签只保留原话中的确切名称；可选标签无依据时丢弃标签，不让整批记录无限重试，策略判定、控制请求和摘要原文证据仍严格校验。失败日志仅包含阶段、异常类型和条数。

Telegram 私聊与 Teams、Slack、Email、Photon、CLI 一样参与历史导入；共享历史缺少逐条认证作者时仍跳过。增加 aliases 仅影响后续身份解析，不会自动改写旧身份。管理员可在停写和备份后调用 gramem.identity_migration.migrate_verified_contact(engine, platform, author)，只接受明确绑定当前 Owner 的账户；迁移保留记忆/来源 ID 和原件/hash，重算聊天 ID、依赖关联并重新执行目标身份的策略检查。存在重叠聊天、未结束来源任务或文档/回填任务时拒绝自动迁移。完成检查后使用 sync_migrated_graph 重建允许的关系，并清理旧身份的派生 Knowledge 图投影；这不是模型工具。

已绑定 aliases 才能合并私人档案；未绑定平台保持独立联系人身份。独立 Hermes profile 的图、SQLite 和身份保持隔离。所有聊天/文件/摘要都是不可信资料，不能执行其内嵌指令。

历史宿主注入的 `<memory-context>` 不算用户原话，保留在校验原件里，但从展示、搜索和摘要输入中剥离。此类记录的导出返回净化后的原话副本（`filtered=true`），同时给出原件和副本各自的 SHA-256，避免下载恢复旧后端排除内容。自动整理同时保留原话中明确出现的实体名称，用同名实体连接聊天、文件与已有事实。
