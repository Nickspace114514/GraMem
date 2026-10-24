# GraMem

[English](README.md) | [简体中文](README.zh-CN.md)

[![CI](https://github.com/Nickspace114514/GraMem/actions/workflows/ci.yml/badge.svg)](https://github.com/Nickspace114514/GraMem/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-%E2%89%A53.12-blue)

**A long-term memory engine for AI agents, with sourced facts, forgetting you can trust, and a temporal knowledge graph.**

GraMem stores what a user said, where it came from, and whether it may still be used. It runs as a native `MemoryProvider` for [Hermes Agent](#use-with-hermes-agent), and also as a standalone Python library and CLI. SQLite is the single source of truth for transactions and visibility. FalkorDB is an optional, independent projection used for relationship recall. Originals (documents, chat transcripts, assistant audio) stay in a private directory on your own machine.

## Why GraMem

- **Every fact has a source.** Memories keep their evidence, version history and confidence, so you can answer "why does the agent believe this?".
- **Forgetting actually blocks use.** Disabling, forgetting, re-enabling and re-authorizing a memory propagate to originals, derived facts, profiles and the graph, so nothing leaks around a deleted item.
- **Bounded recall.** Always / Relevant / Historical tiers, Chinese-aware full-text search, optional vector search and a graph expansion, all inside a token budget (default 1024).
- **Identity and scope.** Owner / Contact / Group spaces, per-profile isolation, and verified cross-channel account linking.
- **Knowledge and chat archive.** PDF / DOCX / text / image originals with versions, OCR, chunk and page locators, search, export and ZIP; two-sided chat transcripts with hashes, summaries and topic timelines.
- **A visible memory network.** Facts, files, chats, audio, topics and events as a weighted, time-ordered graph.
- **Private by default.** No telemetry. The only outbound calls go to the OpenAI-compatible endpoint you configure (`base_url`, DashScope by default, any compatible service works). With no `model` set, nothing is sent anywhere.

## Quick start (no Docker, no API key)

Requires Python 3.12 or newer.

```sh
git clone https://github.com/Nickspace114514/GraMem.git
cd GraMem
python -m venv .venv && . .venv/bin/activate
pip install -e .

mkdir -p ~/gramem-home/gramem && chmod 700 ~/gramem-home
echo '{"owner_id": "me", "trusted_cli_owner": true}' > ~/gramem-home/gramem/config.json

gramem --home ~/gramem-home remember "I prefer concise answers" --type preference
gramem --home ~/gramem-home recall "answers"
gramem --home ~/gramem-home ingest ./some-document.pdf
gramem --home ~/gramem-home status
```

Automatic extraction from conversations, vector search and the graph need a model endpoint and (for the graph) FalkorDB. The [Deployment & usage guide](docs/quickstart.md) walks through each step.

## Use with Hermes Agent

GraMem registers itself under the `hermes_agent.memory_providers` entry point. Add it to your profile configuration, merging with what you already have:

```yaml
memory:
  provider: gramem
  memory_enabled: false
  user_profile_enabled: false
plugins:
  enabled:
    - gramem
```

The agent then gets five tools: `gramem_memory`, `gramem_recall`, `gramem_knowledge`, `gramem_chats` and `gramem_network`. An optional admin console ships in [`integrations/control-panel`](integrations/control-panel/README.md).

## Documentation

| I want to... | Read |
|---|---|
| Install, configure and run it | [Deployment & usage guide](docs/quickstart.md) ([中文](docs/quickstart.zh-CN.md)) |
| Understand the modules, database and transactions | [Architecture](ARCHITECTURE.md) |
| See every config field | [Configuration](docs/configuration.md), [defaults JSON](docs/config-defaults.json) |
| Call the tools, CLI and Python API | [Interfaces](docs/interfaces.md), [tool schemas](docs/tool-schemas.json) |
| Use the admin REST API | [Control panel API](docs/control-panel.md), [OpenAPI](docs/openapi.json) |
| Operate, back up and restore | [Maintenance](docs/maintenance.md), [Deployment reference](docs/deployment.md) |
| Browse everything else | [Documentation index](docs/README.md) |

Most reference documents are written in Chinese; the English guide above covers installation and day-to-day use.

## Development

```sh
pip install -e '.[dev]'
python -m pytest tests/v2 -q
ruff check .
```

Four graph tests are skipped unless `GRAMEM_TEST_GRAPH_URL` points at a disposable FalkorDB (for example `redis://127.0.0.1:6380/0` after `docker compose up -d --wait`). See [CONTRIBUTING.md](CONTRIBUTING.md).

## Limits worth knowing

- Forgetting does not erase host chat history, logs, exports you already made, or old backups. After a restore, re-check later exclusions.
- Automatic image description and image-based search are not implemented. Vector search is linear in the number of memories (fine at personal scale). The `NEXT` relation means order in time, not causation.
- OCR needs system Tesseract, its language packs and Poppler.

## Security

Please report vulnerabilities privately; see [SECURITY.md](SECURITY.md).

## License

[GNU Affero General Public License v3.0](LICENSE). If you run a modified version as a network service, the AGPL requires you to offer its source to the users of that service.
