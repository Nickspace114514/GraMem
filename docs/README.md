# GraMem 文档索引

更新：2026-10-14。GraMem 2.5.0 / schema 8 / 控制台 1.8.1。

## 当前手册

| 文档 | 内容 |
|---|---|
| [部署与使用教程](quickstart.zh-CN.md)（[English](quickstart.md)） | 从独立命令行到 Hermes 接入的分层教程 |
| [项目入口](../README.md)、[项目说明](project.md) | 功能、边界、接入 |
| [架构](../ARCHITECTURE.md) | 模块、表、事务、租约、身份与来源 |
| [使用指南](user-guide.md) | 记忆、文件、档案、音频、控制台 |
| [接口](interfaces.md) | 五工具、CLI、Python 和宿主回调 |
| [REST](control-panel.md) | 认证、profile/scope、参数、返回、错误 |
| [契约索引](api-reference.md) | 五工具和 31 个 REST 操作 |
| [工具 Schema](tool-schemas.json)、[OpenAPI](openapi.json) | 源码生成 JSON；HTTP 不含宿主认证/profile 中间件 |
| [配置](configuration.md)、[默认 JSON](config-defaults.json) | 全部字段、默认值及实例差异 |
| [部署](deployment.md)、[维护](maintenance.md) | 安装、迁移、巡检、队列、图和恢复 |
| [知识库](knowledge-base.md) | 原件、解析、版本和导出 |
| [聊天与记忆网](chat-network.md) | 回填、分页、撤销、语音、事件及权重 |
| [自动审核](automatic-approval.md) | 提取审批、候选、租约和退避 |
| [能力与验收](capabilities.md) | 实现、历史验证和限制 |
| [面板组件](../integrations/control-panel/README.md)、[页面指南](../integrations/control-panel/USER-GUIDE.md) | 管理页面和部署 |

## 历史与设计

- [2026-10-13 关系补齐](relationship-enrichment-20261013.md)；图持久化修复。
- 2026-10-08 跨平台/分页/身份迁移；官方模型与面板管理。
- [2026-10-06 OpenRouter 迁移](openrouter-migration-20261006.md)，后来已切回官方渠道。
- 2.5 音频（部署记录，未随仓库发布）；[2.4.1 修复](context-gramem-fixes-20261004.md)/部署（部署记录，未随仓库发布）。
- 2.4 历史任务（部署记录，未随仓库发布）；2.3 权重（部署记录，未随仓库发布）；2.2 聊天网络（部署记录，未随仓库发布）。
- [2026-10-03 修复](review-fixes-20261003.md)；旧部署（部署记录，未随仓库发布）。
- 完整性（部署记录，未随仓库发布）、项目审查（部署记录，未随仓库发布）、[四项修复](review-fixes-20261002.md)、[图优化](graph-improvements-20261002.md)、会话刷新（部署记录，未随仓库发布）。
- [原始设计输入](original-memory-design.md)、整理前手册（整理前快照，未随仓库发布）。

历史计数/版本/状态代表当次检查，部署时间线未随仓库发布。

## 更新

功能变化同步接口/配置/架构；工具、REST、默认字段变化运行 python scripts/refresh_reference.py 生成三个 JSON 契约，再校对响应/权限手册。发布追加日期证据，保留旧结果。主面板从 integrations/control-panel 同步部署副本；凭据、原件和日志不放文档包。纯文档不重启，不刷新会话，不替换已入库原件。
