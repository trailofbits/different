# Different

[![tests](https://github.com/trailofbits/different/actions/workflows/ci.yml/badge.svg?label=tests)](https://github.com/trailofbits/different/actions/workflows/ci.yml)

Different is a variant-analysis agentic tool built with DeepAgents. It does two things:

- First, it looks at an "inspiration" local Git repository and tries to extract recent bug fixes and security fixes, skipping docs/formatting/test/refactor-only commits unless the diff shows an actual bug fix. It outputs a structured JSON file with one entry per fix, including idea-level root causes and tags so matching can be flexible.
- Then, it takes that JSON and checks a “target” local Git repository to see if the same problems likely apply there. It outputs another JSON file with one entry per finding.

The logic is agentic: an LLM calls local Git tools (and optional GitHub API tools) in a loop to inspect commits, diffs, and related PR/issue context. The target assessment agent now follows a security-judge style and appends a clear verdict to each assessment's `why` field.

## When to use it
- You are fuzzing two parsers, `A` and `B`, that should behave almost identically. Run `different` to check that recent bug/vuln fixes from codebase `A` don't apply to codebase `B`.
- A CVE drops for library `X`. You have an internal fork or a similar implementation. Point `different` at `X` as inspiration and your codebase as target to quickly check if the same bug class affects you.
- Before doing code review for codebase `B`, run `different` against a well-maintained sibling codebase `A` to see what kinds of vulnerabilities are being fixed there and get inspiration from that.
- Give it as context to an LLM/agentinc app. Feed the output to another agent and ask follow-up questions, e.g. _"could a fuzzer have found these bugs? If yes, generate a harness."_

## Requirements

The default config uses GPT-5.2 with xhigh reasonning. If you switch to a Claude model via `--model`, you need `ANTHROPIC_API_KEY`.

## Pre-commit hooks

This repo includes a `.pre-commit-config.yaml` that runs `ruff`, `ty`, and `shellcheck`.
Use `prek` (or `pre-commit`) to run the hooks, for example:

```bash
uv sync --group lint
prek run --all-files
```

Or use the Makefile:

```bash
make lint
```

## Testing
- `pytest` runs with `pytest-cov` .
- Warnings are treated as errors.
Run:
```bash
uv run pytest
```

Or use the Makefile:

```bash
make test
```

## Configuration

The app reads `different.toml`. This is where you set the “recent” window (days + max commits), how many patch lines are fetched per commit, whether GitHub enrichment is enabled, whether HTML reports are generated, and the default model settings. You can also set `extract.since_date` (YYYY-MM-DD or ISO-8601) to scan from a fixed date; it overrides `since_days`.
You can override the model per run with `--model`.

## Usage
Run the full workflow (extract -> check):

```bash
uv sync --all-groups
different-agent --inspiration /path/to/inspiration-repo --target /path/to/target-repo
```

Run extraction only (skip target analysis):

```bash
uv sync --all-groups
different-agent --inspiration /path/to/inspiration-repo --extract-only
```

Outputs are written under `outputs/<project_name>/` and get a time-based suffix per run.
For example: `outputs/my-target/target_assessment_01-12_22-12.json`.
At the end of a run, the console also prints how many commits and PRs were analyzed.

Scan from a given date (overrides `since_days`):

```bash
different-agent --inspiration /path/to/inspiration-repo --target /path/to/target-repo --since-date 2024-01-01
```

Limit GitHub PRs to a number range (inclusive):

```bash
different-agent --inspiration /path/to/inspiration-repo --extract-only --from-pr 3300 --to-pr 3350
```

When a PR range is provided, the extractor skips commit and issue scanning and focuses on GitHub PRs only.
