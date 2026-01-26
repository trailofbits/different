# Different Agent

Different Agent is a small agentic app built with Deep Agents (LangGraph). It does two things:

- First, it looks at an “inspiration” local Git repository and tries to extract recent bug fixes and security fixes. It outputs a structured JSON file with one entry per fix.
- Then, it takes that JSON and checks a “target” local Git repository to see if the same problems likely apply there. It outputs another JSON file with one entry per finding.

The logic is agentic: an LLM calls local Git tools (and optional GitHub API tools) in a loop to inspect commits, diffs, and related PR/issue context.

## Requirements

The default config uses OpenAI `gpt-5.2` with `reasoning_effort="xhigh"`, so you usually want `OPENAI_API_KEY` set. If you switch to a Claude model via `--model`, you need `ANTHROPIC_API_KEY`.

## Configuration

The app reads `different.toml`. This is where you set the “recent” window (days + max commits), how many patch lines are fetched per commit, whether GitHub enrichment is enabled, whether HTML reports are generated, and the default model settings.
You can override the model per run with `--model`.

## Usage
Run the full workflow (extract -> heck):

```bash
uv sync --all-groups
different-agent --inspiration /path/to/inspiration-repo --target /path/to/target-repo
```

## Caching

Each run uses a LangGraph in-memory cache for agent execution to reuse identical model calls within the same process. If you use an Anthropic model, Deep Agents also enables Anthropic prompt caching automatically (no extra config needed).

## GitHub (optional)

If GitHub enrichment is enabled, the extractor tries to infer `{owner, repo}` from the inspiration repo’s `origin` remote and then calls the GitHub REST API to pull recent closed issues and PRs. Set `GITHUB_TOKEN` (or `GH_TOKEN`) to avoid rate limits.
