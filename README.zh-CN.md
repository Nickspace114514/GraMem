# GraMem

[English](README.md) | [简体中文](README.zh-CN.md)

[![CI](https://github.com/Nickspace114514/GraMem/actions/workflows/ci.yml/badge.svg)](https://github.com/Nickspace114514/GraMem/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-%E2%89%A53.12-blue)

**面向 AI Agent 的长期记忆引擎：每条事实有来源，遗忘真正生效，并带有时序知识图。**

GraMem 记录用户说过什么、出自哪里、现在还能不能被使用。它既是 [Hermes Agent](#接入-hermes-agent) 的原生 `MemoryProvider`，也能作为独立的 Python 库和命令行工具使用。SQLite 是事务与可见性的唯一权威；FalkorDB 是可选的独立关系投影，用于关系召回；文档、聊天原件和助手音频保存在你自己机器上的私人目录。

## 特点

- **事实有来源**：记忆保留证据、版本历史和置信度，能回答"智能体为什么这么认为"。
- **遗忘真正生效**：停用、遗忘、解除停用和重新授权会同步到原件、派生事实、画像和图，不会从旁路泄露。
- **有界召回**：Always / Relevant / Historical 三层，中文全文检索、可选向量检索与图扩展，全部限定在 token 预算内（默认 1024）。
- **身份与范围**：Owner / Contact / Group 空间，按 profile 隔离，已核实的跨渠道账号关联。
- **知识库与聊天档案**：PDF / DOCX / 文本 / 图片原件，支持版本、OCR、分块与页码定位、搜索、导出与 ZIP；双方聊天带哈希、摘要与主题时间线。
- **可见的记忆网**：事实、文件、聊天、音频、主题和事件组成带权重、按时间排序的图。
- **默认私有**：没有遥测，唯一的外部请求是发往你配置的 OpenAI 兼容端点（`base_url`，默认 DashScope，可换成任何兼容服务）。不设置 `model` 时不会向外发送任何内容。

## 快速上手（无需 Docker 和 API 密钥）

需要 Python 3.12 或更高版本。

```sh
git clone https://github.com/Nickspace114514/GraMem.git
cd GraMem
python -m venv .venv && . .venv/bin/activate
pip install -e .

mkdir -p ~/gramem-home/gramem && chmod 700 ~/gramem-home
echo '{"owner_id": "me", "trusted_cli_owner": true}' > ~/gramem-home/gramem/config.json

gramem --home ~/gramem-home remember "我喜欢简洁的回答" --type preference
gramem --home ~/gramem-home recall "回答"
gramem --home ~/gramem-home ingest ./some-document.pdf
gramem --home ~/gramem-home status
```

从对话中自动提取、向量检索和图需要模型端点，图还需要 FalkorDB。完整步骤见[部署与使用教程](docs/quickstart.zh-CN.md)。

## 接入 Hermes Agent

GraMem 通过 `hermes_agent.memory_providers` 入口点注册。把下面的内容合并进你的 profile 配置（不要覆盖已有项）：

```yaml
memory:
  provider: gramem
  memory_enabled: false
  user_profile_enabled: false
plugins:
  enabled:
    - gramem
```

接入后智能体获得五个工具：`gramem_memory`、`gramem_recall`、`gramem_knowledge`、`gramem_chats`、`gramem_network`。可选的管理控制台在 [`integrations/control-panel`](integrations/control-panel/README.md)。

## 文档

| 我想…… | 阅读 |
|---|---|
| 安装、配置并运行 | [部署与使用教程](docs/quickstart.zh-CN.md)（[English](docs/quickstart.md)） |
| 了解模块、数据库与事务 | [架构](ARCHITECTURE.md) |
| 查看全部配置字段 | [配置](docs/configuration.md)、[默认 JSON](docs/config-defaults.json) |
| 调用工具、CLI 和 Python 接口 | [接口](docs/interfaces.md)、[工具 Schema](docs/tool-schemas.json) |
| 使用管理 REST 接口 | [控制台接口](docs/control-panel.md)、[OpenAPI](docs/openapi.json) |
| 运维、备份与恢复 | [维护](docs/maintenance.md)、[部署参考](docs/deployment.md) |
| 浏览其余文档 | [文档索引](docs/README.md) |

## 开发

```sh
pip install -e '.[dev]'
python -m pytest tests/v2 -q
ruff check .
```

另有 4 个图测试需要 `GRAMEM_TEST_GRAPH_URL` 指向一次性 FalkorDB 才会运行（例如 `docker compose up -d --wait` 后使用 `redis://127.0.0.1:6380/0`）。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 需要了解的限制

- 遗忘不会擦除宿主的聊天历史、日志、你已导出的副本和旧备份。恢复备份后需要重新核对之后的排除。
- 图片自动描述和以图搜图尚未实现；向量检索随记忆数量线性增长（个人规模无碍）；`NEXT` 关系表示时间顺序，不表示因果。
- OCR 需要系统安装 Tesseract、对应语言包和 Poppler。

## 安全

请私下报告漏洞，见 [SECURITY.md](SECURITY.md)。

## 许可证

[GNU Affero General Public License v3.0](LICENSE)。若你把修改后的版本作为网络服务运行，AGPL 要求你向该服务的用户提供其源码。
