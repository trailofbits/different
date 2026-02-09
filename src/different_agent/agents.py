from __future__ import annotations

from typing import Any, Literal

from deepagents import create_deep_agent
from langchain.agents.structured_output import AutoStrategy
from langchain_core.language_models import BaseChatModel
from langgraph.cache.base import BaseCache
from pydantic import BaseModel, Field

from different_agent.git_tools import (
    ast_grep,
    git_diff,
    git_grep,
    git_recent_commits,
    git_show_commit,
    git_show_file,
)
from different_agent.github_tools import (
    git_github_repo,
    github_fetch_issue,
    github_fetch_pr,
    github_fetch_pr_files,
    github_recent_issues,
    github_recent_prs,
)

FINDING_SCHEMA_VERSION = "v1"


class EvidenceCommit(BaseModel):
    sha: str
    subject: str
    date: str


class FindingEvidence(BaseModel):
    commits: list[EvidenceCommit] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    diff_snippets: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    id: str
    kind: Literal["bug", "vulnerability", "hardening"]
    title: str
    severity: Literal["low", "medium", "high", "critical", "unknown"]
    root_cause: str
    fix_summary: str
    evidence: FindingEvidence
    tags: list[str] = Field(default_factory=list)


class FindingsResponse(BaseModel):
    findings: list[Finding]


class TargetAssessment(BaseModel):
    finding_id: str
    applies: bool | Literal["unknown"]
    confidence: float
    why: str
    evidence: dict[str, Any]
    suggested_next_steps: list[str] = Field(default_factory=list)


class TargetAssessmentsResponse(BaseModel):
    assessments: list[TargetAssessment]


INSPIRATION_AGENT_PROMPT = f"""You analyze a codebase and extract structured “fix findings.” or "vulnerability fix findings"
You do this because you will then feed all of your findings to an agent that checks whether the bugs you found also apply to other codebases.
For example, if a bug that introduces a security issue is discovered in a WASM virtual machine and is fixed via a commit,
you want to extract that bug so another agent can check whether it can be reproduced in another repository that also implements a WASM virtual machine.

The goal is to extract all bug fixes that may have addressed previously introduced security issues, ranging from low- to high-severity.

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
- from_pr: <int or null>
- to_pr: <int or null>

Goal:
- Identify recent bug fixes or vulnerability fixes from commit history.
- If GitHub data is available, also use recent Issues/PRs and (when useful) fetch Issue/PR content for context.
- Produce a JSON array of findings (schema: {FINDING_SCHEMA_VERSION}) with solid evidence.
- Capture enough idea-level detail so a separate agent can check for similar concepts in a target repo (not 1:1
  signature matches).

Hard rules:
- Only use the provided git tools to inspect commits.
- Prefer evidence from diffs over speculation.
- Skip docs-only, formatting-only, test-only, or pure refactor changes unless the diff shows an actual bug fix.
- Commit message alone is never sufficient evidence of a fix. Investigate the difference of lines.
- Do NOT paste entire diffs into the JSON. Keep diff_snippets short.
- If you include GitHub issues/PRs, include their links in evidence.links.
- Be conservative: if you can't justify severity, set severity="unknown".
- root_cause must describe the generalized mechanism (unsafe pattern + conditions), not just the local symbol name.
- fix_summary must describe the conceptual mitigation, not only the exact code change.
- tags should include short idea-level keywords to help variant matching (e.g. "ambiguous-encoding",
  "length-prefix", "hash-collision", "variable-length-bytes").

Output:
- Write the JSON to /outputs/findings.json
- The file must be valid JSON (no trailing commas, no comments).
- Also return a structured response with top-level key "findings" that matches the schema.

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
3) If git_recent_commits is available, call git_recent_commits(repo_path, since_days, max_count). Use the subjects to pick
   a smaller set of likely fixes (ex: subjects containing "fix", "security", "vuln", "cve", "sanitize", "overflow", "race", "dos", "leak").
4) If git_show_commit is available, call git_show_commit(repo_path, sha, max_patch_lines) for likely fixes and extract evidence.
5) Try to resolve GitHub owner/repo using git_github_repo(repo_path). If that succeeds, also call
   github_recent_prs(owner, repo, since_days, max_prs, from_pr, to_pr) / github_recent_issues(owner, repo, since_days, max_issues)
   for the same window (unless from_pr/to_pr is provided), then fetch details (github_fetch_pr / github_fetch_pr_files / github_fetch_issue)
   only for the items that look like fixes.
   If include_github is false, skip all GitHub tools.
6) Write /outputs/findings.json.
"""


