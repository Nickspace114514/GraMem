# GraMem 文件知识库

现行 GraMem 2.5.0 / schema 8 / 面板 1.7.0，核对日期 2026-10-04。文件功能自 2.1 引入，以下描述当前实现。

知识库由长期原件、可定位的文本索引和 GraMem 记忆组成。原件与索引共用 profile 和 principal 范围；每条分块是带 `document_id`、文件名、版本、页码、解析方法的 `knowledge` 记忆。资料是检索证据，不是系统指令。

## 使用

管理面板的“知识库”支持多文件上传、图片说明、文件名查询、内容检索、阅读、历史版本、下载原件、解析重试、停用和遗忘。上传返回 `queued` 表示原件保存完成；`ready` 才表示文字已解析，`partial` 表示存在明确列出的解析限制。语义向量由后台逐块补齐，全文检索可先使用。

agent 的 `gramem_knowledge` 工具支持 `search/list/get/read/import/export/retry/forget/suppress/reactivate`。使用文件时先检索，再按 ID 阅读或导出原件。`read.start` 为零起始分块序号；`list.page` 为一起始页码。`historical=true` 可检索旧版本。`export` 将原件复制到当前 profile 的私有下载缓存，并返回路径供现有 Hermes 文件/图片工具继续使用；不会自行发送消息。模型导入本地文件必须有当前用户的明确路径和导入意图，并经过 Hermes 的文件读取保护。

```sh
gramem --home /path/to/profile ingest ./资料.pdf
gramem --home /path/to/profile knowledge list
gramem --home /path/to/profile knowledge search '项目架构'
gramem --home /path/to/profile knowledge read DOCUMENT_ID --start 0
gramem --home /path/to/profile knowledge export DOCUMENT_ID --destination ./原件.pdf
gramem --home /path/to/profile knowledge backup --destination ./知识库备份.zip
gramem --home /path/to/profile suppress document:DOCUMENT_ID
gramem --home /path/to/profile reactivate document:DOCUMENT_ID
gramem --home /path/to/profile forget document:DOCUMENT_ID
```

CLI Owner 操作仍要求 `trusted_cli_owner=true`。普通 CLI 的模型凭据来自环境；宿主 worker 通过原生 profile 凭据解析器取得密钥，不复制或导出密钥。

## 渠道附件

`knowledge_auto_archive=true` 默认开启。原生 `pre_gateway_dispatch` 钩子只接收 adapter 的真实附件元数据；归档前再次执行 Gateway 同一授权检查，并要求账号已绑定为 Owner。文本中出现的路径不会触发自动归档。仅处理当前运行/传输 profile 的文档或图片缓存，拒绝远程 URL、越界路径、机器人、未知身份和被拒绝的路由。群聊/频道只在 `capture_owner_in_groups=true` 时保存 Owner 附件到其私人库；私人资料不会在群聊检索。

包含“不要保存”、仅本次使用或遗忘意图的附件消息跳过自动归档。有未解除的 GraMem 排除时暂停新导入。普通联系人的附件不自动长期保存；管理员可在相应既有身份范围显式导入。

这个钩子依赖当前 Hermes 的授权与 profile 解析 helper；缺少 helper 时跳过归档。升级 Hermes 后需运行集成检查。无需修改 Hermes 核心。

## 存储与版本

- 当前 SQLite schema 8 包含自 schema 4 引入的 `knowledge_documents` 与 `knowledge_chunks`；Store 支持新库与 schema 2–8，迁移保留原件元数据与记忆。
- 原件位于 GraMem 数据库同目录的 `knowledge/blobs/<前两位>/<opaque document ID>.blob`；目录权限 700，文件 600。写入经临时文件、fsync、原子替换；解析与文件操作使用 profile 的跨进程锁。
- SHA-256 按字节去重，身份范围独立；同身份上传同字节（包括改名）返回原记录。同一文件名、不同字节生成新版本，旧原件继续保留。导入并非覆盖磁盘文件。
- 只有新版本成功索引后，旧版本分块才转为历史；乱序完成的 worker 不会使旧版本重新成为当前版本。失败的新版本不删除旧的可用索引。
- 分块的记忆衰减设为零，资料不会因无人问起而自动消失；仍遵循显式排除。检索预算沿用 GraMem，自动召回附上来源。
- 既有旧式文档导入的文本记录继续有效，但原件当时未留存，无法重建。需重新上传原件才能获得文件下载与版本管理。

