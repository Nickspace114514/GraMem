# 部署与使用教程

[English](quickstart.md) | [简体中文](quickstart.zh-CN.md)

本教程分四个层级，从零带你跑起 GraMem。按需要停在某一层即可。

| 层级 | 得到什么 | 需要什么 |
|---|---|---|
| 1. 独立命令行 | 存储、召回、遗忘、导入文件、备份 | Python 3.12+ |
| 2. 接入模型 | 从对话中自动提取记忆、语义检索 | 第 1 层 + OpenAI 兼容的 API 密钥 |
| 3. 图 | 关系召回与记忆网 | 第 2 层 + Docker（FalkorDB） |
| 4. Hermes Agent | 智能体内的记忆 provider 与管理控制台 | 第 3 层 + Hermes Agent |

文中的 **profile home** 指 GraMem 存放全部数据的目录（下面用 `~/gramem-home`）。接入 Hermes 时，它就是对应 profile 自己的 home，例如 `~/.hermes`。

## 第 1 层：独立命令行

```sh
git clone https://github.com/Nickspace114514/GraMem.git
cd GraMem
python -m venv .venv && . .venv/bin/activate
pip install -e .
```

创建 profile home 和最小配置。目录保持私有（700），配置只允许自己读写（600）：

```sh
export GRAMEM_HOME=~/gramem-home
mkdir -p "$GRAMEM_HOME/gramem" && chmod 700 "$GRAMEM_HOME"
cat > "$GRAMEM_HOME/gramem/config.json" <<'JSON'
{
  "owner_id": "me",
  "trusted_cli_owner": true,
  "timezone": "Asia/Shanghai"
}
JSON
chmod 600 "$GRAMEM_HOME/gramem/config.json"
```

`owner_id` 是记忆所属者的稳定 ID。`trusted_cli_owner` 把本机命令行映射为该所属者，只应在你信任的机器上开启。`config.json` 中的未知键会被拒绝，能及早发现拼写错误。

试一试：

```sh
gramem --home "$GRAMEM_HOME" remember "我喜欢简洁的回答" --type preference
gramem --home "$GRAMEM_HOME" recall "回答"
gramem --home "$GRAMEM_HOME" ingest ./notes.pdf          # PDF、DOCX、文本或图片
gramem --home "$GRAMEM_HOME" status
gramem --home "$GRAMEM_HOME" backup ./backup-dir
```

`recall` 返回智能体实际会收到的有界上下文，并带有每条记忆的层级、类型、强度和版本。`gramem --help` 可查看全部命令（`forget`、`suppress`、`reactivate`、`reauthorize`、`confirm`、`reject`、`chats`、`knowledge`、`network`、`graph`、`import` 等）。

扫描版 PDF 和图片需要 OCR：安装 Tesseract 及所需语言包，再装 Poppler。Debian / Ubuntu：`sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-sim poppler-utils`。`knowledge_ocr_languages`（默认 `chi_sim+eng`）要与已安装的语言包一致。

## 第 2 层：接入模型

GraMem 可对接任何 OpenAI 兼容的 Chat Completions 与 embeddings 接口。API 密钥从环境变量读取，不会写进 `config.json`。

```sh
export DASHSCOPE_API_KEY=你的密钥        # 变量名由 "api_key_env" 决定
```

在 `config.json` 中加入：

```json
{
  "owner_id": "me",
  "trusted_cli_owner": true,
  "timezone": "Asia/Shanghai",
  "model": "qwen3.8-flash",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "api_key_env": "DASHSCOPE_API_KEY",
  "embedding_model": "text-embedding-v4",
  "embedding_dimensions": 1024
}
```

- 换用其他服务商，修改 `base_url`、`model` 和 `api_key_env` 即可。
- `embedding_model` 留空则只用全文检索。
- 之后若更换向量模型或维度，请同时修改 `embedding_revision`，旧向量不会与新向量混算。
- `model` 为空时 GraMem 不发起任何网络请求，也无法自动提取记忆，但 `remember` 与 `ingest` 仍可使用。

全部字段与默认值见 [configuration.md](configuration.md) 和 [config-defaults.json](config-defaults.json)，起步可参考 [integrations/hermes/config.example.json](../integrations/hermes/config.example.json)。

提取、审核、文件解析、向量、聊天处理和图同步都通过同一个持久后台队列运行。Hermes 在智能体活跃时会处理队列；除此之外，请自己运行一个 worker：

```sh
gramem --home "$GRAMEM_HOME" worker            # 处理队列，并每天维护、定期反思归纳
gramem --home "$GRAMEM_HOME" knowledge-worker  # 处理同一个队列，不做上述周期任务
```

