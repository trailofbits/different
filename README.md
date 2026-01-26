# Different Agent

Different Agent is a small agentic app built with Deep Agents (LangGraph). It does two things:

First, it looks at an “inspiration” local Git repository and tries to extract recent bug fixes and security fixes. It outputs a structured JSON file with one entry per fix.

Second, it takes that JSON and checks a “target” local Git repository to see if the same problems likely apply there. It outputs another JSON file with one entry per finding.

The logic is agentic: an LLM calls local Git tools (and optional GitHub API tools) in a loop to inspect commits, diffs, and related PR/issue context.

## Requirements

You need Python 3.11+ and at least one model API key.

The default config uses OpenAI `gpt-5.2` with `reasoning_effort="xhigh"`, so you usually want `OPENAI_API_KEY` set. If you switch to a Claude model via `--model`, you need `ANTHROPIC_API_KEY`.

## Configuration

The app reads `different.toml`. This is where you set the “recent” window (days + max commits), how many patch lines are fetched per commit, whether GitHub enrichment is enabled, whether HTML reports are generated, and the default model settings.

You can override the model per run with `--model`.

## Usage

Install (recommended):

```bash
uv sync --all-groups
```

Run the full workflow (extract → check):

```bash
different-agent --inspiration /path/to/inspiration-repo --target /path/to/target-repo
```

Override output paths:

```bash
different-agent \
  --inspiration /path/to/inspiration-repo \
  --target /path/to/target-repo \
  --findings-out outputs/findings.json \
  --assessment-out outputs/target_assessment.json
```

If `reports.html=true` in `different.toml`, the CLI also writes `outputs/findings.html` and `outputs/target_assessment.html`.

## Logging

The CLI writes INFO-level progress logs to stderr so you can follow startup, config, agent runs, tool calls, and output writes. Log levels are ANSI color-coded.

## GitHub (optional)

If GitHub enrichment is enabled, the extractor tries to infer `{owner, repo}` from the inspiration repo’s `origin` remote and then calls the GitHub REST API to pull recent closed issues and PRs. Set `GITHUB_TOKEN` (or `GH_TOKEN`) to avoid rate limits.

## Notes

Both inputs must be local Git repos and must contain a `.git/` directory. Output quality depends on the model, prompts, and available context, so treat results as a starting point for review, not a final security verdict.

## Development

Run tooling with `uv run`:

```bash
uv run ruff format .
uv run ruff check .
uv run ty check src/
uv run pytest
```
