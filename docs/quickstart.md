# Deployment & usage guide

[English](quickstart.md) | [简体中文](quickstart.zh-CN.md)

This guide takes you from nothing to a working GraMem, in four levels. Stop at the level you need.

| Level | You get | You need |
|---|---|---|
| 1. Standalone CLI | Store, recall, forget, ingest files, back up | Python 3.12+ |
| 2. Model-backed | Automatic extraction from conversations, semantic search | Level 1 + an OpenAI-compatible API key |
| 3. Graph | Relationship recall and the memory network | Level 2 + Docker (FalkorDB) |
| 4. Hermes Agent | The memory provider inside your agent, plus the admin console | Level 3 + Hermes Agent |

Throughout, **profile home** means the directory GraMem keeps everything in (`~/gramem-home` below). With Hermes it is the profile's own home, for example `~/.hermes`.

## Level 1: standalone CLI

```sh
git clone https://github.com/Nickspace114514/GraMem.git
cd GraMem
python -m venv .venv && . .venv/bin/activate
pip install -e .
```

Create the profile home and a minimal config. Keep the directory private (700) and the config readable only by you (600):

```sh
export GRAMEM_HOME=~/gramem-home
mkdir -p "$GRAMEM_HOME/gramem" && chmod 700 "$GRAMEM_HOME"
cat > "$GRAMEM_HOME/gramem/config.json" <<'JSON'
{
  "owner_id": "me",
  "trusted_cli_owner": true,
  "timezone": "UTC"
}
JSON
chmod 600 "$GRAMEM_HOME/gramem/config.json"
```

`owner_id` is the stable ID of the person the memories belong to. `trusted_cli_owner` maps the local command line to that owner, so only enable it on a machine you trust. Unknown keys in `config.json` are rejected, which catches typos early.

Try it:

```sh
gramem --home "$GRAMEM_HOME" remember "I prefer concise answers" --type preference
gramem --home "$GRAMEM_HOME" recall "answers"
gramem --home "$GRAMEM_HOME" ingest ./notes.pdf          # PDF, DOCX, text or image
gramem --home "$GRAMEM_HOME" status
gramem --home "$GRAMEM_HOME" backup ./backup-dir
```

`recall` returns the bounded context an agent would receive, with each memory's tier, type, strength and version. Run `gramem --help` for the full command list (`forget`, `suppress`, `reactivate`, `reauthorize`, `confirm`, `reject`, `chats`, `knowledge`, `network`, `graph`, `import`, and more).

Scanned PDFs and images need OCR: install Tesseract with the language packs you want, plus Poppler. On Debian or Ubuntu: `sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-sim poppler-utils`. Set `knowledge_ocr_languages` (default `chi_sim+eng`) to match what you installed.

## Level 2: connect a model

GraMem talks to any OpenAI-compatible Chat Completions and embeddings API. The API key is read from an environment variable and is never stored in `config.json`.

```sh
export DASHSCOPE_API_KEY=your-key        # name is set by "api_key_env"
```

Add to `config.json`:

```json
{
  "owner_id": "me",
  "trusted_cli_owner": true,
  "timezone": "UTC",
  "model": "qwen3.8-flash",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "api_key_env": "DASHSCOPE_API_KEY",
  "embedding_model": "text-embedding-v4",
  "embedding_dimensions": 1024
}
```

- Use another provider by changing `base_url`, `model` and `api_key_env`.
- Leave `embedding_model` empty to use full-text search only.
- If you change the embedding model or dimensions later, also change `embedding_revision` so old vectors are never mixed with new ones.
- With `model` empty, GraMem makes no network calls and cannot extract memories automatically; `remember` and `ingest` still work.

All fields and defaults are in [configuration.md](configuration.md) and [config-defaults.json](config-defaults.json). A starting point is [integrations/hermes/config.example.json](../integrations/hermes/config.example.json).

Extraction, review, file parsing, embeddings, chat processing and graph sync all run through one durable background queue. Hermes drains it while the agent is active; outside that, run a worker yourself:

```sh
gramem --home "$GRAMEM_HOME" worker            # drains the queue, plus daily maintenance and periodic reflection
gramem --home "$GRAMEM_HOME" knowledge-worker  # drains the same queue, without the periodic jobs
```