TARGET_AGENT_PROMPT = f"""You analyze a target codebase for applicability of known findings.

Role and objective:
- You are a senior security judge focused on analyzing security fixes.
- Your main goal is to decide whether each reported finding is a genuine security concern in the target repo
  or a false positive. Be pragmatic and honest.

Inputs:
- A local git repository path (it will have a .git directory).
- A findings JSON file at /inputs/findings.json (schema: {FINDING_SCHEMA_VERSION}).

The user message will include:
- target_repo_path: <path>

Core instructions:
- Use critical thinking for every finding. Assess factual accuracy AND whether any actual security risk exists.
- Collect concrete evidence; consider edge and corner cases.
- Use all available documentation, code, and descriptions to inform your judgment.
- Read available documentation and code context (use git_show_file as needed).
- If you create scratch files, use /tmp. Final output must still be written to /outputs/target_assessment.json.

Goal:
- For each finding, decide if it likely applies to the target codebase.
- Produce a JSON array of assessments.

Output:
- Write the JSON to /outputs/target_assessment.json
- Also return a structured response with top-level key "assessments" that matches the schema.

Assessment fields:
- finding_id
- applies (true | false | "unknown")
- confidence (0..1)
- why (string)
- evidence (object)
- suggested_next_steps ([string])

Verdict mapping:
- applies=true => valid issue
- applies=false => false positive
- applies="unknown" => unknown
- End each "why" with the exact words "valid issue", "false positive", or "unknown".

Workflow (recommended):
1) Read /inputs/findings.json.
2) Treat target_repo_path as repo_path for all git tools.
3) For each finding:
   - Use git_grep(repo_path, ...) to search for the vulnerable pattern or key identifiers (prefer fixed-string searches
     based on diff_snippets, file paths, function names, and error strings).
   - If needed, use git_show_file(repo_path, file_path, ref="HEAD") to inspect context.
   - Use git_diff(repo_path, ref_a, ref_b) to compare two refs when you need to see what changed between versions.
   - Use ast_grep(repo_path, pattern, language) for structural code matching (e.g. find all calls to a function
     with specific argument shapes, or match code patterns regardless of variable naming). This is more precise than
     text grep for code patterns. ast_grep may not be installed; if it returns an error, fall back to git_grep.
   - Decide applies=true/false/unknown with a confidence score.
4) Write /outputs/target_assessment.json.
"""


def create_inspiration_agent(
    model: BaseChatModel,
    cache: BaseCache | None = None,
    *,
    include_commits: bool = True,
    include_issues: bool = True,
) -> Any:
    tools = [
        git_github_repo,
        github_recent_prs,
        github_fetch_pr,
        github_fetch_pr_files,
    ]
    if include_commits:
        tools = [
            git_recent_commits,
            git_show_commit,
            *tools,
        ]
    if include_issues:
        tools.extend([github_recent_issues, github_fetch_issue])
    return create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=INSPIRATION_AGENT_PROMPT,
        response_format=AutoStrategy(FindingsResponse),
        cache=cache,
    )


def create_target_agent(model: BaseChatModel, cache: BaseCache | None = None) -> Any:
    return create_deep_agent(
        model=model,
        tools=[git_grep, git_show_file, git_diff, ast_grep],
        system_prompt=TARGET_AGENT_PROMPT,
        response_format=AutoStrategy(TargetAssessmentsResponse),
        cache=cache,
    )
