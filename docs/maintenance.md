# GraMem 维护手册

适用于 **2.5.0 / schema 8 / 面板 1.8.1**，核对日期 2026-10-14，Asia/Singapore。安装及实例目录见[部署](deployment.md)，宿主服务、NAS 与静默维护见Hermes 维护。

## 日常观察

Hermes provider 与受管理的常驻 worker 共用持久租约、attempts、跨进程图/原件锁，处理会话提取、候选审核、知识解析/embedding、聊天整理/回填和图同步。实例知识 worker 每分钟只读扫描可信私人 SessionDB 历史，同步既有档案的来源及原生撤销状态；不要为排错增加未管理常驻进程。

```sh
gramem --home /path/to/profile status
gramem --home /path/to/profile knowledge list
gramem --home /path/to/profile chats progress
```

除 status 外，CLI 需要 trusted_cli_owner=true；模型密钥来自环境。宿主 provider 和实例 worker 使用 profile secret resolver。管理输出属于全 profile 或 Owner 范围，面板应由管理员认证访问。

| 状态 / 指标 | 含义与检查 |
|---|---|
| 文件 queued / processing | 原件已保存，等待或按租约解析；看 worker、lease、磁盘与日志 |
| ready / partial | 文字索引完成 / 有解析限制；向量可能仍在逐块补齐 |
| needs_parser / failed / empty | 缺组件 / 失败 / 无文本；修好原因后 knowledge retry |
| 会话 sources failed | 提取有限重试后失败，查看安全阶段/result；没有 CLI source retry |
| 聊天 pending / working / ready / silent / redacted | 待整理 / 租约执行 / 可见 / 禁提 / 已擦除；另复核 policy_epoch 与 native_active |
| 回填 importing / processing / completed / failed | 导入 / 整理 / 完成 / 导入故障；total 随导入增长，protected 计为完成 |
| graph_pending | outbox 待同步；与图健康一起看，查询空不证明服务健康 |

metrics / model_usage 为当前进程统计；durable_usage 只累计任务已报告的 usage，不是完整账单。`model_available=false` 时保存原话不算已整理。知识分块 decay=0，不会因普通衰减消失。

## 排错与重试

先查版本、运行路径、配置、principal、队列与日志，再选择具体操作。

| 现象 | 处理 |
|---|---|
| 文件失败或缺 parser | 核对实际 managed runtime 的 PDF/DOCX/Pillow，以及系统 Tesseract/语言包/Poppler；修好后 `knowledge retry ID` |
| OCR 汉字不符合资料语言 | 简体 chi_sim+eng；繁体 chi_tra+eng，先装语言包 |
| ready 但语义命中弱 | 查 embedding 是否补齐、维度/revision 和凭据；空间变更后等待重新补向量 |
| 历史整理停滞 | 查 worker、chats progress、model_available、lease/retry_at；未完成任务用 `chats retry`，仍有效租约不会被接管 |
| /rewind 后档案暂时仍可见 | 等待一次可信历史扫描；通常一分钟，检查 chat_native_state 与 worker 日志，不编辑原件/hash |
| 档案、来源事实或派生不可见 | 查 scope、状态、policy_epoch、native_active、排除及来源链；total 与分页同一过滤，不能靠换接口恢复 |
| 图为空或积压 | 查容器健康、地址、namespace 与 outbox；普通事实仍可保存/召回，修好后同步 |
| provider 或面板无法加载 | 查显式注册、enabled、原生发现与实际依赖环境；不要安装到无关 venv |

候选默认由 LLM 自动审核，失败退避，最长一小时；查看 metadata.auto_review.error。会话提取最多 5 次尝试，修复后若需要管理员重排，先确认来源未删除/停用并审查当前实现；不得重置 redacted 内容。图 outbox 按顺序退避、没有固定尝试上限。

不可见与物理删除不同：silent 或 native inactive 的聊天可保留原件但阻断阅读/下载/摘要/事实/图；deleted 清除匹配原件与派生。文档任一分块排除会阻断整份版本。知识 reconcile 清孤儿/临时文件并报告缺失原件；不能用分块拼接冒充原件。

## 备份与恢复

