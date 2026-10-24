# 部署手册

现行 **GraMem 2.5.0 / SQLite schema 8 / 面板 1.8.1**，核对日期 2026-10-14，Asia/Singapore。本文说明安装与升级；日常操作见[维护](maintenance.md)，历次结果见[文档索引](README.md)的历史区。

## 通用安装

1. 准备 Python ≥3.12 和支持原生 MemoryProvider 的 Hermes。选择 profile home，按可信 transport 核实 Owner / aliases；不同 profile 分开配置、数据库及图 namespace。
2. 在本仓库运行图服务：

   ```sh
   docker compose up -d --wait
   ```

   compose 固定 FalkorDB v4.12.0 与 digest，只绑定 `127.0.0.1:6380`，命名卷持久化、AOF、默认内存上限 2 GiB；EFFECTS_THRESHOLD 0，json-file 轮转 20m × 3。跨机地址需配私网和认证。
3. 将根入口 `__init__.py`、`plugin.yaml`、`pyproject.toml` 和 `gramem/` 保持结构放入 `<profile-home>/plugins/gramem/`。目录插件与 pip entry point 择一；保留显式 `register_memory_provider`。实例 CLI wrapper 使用 `scripts/`，部署时同时保存所需脚本与文档。
4. 复制[配置示例](../integrations/hermes/config.example.json)到 `<profile-home>/gramem/config.json`，填写身份、模型、embedding 与图地址。home/原件目录 700，私人配置和数据文件 600；API 密钥通过 Hermes secrets 设置，CLI 从环境读取。
5. 通过 Hermes 当前 managed package transaction 安装主依赖。系统 Python 或独立测试 venv 的安装不能代替宿主实际运行环境。PDF/DOCX/Pillow 是主依赖；OCR 另需 Tesseract、语言包和 Poppler，例如 Debian/Ubuntu 的 `tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng poppler-utils`。
6. 合并 Hermes 配置，保留所需其他插件和 memory toolset：

   ```yaml
   memory:
     provider: gramem
     memory_enabled: false
     user_profile_enabled: false
   plugins:
     enabled:
       - gramem
   ```

   旧 Hindsight provider/MCP/toolset 项目在切换时停用。密钥由 `api_key_env` 引用。Qwen 使用严格文本 JSON 解析，默认关闭 thinking。
7. 如需管理界面，将 `integrations/control-panel/` 部署到默认 home 的 `plugins/hermes-control/`，按 Hermes 原生方式启用并重启 dashboard，入口 `/control`。所有 API 使用宿主管理员认证与 profile scope，见[面板接口](control-panel.md)。
8. 启动 Gateway、面板及选定的 worker，核对原生发现、五个工具、profile 身份和持久队列。Hermes provider 自带后台线程；没有活跃会话时仍需处理资料的实例运行受管理的常驻 `gramem --home <profile-home> knowledge-worker`。

首次 provider / 工具 schema 切换可能需要刷新已有会话保存的系统提示与工具名；先备份，在停写窗口通过宿主 SessionDB API 操作，逐字段验证消息及非缓存元数据。2.4.1 升级当时保留全部缓存；2.5 增加工具动作，在静默窗口刷新系统提示与工具名缓存，所有原生消息与非缓存元数据保留。纯文档变更无需重启或刷新缓存。

## 数据迁移与升级顺序

1. 核对源版本、当前 `PRAGMA user_version`、宿主接口和实际依赖环境，完成与变更相关的隔离验证。
2. 备份代码、配置、SQLite 一致性快照、原件、Context 索引、宿主会话与服务定义。知识 ZIP 包含 GraMem SQLite/原件/manifest，完整恢复还需 FalkorDB、宿主配置/会话与凭据。
3. 使用原生 drain 等待活跃工作归零，停止写入相关进程。部署代码与依赖完成后再统一启动，避免 Gateway、面板与 worker 混用版本。静默维护及 NAS 锁见实例部署指南。
4. Store 在事务中将新库或 schema 2–8 升到 8。schema 5 为聊天表，6 为回填任务，7 增加 `source_turns` 和 `chat_native_state`；schema 8 添加 chat_audio，保留聊天 JSON/hash、事实与排除。后台扫描补齐既有来源和原生有效状态。
5. 等待 Hermes 的源码依赖补全事务结束；如进程在补全前已启动，完成后统一刷新相关进程。确认加载路径/版本、配置、队列、认证 API、原件 hash 和来源过滤，再结束维护。

schema 8 不能由旧版 Store 打开。回退时先保存发布后的新数据，在停写窗口恢复相互匹配的旧代码、数据库、原件与配置；不能只换回旧源码。移动 home 会改变图 namespace，需要规划图迁移。JSON/JSONL 迁移默认候选，先导入排除；不会隐式导入旧后端或恢复用户已遗忘内容。

## 实例部署记录

具体主机、路径、端口、版本和备份位置属于部署私有记录，不随开源仓库发布。安装、升级与回退步骤见上文；各次实例验收与部署过程不在仓库内维护。

## 当前模型与关系/图扩展

默认 Chat/Embedding 模型与接口以面板“行为与模型”页面和 `docs/configuration.md` 为准。面板 1.8.1 固定官方模型保存，带 revision、备份及重载提示；换向量空间不自动迁移普通记忆的旧向量。

10 月 13 日新增 Relations 后台补齐（版本仍 2.5.0）及 EFFECTS_THRESHOLD 0 图回放修复。部署精确文件/Compose，不能认为同一版本号内容永远相同。发布前记录文件 hash，完整源码归属见维护清单。
