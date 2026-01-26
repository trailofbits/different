# Different

Different is a small agentic app built with Deep Agents (LangGraph). It does two things:

- First, it looks at an "inspiration" local Git repository and tries to extract recent bug fixes and security fixes, skipping docs/formatting/test/refactor-only commits unless the diff shows an actual bug fix. It outputs a structured JSON file with one entry per fix, including idea-level root causes and tags so matching can be flexible.
- Then, it takes that JSON and checks a “target” local Git repository to see if the same problems likely apply there. It outputs another JSON file with one entry per finding.

The logic is agentic: an LLM calls local Git tools (and optional GitHub API tools) in a loop to inspect commits, diffs, and related PR/issue context. The target assessment agent now follows a security-judge style and appends a clear verdict to each assessment's `why` field.

## Requirements

The default config uses OpenAI `gpt-5.2` with `reasoning_effort="xhigh"`, so you usually want `OPENAI_API_KEY` set. If you switch to a Claude model via `--model`, you need `ANTHROPIC_API_KEY`.

## Configuration

The app reads `different.toml`. This is where you set the “recent” window (days + max commits), how many patch lines are fetched per commit, whether GitHub enrichment is enabled, whether HTML reports are generated, and the default model settings.
You can override the model per run with `--model`.

## Usage
Run the full workflow (extract -> check):

```bash
uv sync --all-groups
different-agent --inspiration /path/to/inspiration-repo --target /path/to/target-repo
```

## Logging
Logs are sentence-style and omit module name prefixes (example: `2026-01-26 10:15:42 INFO Starting different-agent.`).