每个 profile 一个 worker 就够了。没有其他组件负责维护时用 `worker`；宿主已经负责维护时，旁边用 `knowledge-worker`。

## 第 3 层：加上图

图是独立的 FalkorDB 投影。SQLite 始终是权威；图不可用时召回照常工作，图稍后会追平。

```sh
docker compose up -d --wait
```

仓库自带的 [compose.yaml](../compose.yaml) 固定 FalkorDB v4.12.0，只绑定 `127.0.0.1:6380`，用命名卷与 AOF 持久化，内存上限 2 GiB。默认 `graph_url`（`redis://127.0.0.1:6380/0`）已与之匹配。若图需要密码，设置 `GRAMEM_GRAPH_PASSWORD`（或 `graph_password_env` 指定的变量）。没有私有网络和认证时，不要把端口暴露到本机之外。

验证：

```sh
gramem --home "$GRAMEM_HOME" maintain       # 执行生命周期变更并同步图
gramem --home "$GRAMEM_HOME" graph "me"     # 查询某个实体周围的关系
```

每个 profile 有独立的图命名空间（`graph_name` 加 profile home 的哈希），多个 profile 可以共用一个 FalkorDB。

## 第 4 层：接入 Hermes Agent

1. 把 GraMem 装进 Hermes 所用的同一个 Python 环境（在那里执行 `pip install -e .`），或把 `__init__.py`、`plugin.yaml`、`pyproject.toml` 和 `gramem/` 复制到 `<profile-home>/plugins/gramem/`。目录插件与 pip 入口点择一，不要同时使用。
2. 把 `config.json` 放在 `<profile-home>/gramem/config.json`，API 密钥通过 Hermes 的 secret 机制设置。
3. 合并下面的内容到 profile 配置，保留其他设置：

   ```yaml
   memory:
     provider: gramem
     memory_enabled: false
     user_profile_enabled: false
   plugins:
     enabled:
       - gramem
   ```

4. 把你的各渠道账号关联到所属者，使每个渠道都使用同一个人的记忆。在 `config.json` 中：

   ```json
   "aliases": {
     "email:you@example.com": "me",
     "telegram:123456789": "me"
   }
   ```

   只列出传输层已核实的身份。群聊使用独立的记忆空间，不会读取所属者的私人记忆。
5. 重启智能体。此时智能体拥有 `gramem_memory`、`gramem_recall`、`gramem_knowledge`、`gramem_chats`、`gramem_network` 五个工具。

### 管理控制台（可选）

把 `integrations/control-panel/` 复制到 `<profile-home>/plugins/hermes-control/`，执行 `hermes plugins enable hermes-control` 并重启 dashboard。控制台入口为 `/control`，使用宿主自己的 dashboard 认证。页面说明见[控制台指南](../integrations/control-panel/USER-GUIDE.md)，接口见 [REST 手册](control-panel.md)。

### 让 worker 常驻（systemd 示例）

在 Linux 上以用户服务运行 worker，按需调整路径：

```ini
# ~/.config/systemd/user/gramem-knowledge-worker.service
[Unit]
Description=GraMem knowledge worker

[Service]
ExecStart=%h/GraMem/.venv/bin/gramem --home %h/gramem-home knowledge-worker
EnvironmentFile=%h/gramem-home/.env
Restart=on-failure

[Install]
WantedBy=default.target
```

把 `DASHSCOPE_API_KEY=...` 写进该 `.env` 并设为 `chmod 600`，然后执行 `systemctl --user enable --now gramem-knowledge-worker.service`。如果宿主上没有别的组件做周期维护，把 `ExecStart` 里的 `knowledge-worker` 换成 `worker`。

## 日常运维

- **备份**：`gramem --home "$GRAMEM_HOME" backup DEST`。如果同时使用图，输出里会有 `graph_backup_required: true`，需要另外备份 FalkorDB 卷。请在安静时段备份，或先停掉写入方。
- **升级**：先备份，停止所有写入方（智能体、控制台、worker），更新代码，再一起启动。存储层会在事务内迁移 schema。旧版本无法打开新 schema，若可能回退，请保留备份和对应的旧代码。细节见 [deployment.md](deployment.md)。
- **遗忘**：`forget`、`suppress`、`reactivate`、`reauthorize` 作用于记忆及其全部派生内容；不会清除你之前导出的副本、宿主日志或更早的备份。
- **排错**：`gramem --home "$GRAMEM_HOME" status` 可看到排队和失败的任务；`processor_available: false` 表示没有配置模型或模型不可达；配置里有未知键时，加载会失败并在信息里给出键名。

## 下一步

[架构](../ARCHITECTURE.md)、[接口](interfaces.md)、[维护](maintenance.md)、[知识库](knowledge-base.md)、[聊天档案与记忆网](chat-network.md)。
