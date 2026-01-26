# Different Agent

Different Agent is a small agentic app built with Deep Agents (LangGraph). It does two things:

First, it looks at an “inspiration” local Git repository and tries to extract recent bug fixes and security fixes. It outputs a structured JSON file with one entry per fix.

Second, it takes that JSON and checks a “target” local Git repository to see if the same problems likely apply there. It outputs another JSON file with one entry per finding.

The logic is agentic: an LLM calls local Git tools (and optional GitHub API tools) in a loop to inspect commits, diffs, and related PR/issue context.
If you change core behavior, keep `README.md` and `AGENTS.md` updated.

## Requirements

You need Python 3.11+ and at least one model API key.

The default config uses OpenAI `gpt-5.2` with `reasoning_effort="xhigh"`, so you usually want `OPENAI_API_KEY` set. If you switch to a Claude model via `--model`, you need `ANTHROPIC_API_KEY`.

## Configuration

The app reads `different.toml`. This is where you set the “recent” window (days + max commits), how many patch lines are fetched per commit, whether GitHub enrichment is enabled, whether HTML reports are generated, and the default model settings.

You can override the model per run with `--model`.

## Usage

Install (pick one):

```bash
uv sync
```

or:

```bash
python3 -m venv .venv
./.venv/bin/pip install -e .
```

Extract findings from an inspiration repo:

```bash
different-agent extract --inspiration /path/to/inspiration-repo --out outputs/findings.json
```

Check a target repo against those findings:

```bash
different-agent check --target /path/to/target-repo --findings outputs/findings.json --out outputs/target_assessment.json
```

If `reports.html=true` in `different.toml`, the CLI also writes `outputs/findings.html` and `outputs/target_assessment.html`.

## GitHub (optional)

If GitHub enrichment is enabled, the extractor tries to infer `{owner, repo}` from the inspiration repo’s `origin` remote and then calls the GitHub REST API to pull recent closed issues and PRs. Set `GITHUB_TOKEN` (or `GH_TOKEN`) to avoid rate limits.

## Notes

Both inputs must be local Git repos and must contain a `.git/` directory. Output quality depends on the model, prompts, and available context, so treat results as a starting point for review, not a final security verdict.