```sh
gramem --home /path/to/profile knowledge backup   --destination /private/backups/knowledge.zip
```

ZIP 包含一致性 SQLite、保留原件和 SHA-256 manifest，聊天 JSON 原件随 SQLite 保存，助手语音文件位于 chats/audio，ZIP 同时包含音频和关联 hash 清单。目标须不存在且位于 live GraMem 数据目录之外。旧 backup / Store.backup 仅含 SQLite；FalkorDB、Hermes 会话/配置/凭据、Context 索引需另外覆盖。

恢复在新私有目录演练：校验 manifest、原件 hash、SQLite integrity/foreign keys、目录 700/文件 600。停全部写入进程、另存当前快照后才切换匹配的代码/配置/数据库/原件及图。schema 8 回退旧版本必须恢复对应旧库，不能只回退代码；快照后的新数据需保存并规划迁回。移动 home 改变 namespace，需显式迁移图。

旧备份包含当时的排除状态和原件，恢复前核对之后的遗忘/停用；恢复不是重新授权。无一键 restore CLI。最近发布快照及覆盖边界见2.5 语音原件部署（部署记录，未随仓库发布）。

## 开发与升级验证

```sh
python -m pip install -e '.[dev]'
python -m pytest tests/v2 -q
ruff check gramem tests/v2 __init__.py scripts integrations
```

按变更选择检查，避免把生产写入脚本当巡检：

| 检查 | 范围 |
|---|---|
| `tests/v2` | 临时库、假模型；真实图项须 GRAMEM_TEST_GRAPH_URL，使用临时 namespace |
| `verify_hermes.py`（私有部署） | 原生身份/工具/压缩/附件集成，临时 homes 与图 namespace |
| `verify_knowledge.py`（私有部署） | 临时库 OCR、真实模型/embedding、原件与 ZIP，可能计费 |
| `verify_control_panel.py`（私有部署） | 隔离引擎/API 与线上认证只读查询 |
| `verify_chat_audio.py`（私有部署） | 只读真实历史/缓存，临时档案验证音频与 ZIP 恢复，无新 TTS/ASR |
| `verify_chat_live.py`（私有部署） | 生产认证只读查询、聊天/语音/ZIP hash、匿名/profile 拒绝 |
| `verify_knowledge_live.py`（私有部署） | 固定已入库说明的字节与分块，文档换版本需同步断言 |
| `verify_production.py` / `verify_category_matrix.py` / `verify_integrity.py`（私有部署） | 生产写入或真实资料回填与模型调用，有操作副作用 |

`verify_runtime.py`（私有部署） 初始化真实 provider，不能视为隔离库检查。2.5 服务器隔离验收为 243 passed，含真实 FalkorDB；历史语音关联与 ZIP 恢复通过，具体范围见[能力](capabilities.md)。

引擎/配置/凭据变化统一更新 Gateway、面板和知识 worker。面板从 `integrations/control-panel/` 主源码同步到各副本。升级检查五个工具、实际作者、profile secrets、压缩 checkpoint、附件授权、聊天来源/撤销同步和原生发现。纯 Markdown 同步不重启、不刷新会话；更新本地说明不会自动替换知识库中已保存的原件版本。

## 关系补齐与图持久化

实例知识 worker 包含 Relations.process_one：metadata.relation_extraction.revision=1 表示完成，count=0 也是正常结果；retry_at 是 300 秒租约/退避。先看事实有效性、来源、模型和待处理标记，再看图 outbox。没有批量关系重试 CLI，不以清 metadata 绕过保护。

部署 Compose 保留 EFFECTS_THRESHOLD 0 与 json-file 20m × 3，防止已复现的查询 AOF 回放错误和日志满盘。standalone RDB 在 appendonly=no 的隔离种子加载后再启用/rewrite AOF；不要直接删除日志后 appendonly=yes 启动。活动图卷及旧故障取证分别保留。见图修复。

本次运行核对有两条 failed 来源，具体统计见当前状态，没有为文档整理重排。接口修改后执行 python scripts/refresh_reference.py，更新工具/HTTP/默认配置 JSON，并同步响应和权限说明。