## 解析与检索

支持 UTF-8 TXT/MD/CSV/JSON、PDF、DOCX 和 PNG/JPEG/WebP/GIF/TIFF/BMP。单文件上限 20,000,000 字节；PDF 至多 200 页，提取文本至多 2,000,000 字符、5,000 分块，图片至多 2,500 万像素。

PDF 优先提取已有文本，对没有文本的页面调用 Poppler 和 Tesseract。每份 PDF 最多 OCR 30 页，处理预算 10 分钟；达到限制会显示 partial，不会假称完整。DOCX 提取段落和表格，不虚构 Word 页码。多帧图片只索引首帧并显示限制。图片 OCR 识别文字；没有文字的照片/插图可用文件名和用户说明检索，导出后交给视觉模型使用。尚未实现自动视觉描述或以图搜图，也不提取 PDF/Word 内嵌图片中的语义。

Python 解析组件安装 `gramem[documents]`；本地 OCR 需要 Tesseract、中文/英文语言包及 Poppler。部署实例已安装简体中文、繁体中文、英文语言包；默认 `knowledge_ocr_languages=chi_sim+eng`，繁体资料可改为 `chi_tra+eng`，避免同时启用两种中文包造成不必要的字符转换。参考 [Tesseract 命令用法](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html)。

解析任务以 SQLite 状态和 lease 持久保存。worker 崩溃后可在 lease 到期后恢复。`failed/needs_parser/empty` 的文件保留原件并允许重试；不把解析失败当作成功入库。文本中检测到凭据材料时会阻止导入；解析后发现凭据则遗忘该原件。解析提交重新核对权限、lease 和排除 epoch，防止解析期间的遗忘导致内容复活。

全文索引使用已有中文分词规则；向量索引使用当前配置的 embedding 模型与空间。后台每次补一个向量，失败退避，模型空间变更后重新补齐。发送到 embedding 服务前核对排除；私有原件始终留在本机，文本分块按已有模型配置发往服务。检索返回文件、版本、页码、分块、OCR/原文标记；导入不自动抽取实体关系图。

## 生命周期与备份

`document:<ID>` 是整份文件版本的生命周期槽位。停用后原件下载、分块、普通记忆召回和派生事实一起隐藏；解除后可再次使用。遗忘文件或任一分块时删除整份版本的原件，擦除文档来源和分块内容/向量，并沿 GraMem 来源链清理派生记忆、排队删除图记录。

遗忘一个版本不会自动删除其他版本。面板明确标示当前版本；需要遗忘全部版本时应枚举历史并逐一操作。重新授权只允许新内容，不恢复被遗忘的字节。遗忘不覆盖渠道历史、Hermes 缓存/日志、已导出的副本、旧系统或此前备份；不承诺磁盘取证级物理擦除。

`Knowledge.backup()` 或控制台备份生成 mode-600 ZIP，包含一致性 SQLite、所有仍保留的原件及 SHA-256/大小清单。备份时阻止资料写入和原件删除；FalkorDB 仍需独立备份。恢复应停服务后，在新的数据目录解压 `memory.sqlite` 与 `knowledge/`，核对 manifest 与权限，再切换运行目录。恢复旧备份也会恢复其当时的数据与排除状态，需要先核对后续遗忘要求。不要覆盖运行中的数据库。

部署实例的 `gramem-knowledge-worker.service` 独立处理资料解析/embedding，控制台没有用户会话时也会继续工作。通用安装可运行 `gramem --home ... knowledge-worker`（模型密钥需可用）；部署实例可用自带的 worker 封装接入宿主凭据。

## 验证

新增测试覆盖原件重启留存、去重与范围隔离、版本与乱序 worker、失败恢复、OCR/页码、Word 表格、文件/分块遗忘、停用的派生事实、解析期间遗忘、持久队列恢复、embedding 前排除、ZIP 备份、API 上传/下载/检索/身份隔离、原生渠道授权与私有工具导出。私有验收脚本在隔离库验证真实中文 OCR、扫描 PDF、真实 embedding、原件导出、备份恢复与文件删除，不写生产测试记忆。

2.1.1 默认自动审批：后台 worker 定期执行 review_one，旧 awaiting_confirm/review 候选也会自动处理。模型故障保留候选并自动退避重试，最长间隔一小时，无需人工批准；查看 metadata.auto_review.error。配置变更须重启三个服务。
