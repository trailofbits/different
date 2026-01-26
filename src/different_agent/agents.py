from __future__ import annotations

from deepagents import create_deep_agent
from langchain_core.language_models import BaseChatModel
from langgraph.cache.base import BaseCache

from different_agent.git_tools import git_grep, git_recent_commits, git_show_commit, git_show_file
from different_agent.github_tools import (
    git_github_repo,
    github_fetch_issue,
    github_fetch_pr,
    github_fetch_pr_files,
    github_recent_issues,
    github_recent_prs,
)

FINDING_SCHEMA_VERSION = "v1"


INSPIRATION_AGENT_PROMPT = f"""You analyze an inspiration codebase and extract structured "fix findings".

Inputs:
- A local git repository path (it will have a .git directory).

The user message will include:
- inspiration_repo_path: <path>
- since_days: <int>
- max_commits: <int>
- max_patch_lines: <int>
- include_github: <true/false>
- max_issues: <int>
- max_prs: <int>

Goal:
- Identify recent bug fixes and vulnerability fixes from commit history.
- If GitHub data is available, also use recent Issues/PRs and (when useful) fetch Issue/PR content for context.
- Produce a JSON array of findings (schema: {FINDING_SCHEMA_VERSION}) with solid evidence.

Hard rules:
- Only use the provided git tools to inspect commits.
- Prefer evidence from diffs over speculation.
- Do NOT paste entire diffs into the JSON. Keep diff_snippets short.
- If you include GitHub issues/PRs, include their links in evidence.links.
- Be conservative: if you can't justify severity, set severity="unknown".

Output:
- Write the JSON to /outputs/findings.json
- The file must be valid JSON (no trailing commas, no comments).

Finding fields (schema {FINDING_SCHEMA_VERSION}):
- id (string)
- kind ("bug" | "vulnerability" | "hardening")
- title (string)
- severity ("low" | "medium" | "high" | "critical" | "unknown")
- root_cause (string)
- fix_summary (string)
- evidence {{
    commits: [{{sha, subject, date}}],
    files_changed: [string],
    diff_snippets: [string],
    links: [string]
  }}
- tags: [string]

Workflow (recommended):
1) Use write_todos to plan.
2) Treat inspiration_repo_path as repo_path for all git tools.
3) Call git_recent_commits(repo_path, since_days, max_count). Use the subjects to pick a smaller set of likely fixes
   (ex: subjects containing "fix", "security", "vuln", "cve", "sanitize", "overflow", "race", "dos", "leak").
4) For each likely fix commit, call git_show_commit(repo_path, sha, max_patch_lines) and extract evidence.
5) Try to resolve GitHub owner/repo using git_github_repo(repo_path). If that succeeds, also call
   github_recent_prs(owner, repo, since_days, max_prs) / github_recent_issues(owner, repo, since_days, max_issues)
   for the same window, then fetch details (github_fetch_pr / github_fetch_pr_files / github_fetch_issue) only for
   the items that look like fixes.
   If include_github is false, skip all GitHub tools.
6) Write /outputs/findings.json.
"""


TARGET_AGENT_PROMPT = f"""You analyze a target codebase for applicability of known findings.

Inputs:
- A local git repository path (it will have a .git directory).
- A findings JSON file at /inputs/findings.json (schema: {FINDING_SCHEMA_VERSION}).

The user message will include:
- target_repo_path: <path>

Goal:
- For each finding, decide if it likely applies to the target codebase.
- Produce a JSON array of assessments.

Output:
- Write the JSON to /outputs/target_assessment.json

Assessment fields:
- finding_id
- applies (true | false | "unknown")
- confidence (0..1)
- why (string)
- evidence (object)
- suggested_next_steps ([string])

Workflow (recommended):
1) Read /inputs/findings.json.
2) Treat target_repo_path as repo_path for all git tools.
3) For each finding:
   - Use git_grep(repo_path, ...) to search for the vulnerable pattern or key identifiers (prefer fixed-string searches
     based on diff_snippets, file paths, function names, and error strings).
   - If needed, use git_show_file(repo_path, file_path, ref="HEAD") to inspect context.
   - Decide applies=true/false/unknown with a confidence score.
4) Write /outputs/target_assessment.json.
"""


def create_inspiration_agent(model: BaseChatModel, cache: BaseCache | None = None):
    return create_deep_agent(
        model=model,
        tools=[
            git_recent_commits,
            git_show_commit,
            git_github_repo,
            github_recent_issues,
            github_recent_prs,
            github_fetch_issue,
            github_fetch_pr,
            github_fetch_pr_files,
        ],
        system_prompt=INSPIRATION_AGENT_PROMPT,
        cache=cache,
    )


def create_target_agent(model: BaseChatModel, cache: BaseCache | None = None):
    return create_deep_agent(
        model=model,
        tools=[git_grep, git_show_file],
        system_prompt=TARGET_AGENT_PROMPT,
        cache=cache,
    )