One worker per profile is enough. Use `worker` when nothing else performs maintenance, and `knowledge-worker` next to a host that already does.

## Level 3: add the graph

The graph is an independent FalkorDB projection. SQLite stays authoritative; if the graph is down, recall falls back to the other tiers and the graph catches up later.

```sh
docker compose up -d --wait
```

The bundled [compose.yaml](../compose.yaml) pins FalkorDB v4.12.0, binds only `127.0.0.1:6380`, persists to a named volume with AOF, and caps memory at 2 GiB. The default `graph_url` (`redis://127.0.0.1:6380/0`) already matches. If your graph needs a password, set `GRAMEM_GRAPH_PASSWORD` (or the variable named by `graph_password_env`). Do not expose the port beyond localhost without a private network and authentication.

Check it:

```sh
gramem --home "$GRAMEM_HOME" maintain       # runs lifecycle changes and graph sync
gramem --home "$GRAMEM_HOME" graph "me"     # query relations around an entity
```

Each profile gets its own graph namespace (`graph_name` plus a hash of the profile home), so several profiles can share one FalkorDB.

## Level 4: use it with Hermes Agent

1. Install GraMem into the same Python environment Hermes runs in (`pip install -e .` there). Alternatively copy `__init__.py`, `plugin.yaml`, `pyproject.toml` and `gramem/` into `<profile-home>/plugins/gramem/`. Use either the directory plugin or the pip entry point, not both.
2. Put `config.json` at `<profile-home>/gramem/config.json`, and set the API key through Hermes' secret mechanism.
3. Merge this into the profile configuration, keeping your other settings:

   ```yaml
   memory:
     provider: gramem
     memory_enabled: false
     user_profile_enabled: false
   plugins:
     enabled:
       - gramem
   ```

4. Link your accounts to the owner so the right person's memory is used on every channel. In `config.json`:

   ```json
   "aliases": {
     "email:you@example.com": "me",
     "telegram:123456789": "me"
   }
   ```

   Only list identities your transport has verified. Group chats keep a separate memory space and never read the owner's private memories.
5. Restart the agent. The agent now has the tools `gramem_memory`, `gramem_recall`, `gramem_knowledge`, `gramem_chats` and `gramem_network`.

### Admin console (optional)

Copy `integrations/control-panel/` to `<profile-home>/plugins/hermes-control/`, run `hermes plugins enable hermes-control`, and restart the dashboard. The console is at `/control` and uses the host's own dashboard authentication. See the [console guide](../integrations/control-panel/USER-GUIDE.md) (Chinese) and [REST reference](control-panel.md).

### Keeping workers running (systemd example)

On Linux, run a worker as a user service. Adjust the paths:

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

Put `DASHSCOPE_API_KEY=...` in that `.env` file with `chmod 600`, then `systemctl --user enable --now gramem-knowledge-worker.service`. Swap `knowledge-worker` for `worker` in `ExecStart` if nothing else on the host runs the periodic maintenance.

## Operating it

- **Back up** with `gramem --home "$GRAMEM_HOME" backup DEST`. The output says `graph_backup_required: true` when you also use the graph; back up the FalkorDB volume as well. Stop writers or take the backup during a quiet moment.
- **Upgrade**: back up first, stop everything that writes (agent, console, workers), update the code, then start everything again together. The store migrates its schema inside a transaction. A newer schema cannot be opened by an older version, so keep the backup and the matching old code if you may need to roll back. Details in [deployment.md](deployment.md).
- **Forgetting**: `forget`, `suppress`, `reactivate` and `reauthorize` act on the memory and everything derived from it. They do not remove copies you exported earlier, host logs, or older backups.
- **Troubleshooting**: `gramem --home "$GRAMEM_HOME" status` shows queued and failed jobs. `processor_available: false` means no model is configured or reachable. Unknown config keys fail at load with the key name in the message.

## Where next

[Architecture](../ARCHITECTURE.md), [interfaces](interfaces.md), [maintenance](maintenance.md), [knowledge base](knowledge-base.md), [chat archive and memory network](chat-network.md).
