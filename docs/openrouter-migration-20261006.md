# OpenRouter 迁移：2026-10-06

实例 `<HERMES_HOME>` 的 GraMem 文本、向量调用均迁至 `https://openrouter.ai/api/v1`，凭据由原生 `get_env_value('OPENROUTER_API_KEY')` 按 profile 解析，不复制到代码或配置。通用 Config 的原有 DashScope 默认地址保持向后兼容；本次发布使用显式 OpenRouter 配置。

| 字段 | 本实例 | 行为 |
|---|---|---|
| model | qwen/qwen3.8-flash | 记忆提取、控制分类、画像等文本处理 |
| provider_preference | price | OpenRouter 文本请求的 provider.sort |
| embedding_model | qwen/qwen3-embedding-8b | 替换 text-embedding-v4 |
| embedding_dimensions | 1024 | 实测 API 返回 1024 维；不截取旧向量 |
| embedding_provider_preference | throughput | 向量召回处于回复前的路径，优先吞吐量 |
| embedding_revision | openrouter-qwen3-8b-20261006 | 新空间与旧空间隔离 |

新增的两种 preference 均只接受 `price` / `throughput`。仅当 base_url 的 hostname 是 `openrouter.ai` 时发送 provider 对象；文本还发送 reasoning.enabled=false 与 JSON 输出要求，原有兼容供应商行为保持。独立 worker 使用原生 scoped credential resolver；独立 CLI 仍使用配置指定的环境变量。

先离线准备线上 20 条记忆的向量，再在停止 gateway、worker、控制面板后核对每条 ID 与内容 SHA256，并在单个 SQLite 事务中只替换 embedding、embedding_space。字段级校验确认内容、身份、生命周期、来源、访问次数、版本均保留。检索继续使用全文、向量、图的现有融合逻辑。新模型检索质量与旧模型是否等价尚未做标注集评测；本次验收确认接口、维度、完整迁移及原有作用域隔离。

修改源为 `gramem/config.py`、`gramem/model.py`、`tests/v2/test_model.py` 和 `integrations/control-panel/dashboard/dist/index.js`，面板的部署副本同步。语音识别与 Qwen TTS 已脱离 GraMem 的凭据/地址配置，因此记忆迁移不会改动音频供应商。

模型/原生 provider 相关 45 项测试通过。更宽的 v2 测试在新增路由测试前为 237 通过、4 跳过、2 失败：本地开发环境缺少 Pillow；512-token memory_net 输出为空的断言失败。后者已用发布前 Config/Model 在独立副本重现，属于既有预算问题。本次不修改其实现。真实 OpenRouter JSON 提取、1024 维 embedding、全部 20 条迁移、worker 启动通过。

回滚需静默排空并停止相关服务，恢复配置与两个模型源文件。若回到旧 embedding 模型，应重新计算当前事实的旧模型向量或只恢复核对过内容的旧向量列；不要覆盖整个线上记忆数据库或 state.db。

跨组件部署证据与备份见 Hermes 迁移记录。接口依据：[OpenRouter embeddings](https://openrouter.ai/docs/api/api-reference/embeddings/submit-an-embedding-request)、[Qwen3 Embedding 8B](https://openrouter.ai/qwen/qwen3-embedding-8b)、[provider routing](https://openrouter.ai/docs/guides/routing/provider-selection)。
