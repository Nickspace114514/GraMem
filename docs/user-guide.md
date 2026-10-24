# GraMem 使用指南

更新：2026-10-14。入口为 agent 私聊的五个原生工具，或管理员[控制台](http://<宿主地址>:8500/control)。

## 记忆与画像

对话中说明“记住/更新”并提供事实原话；查询可自然描述主题。自动提取、审核和画像在后台完成，模型不可用时保存任务。面板“记忆”可搜索、查看来源/版本、增加/修改/合并，画像页面可回到来源事实编辑。

停用保留内容但阻断使用；解除停用仅针对 suppressed。遗忘清对应槽位、派生和匹配原件；重新授权只允许未来新事实，不恢复旧值。范围不明确先澄清，历史模式仍服从排除。

## 知识库

上传后 queued 表示字节保存，ready/partial 表示解析结果；向量独立补齐。正文搜索和文件名/说明搜索不同，阅读结果可带页码/分块来源。支持 PDF/DOCX/文本/图片，最大 20,000,000 字节。

相同身份和字节去重；同名不同内容为新版本。导出原件保留真实字节，指定 ID 遗忘一个版本；删除任何知识分块会清理对应整份文档来源。失败先修 parser/OCR/磁盘再重试。详见[知识库](knowledge-base.md)。

## 档案与语音

按平台、会话、日期查双方原话，引用记录 ID/时间。工具 read 按 start/next 字符游标续读，直到 next=null；不要把 truncated 页当完整内容。面板支持原件 JSON 与音频包下载。

“一键处理全部未整理记录”覆盖选定身份启动前的可信私人历史，筛选不限制范围；重复请求复用，关闭页面继续。进度查询/重试不接管有效租约。禁提、撤销和 silent 保护仍有效。

音频为助手 TTS 原件，文案是合成证据，不是转写。可播放、单音频下载或包含聊天/音频/hash 的 ZIP；下载重新核对授权。详见[聊天网络](chat-network.md)。

## 关系和记忆网

关系图看实体/谓词/来源，记忆网看事实、资料、档案、摘要、主题、会话、事件和音频。可以展开 1–3 跳、查看历史/权重。NEXT 仅时间顺序，原始节点无评估时权重为 null。空图先查关系和健康，不直接重建数据。

## 管理配置

先选择 profile 和已有身份。账号关联须核实 transport，保存后影响后续识别，旧 Contact 数据须独立迁移。行为/模型设置带 revision；冲突重新加载。密钥单独设置，不返回旧值。

更换模型、维度或向量空间后重载 Gateway/面板/worker，旧向量不混用；知识向量后台重建，普通记忆不保证自动补齐。面板不管理 Hermes 主模型、渠道、SOUL 或 Cron。

## CLI 示例

可信本机开启 trusted_cli_owner，使用正确 home：

```sh
gramem --home /path/to/profile status
gramem --home /path/to/profile recall '部署方法'
gramem --home /path/to/profile knowledge list
gramem --home /path/to/profile knowledge search '架构'
gramem --home /path/to/profile chats progress
gramem --home /path/to/profile network 'GraMem' --hops 2
```

导出目标不能已存在。命令及参数见[接口](interfaces.md)，备份/恢复和队列问题见[维护](maintenance.md)，页面操作见[控制台指南](../integrations/control-panel/USER-GUIDE.md)。
