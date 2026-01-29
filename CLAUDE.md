**Project context**
- Agentic CLI that extracts fix findings from an inspiration Git repo and checks applicability to a target repo, producing structured JSON reports.
- Good output = reviewable findings/assessments; it does not auto-patch repos.

**Repo map**
- `src/different_agent/`: CLI + core logic (agents, config, git/github tools, reporting).
- `tests/`: pytest suite.
- `outputs/`: generated reports (local artifacts).
- `different.toml`: default runtime config.

**Tech stack**
- Python 3.11.
- DeepAgents + LangChain OpenAI.
- Tooling: uv, ruff, ty, pytest.

**Common commands**
```bash
uv sync --all-groups

different-agent --inspiration /path/to/inspiration --target /path/to/target
different-agent --inspiration /path/to/inspiration --extract-only
```
```bash
uv run ruff format .
uv run ruff check .
uv run ty check src/
uv run pytest
```

**Code style**
- Ruff line length: 100; target version: py311.
- `E501` is ignored in `src/different_agent/agents.py` and `src/different_agent/report.py` (long prompt/template strings).

**Workflow rules**
- Explore code before changes; keep edits minimal and focused.
- Run format + lint + typecheck + tests before finishing.

**Testing**
- Pytest with coverage and warnings-as-errors (see `pyproject.toml`).
- Single test example:
```bash
uv run pytest tests/test_config.py -k test_name
```

**Tooling notes**
- Pre-commit hooks: `prek run --all-files` (ruff, ty, shellcheck).
- Runtime config is `different.toml`; CLI uses it by default. Use `--model` to override per run.

**Gotchas**
- GitHub enrichment needs a token to avoid rate limits (see README).
- Outputs are written under `outputs/<project_name>/` with time-based suffixes.

**More docs**
- @README.md
