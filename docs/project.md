# GraMem 项目说明

更新：2026-10-14。引擎 2.5.0 / schema 8，控制台 1.8.1。

GraMem 为 Hermes 提供长期私人记忆和资料管理，不建立第二套对话宿主或远程 MCP 服务。MemoryProvider、可信本机 CLI/Python、宿主管理员 REST 共用同一 Engine、身份和来源控制。

## 功能与模块

| 功能 | 模块 | 结果 |
|---|---|---|
| 事实/来源/版本/生命周期 | engine/store/evidence | 持久任务、原话证据、冲突和可恢复处理 |
| 召回 | engine/model/graph/tokens | FTS/向量/来源图、总预算及实际交付强化 |
| 身份 | config/hermes/identity_migration | Owner/Contact/Group、profile 和可信账号关联 |
| 候选与画像 | approval/reflection | 自动审核、同槽整理、有来源画像 |
| 文件 | knowledge/knowledge_gateway | 原件、去重/版本、解析/OCR、分块、向量 |
| 聊天 | chats/chat_import/chat_backfill | 双方原话、批量历史、摘要、来源撤销 |
| 音频 | chat_audio | 助手合成音频原件与档案关联 |
| 网络 | network/graph/relations | 可见子图、事件/权重、关系后台补齐 |
| 管理 | cli / integrations/control-panel | 当前数据、模型、身份、队列和备份 |

助手回复可以进入档案，事实提取只用用户证据；显示名/模型判断不能绑定身份。群采集和群读取分别限制，允许 Owner 群内原话采集不开放私人召回。

## 限制和维护

SQLite 是可见性权威，图为投影，图失效不等于事实丢失。原生撤销通过可信扫描同步，通常一分钟；没有跨库即时事务。模型失败保留持久任务，不假标完成。

图片支持原件/OCR，自动描述、以图搜图、文档自动抽图未实现。线性向量和有界图用于个人规模；缺少权重表示未评估，NEXT 仅时间先后。

局部 ZIP 含 SQLite/文件/音频，完整恢复另需图、宿主、配置/凭据。旧备份不代表新授权，遗忘也不自动清理宿主或旧副本。日常见[使用](user-guide.md)，维护见[手册](maintenance.md)，详尽实现/验收见[能力](capabilities.md)。
