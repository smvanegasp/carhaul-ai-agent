# Mia agent

The LiveKit voice-agent worker: prompt, call state, tools (geocoding, CarHauler247 API) and
evals. See the repo-root [AGENTS.md](../AGENTS.md).

```sh
uv sync
uv run pytest -q          # offline tests
uv run pytest -m live     # tests that call real APIs (needs keys in the repo-root .env)
uv run ruff check . && uv run ruff format --check .
```
