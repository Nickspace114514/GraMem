# 接口契约索引

核对日期：2026-10-14。此页及 JSON 契约由当前源码生成；操作说明见[接口手册](interfaces.md)和[管理员 REST](control-panel.md)。

## 模型工具

[tool-schemas.json](tool-schemas.json)包含五个工具的完整 JSON Schema。身份由宿主解析，不能传入任意 principal；参数/分页语义与手册共同维护。

| 工具 | 必填 | 参数 |
|---|---|---|
| `gramem_chats` | action | action, query, id, audio_id, platform, session, after, before, start |
| `gramem_network` |  | query, id, hops, historical |
| `gramem_knowledge` | action | action, query, id, path, title, description, start, page, historical |
| `gramem_recall` | query | query, historical, graph, hops |
| `gramem_memory` | action | action, id, content, evidence, type, slot, targets, group_safe |

## REST 路由

[openapi.json](openapi.json)记录插件路由参数、请求体及校验约束。宿主的认证/profile 中间件不在插件规范中；所有请求仍需管理员认证，并指定已有 profile，不能据此推断匿名入口。

成功响应主要是动态字典，未声明完整 response_model；OpenAPI 不能替代[响应与错误手册](control-panel.md)。

| 方法 | 路径 | 源码函数 |
|---|---|---|
| GET | `/overview` | `overview` |
| GET | `/settings` | `settings` |
| PUT | `/settings` | `save_settings` |
| GET | `/credentials` | `credentials` |
| GET | `/models` | `models` |
| PUT | `/models` | `save_models` |
| PUT | `/credentials` | `save_credential` |
| GET | `/memories` | `memories` |
| GET | `/recall` | `recall` |
| GET | `/graph` | `graph` |
| GET | `/profile` | `profile` |
| GET | `/queues` | `queues` |
| POST | `/operation` | `operation` |
| POST | `/import` | `import_data` |
| POST | `/knowledge/upload` | `document` |
| POST | `/document` | `document` |
| GET | `/knowledge` | `knowledge_list` |
| GET | `/knowledge/search` | `knowledge_search` |
| GET | `/knowledge/{id}/original` | `knowledge_original` |
| GET | `/knowledge/{id}` | `knowledge_read` |
| POST | `/knowledge/control` | `knowledge_control` |
| GET | `/chats/process` | `chats_processing_status` |
| POST | `/chats/process` | `chats_process_all` |
| POST | `/chats/process/retry` | `chats_processing_retry` |
| GET | `/chats/overview` | `chats_overview` |
| GET | `/chats` | `chats_search` |
| GET | `/chats/{id}/original` | `chat_original` |
| GET | `/chats/{id}/bundle` | `chat_original_bundle` |
| GET | `/chats/{id}/audio/{audio_id}/original` | `chat_audio_original` |
| GET | `/chats/{id}` | `chat_read` |
| GET | `/network` | `memory_net` |

## 配置与更新

[config-defaults.json](config-defaults.json)包含全部 Config 默认字段；实例显式值在[配置手册](configuration.md)与实例当前状态维护。

修改工具/路由/配置后运行 `python scripts/refresh_reference.py`，同步参数、响应、权限和使用说明。契约是源码快照，不是实时运行状态；生成过程不打开记忆库、不调用模型。
