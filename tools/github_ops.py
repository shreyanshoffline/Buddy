"""
tools/github_ops.py

Real git/GitHub actions for Buddy: clone a repo, commit, push, open a
PR, leave review comments, and drop inline comments into a file for a
code review pass. Uses the GitHub token already stored via Plugins >
GitHub (the device-flow connection in tools/integrations.py) — no
separate token needed.

Git operations shell out to the real `git` binary (matches the rest of
this codebase's pattern of using real OS tools via subprocess rather
than reimplementing them). GitHub API calls (PRs, review comments) use
the REST API directly with the stored token.
"""

import os
import subprocess
import requests

GITHUB_API = "https://api.github.com"


def _github_token() -> str:
    import core
    conn = core.get_plugin_connection("github")
    token = conn.get("access_token") if conn else None
    if not token:
        raise RuntimeError("GitHub isn't connected. Plugins > GitHub > Connect first.")
    return token


def _run_git(args, cwd=None, timeout=60) -> str:
    result = subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        return f"ERROR: {result.stderr.strip() or result.stdout.strip()}"
    return result.stdout.strip() or "OK"


# ---------------------------------------------------------------------------
# Clone / status / commit / push — plain git, no GitHub API needed
# ---------------------------------------------------------------------------

def github_clone_repo(repo_url: str, local_path: str) -> str:
    local_path = os.path.expanduser(local_path)
    if os.path.exists(local_path) and os.listdir(local_path):
        return f"ERROR: {local_path} already exists and isn't empty."
    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    # Embed the token so private repos work without a credential prompt.
    if repo_url.startswith("https://github.com/"):
        token = _github_token()
        repo_url = repo_url.replace("https://github.com/", f"https://{token}@github.com/")
    out = _run_git(["clone", repo_url, local_path])
    return f"Cloned into {local_path}." if not out.startswith("ERROR") else out


def github_status(repo_path: str) -> str:
    return _run_git(["status", "--short"], cwd=os.path.expanduser(repo_path)) or "Clean — nothing to commit."


def github_create_branch(repo_path: str, branch_name: str) -> str:
    out = _run_git(["checkout", "-b", branch_name], cwd=os.path.expanduser(repo_path))
    return f"Created and switched to branch {branch_name}." if not out.startswith("ERROR") else out


def github_commit_all(repo_path: str, message: str) -> str:
    repo_path = os.path.expanduser(repo_path)
    _run_git(["add", "-A"], cwd=repo_path)
    out = _run_git(["commit", "-m", message], cwd=repo_path)
    if "nothing to commit" in out.lower():
        return "Nothing to commit — working tree is clean."
    return f'Committed: "{message}"' if not out.startswith("ERROR") else out


def github_push(repo_path: str, branch: str = None, set_upstream: bool = True) -> str:
    repo_path = os.path.expanduser(repo_path)
    if not branch:
        branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
    args = ["push"]
    if set_upstream:
        args += ["-u", "origin", branch]
    else:
        args += ["origin", branch]
    out = _run_git(args, cwd=repo_path)
    return f"Pushed {branch} to origin." if not out.startswith("ERROR") else out


def github_pull(repo_path: str) -> str:
    return _run_git(["pull"], cwd=os.path.expanduser(repo_path))


# ---------------------------------------------------------------------------
# GitHub API — pull requests and review comments
# ---------------------------------------------------------------------------

def _api_headers():
    return {"Authorization": f"Bearer {_github_token()}", "Accept": "application/vnd.github+json"}


def github_create_pull_request(owner: str, repo: str, title: str, head: str, base: str, body: str = "") -> str:
    r = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
        headers=_api_headers(),
        json={"title": title, "head": head, "base": base, "body": body},
        timeout=15,
    )
    if r.status_code >= 300:
        return f"ERROR: {r.status_code} {r.text[:300]}"
    pr = r.json()
    return f'Opened PR #{pr["number"]} — {pr["html_url"]}'


def github_list_open_prs(owner: str, repo: str, limit: int = 10) -> str:
    r = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
        headers=_api_headers(), params={"state": "open", "per_page": limit}, timeout=15,
    )
    r.raise_for_status()
    prs = r.json()
    if not prs:
        return "No open pull requests."
    return "\n".join(f'#{p["number"]} {p["title"]} — {p["html_url"]}' for p in prs)


def github_add_pr_comment(owner: str, repo: str, pr_number: int, body: str) -> str:
    """A general PR comment (the conversation tab), not tied to a specific line."""
    r = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/{pr_number}/comments",
        headers=_api_headers(), json={"body": body}, timeout=15,
    )
    if r.status_code >= 300:
        return f"ERROR: {r.status_code} {r.text[:300]}"
    return f"Commented on PR #{pr_number}."


def github_add_review_comment(owner: str, repo: str, pr_number: int, commit_id: str,
                               path: str, line: int, body: str) -> str:
    """A comment anchored to a specific file+line — a real code review comment,
    not just a general PR remark. commit_id is the head commit SHA of the PR
    (get it from github_list_open_prs's underlying PR object, field 'head.sha',
    or `git rev-parse HEAD` on the branch)."""
    r = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/comments",
        headers=_api_headers(),
        json={"body": body, "commit_id": commit_id, "path": path, "line": line, "side": "RIGHT"},
        timeout=15,
    )
    if r.status_code >= 300:
        return f"ERROR: {r.status_code} {r.text[:300]}"
    return f"Left a review comment on {path}:{line}."


# ---------------------------------------------------------------------------
# Local code review — annotate a file directly, for when there's no PR yet
# (e.g. "review this file and add comments")
# ---------------------------------------------------------------------------

COMMENT_PREFIX_BY_EXT = {
    ".py": "#", ".sh": "#", ".rb": "#",
    ".js": "//", ".ts": "//", ".jsx": "//", ".tsx": "//", ".java": "//", ".c": "//", ".cpp": "//", ".swift": "//",
    ".html": "<!--", ".xml": "<!--",
}


def add_code_comment(file_path: str, line_number: int, comment_text: str) -> str:
    """Inserts a comment line directly above line_number, using the right
    comment syntax for the file's extension. 1-indexed line_number, matching
    what an editor shows."""
    file_path = os.path.expanduser(file_path)
    if not os.path.exists(file_path):
        return f"ERROR: {file_path} does not exist."
    ext = os.path.splitext(file_path)[1]
    prefix = COMMENT_PREFIX_BY_EXT.get(ext, "#")
    suffix = " -->" if prefix == "<!--" else ""

    with open(file_path, "r") as f:
        lines = f.readlines()
    if not (1 <= line_number <= len(lines) + 1):
        return f"ERROR: line {line_number} is out of range (file has {len(lines)} lines)."

    indent = ""
    if line_number <= len(lines):
        stripped = lines[line_number - 1]
        indent = stripped[: len(stripped) - len(stripped.lstrip())]
    comment_line = f"{indent}{prefix} {comment_text}{suffix}\n"
    lines.insert(line_number - 1, comment_line)

    with open(file_path, "w") as f:
        f.writelines(lines)
    return f"Added comment above line {line_number} in {file_path}."
