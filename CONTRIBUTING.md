# Contributing to GraMem

Thanks for helping. A short guide.

## Set up

```sh
git clone https://github.com/Nickspace114514/GraMem.git
cd GraMem
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
```

Python 3.12 or newer is required.

## Check your change

```sh
ruff check .
python -m pytest tests/v2 -q
```

Four graph tests are skipped unless `GRAMEM_TEST_GRAPH_URL` points at a disposable FalkorDB. To run them:

```sh
docker compose up -d --wait
GRAMEM_TEST_GRAPH_URL=redis://127.0.0.1:6380/0 python -m pytest tests/v2 -q
```

Tests use temporary homes and never touch real profile data. Never point a test at a database you care about.

## Rules that matter

- **Forgetting and visibility are the core promise.** Any change near recall, export, listing or the graph must keep disabled, forgotten and out-of-scope data unreachable, and needs a test that proves it.
- **Keep SQLite authoritative.** The graph is a projection that may lag; it must never decide what is visible.
- **Schema changes** are additive and migrated inside the existing transaction. Bump the schema version, add a migration test, and say so in the PR.
- **No secrets or personal data** in code, tests, fixtures or docs. Use obvious fakes such as `sk-example-...`, `user@example.com`, `<host>`.
- Keep the diff focused. Update the English and Chinese docs together when a command or config key changes.

## Pull requests

Describe what changed and why, tick the checklist in the template, and keep commits understandable. For anything large, open an issue first so we can agree on the direction.

By contributing you agree that your work is licensed under the project's [AGPL-3.0](LICENSE) license.
