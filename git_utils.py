"""
git_utils.py
------------
Utilities for extracting git diff, author, date, and commit message.
Works with local repos or public GitHub URLs (cloned to a temp dir).
"""

import os
import re
import subprocess
import tempfile
import shutil
from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass
class CommitInfo:
    sha: str
    author: str
    email: str
    date: str        # ISO-8601
    message: str
    short_sha: str = ""

    def __post_init__(self):
        self.short_sha = self.sha[:7]


@dataclass
class DiffResult:
    diff_text: str
    changed_files: list
    commits: list
    repo_path: str
    commit_range: str
    stats: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_diff(repo_path_or_url: str, commit_range: str) -> DiffResult:
    """
    Accepts a local path or public GitHub HTTPS URL.
    commit_range: "HEAD~1..HEAD", "abc..def", or single ref like "HEAD".
    """
    local_path, cloned = _resolve_repo(repo_path_or_url)
    try:
        return _extract_diff(local_path, commit_range)
    finally:
        if cloned:
            shutil.rmtree(local_path, ignore_errors=True)


def list_recent_commits(repo_path_or_url: str, n: int = 20) -> list:
    """Return the N most recent commits for the UI commit picker."""
    local_path, cloned = _resolve_repo(repo_path_or_url)
    try:
        try:
            return _get_commits(local_path, f"HEAD~{n}..HEAD", limit=n)
        except Exception:
            return _get_commits(local_path, "HEAD", limit=n)
    finally:
        if cloned:
            shutil.rmtree(local_path, ignore_errors=True)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _resolve_repo(s):
    s = s.strip()
    p = urlparse(s)
    if p.scheme in ("http", "https") and "github.com" in (p.netloc or ""):
        tmp = tempfile.mkdtemp(prefix="changelens_")
        _run(["git", "clone", "--depth", "50", s, tmp])
        return tmp, True
    local = os.path.expanduser(s)
    if not os.path.isdir(local):
        raise FileNotFoundError(f"Repository path not found: {local}")
    return local, False


def _run(cmd, cwd=None, check=True):
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git error: {result.stderr.strip()}")
    return result.stdout


def _normalise_range(commit_range, cwd):
    r = commit_range.strip()
    if ".." in r:
        return r
    sha = _run(["git", "rev-parse", r], cwd=cwd).strip()
    return f"{sha}~1..{sha}"


def _extract_diff(local_path, commit_range):
    norm = _normalise_range(commit_range, local_path)
    diff_text = _run(["git", "diff", "--unified=5", norm], cwd=local_path)
    raw_files = _run(["git", "diff", "--name-only", norm], cwd=local_path)
    changed_files = [f for f in raw_files.splitlines() if f.strip()]
    stat_raw = _run(["git", "diff", "--shortstat", norm], cwd=local_path)
    stats = _parse_shortstat(stat_raw.strip())
    commits = _get_commits(local_path, norm)
    return DiffResult(
        diff_text=diff_text,
        changed_files=changed_files,
        commits=commits,
        repo_path=local_path,
        commit_range=commit_range,
        stats=stats,
    )


def _get_commits(local_path, commit_range, limit=100):
    SEP = ""   # ASCII unit separator – safe in git log
    fmt = f"%H{SEP}%an{SEP}%ae{SEP}%aI{SEP}%s"
    try:
        raw = _run(
            ["git", "log", f"--format={fmt}", f"-{limit}", commit_range],
            cwd=local_path,
        )
    except RuntimeError:
        try:
            raw = _run(["git", "log", f"--format={fmt}", "-1"], cwd=local_path)
        except RuntimeError:
            return []
    commits = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(SEP, 4)
        if len(parts) < 5:
            continue
        sha, author, email, date, message = parts
        commits.append(CommitInfo(sha=sha, author=author, email=email, date=date, message=message))
    return commits


def _parse_shortstat(stat):
    out = {"files": 0, "insertions": 0, "deletions": 0}
    m = re.search(r"(\d+) files? changed", stat)
    if m:
        out["files"] = int(m.group(1))
    m = re.search(r"(\d+) insertions?", stat)
    if m:
        out["insertions"] = int(m.group(1))
    m = re.search(r"(\d+) deletions?", stat)
    if m:
        out["deletions"] = int(m.group(1))
    return out
