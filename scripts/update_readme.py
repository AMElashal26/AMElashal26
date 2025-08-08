#!/usr/bin/env python3
import os
import re
import sys
import json
import time
import math
import pathlib
import datetime as dt
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

README_PATH = pathlib.Path(__file__).resolve().parents[1] / "README.md"
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "AMElashal26")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")  # optional
API_BASE = "https://api.github.com"

REQUEST_TIMEOUT = 15
MAX_REPOS = 6
MAX_EVENTS = 5


def github_get(url: str):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-updater"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        print(f"HTTPError {e.code} for {url}: {e.read().decode('utf-8', errors='ignore')}", file=sys.stderr)
    except URLError as e:
        print(f"URLError for {url}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
    return None


def format_projects():
    # Fetch user repos sorted by updated
    repos = github_get(f"{API_BASE}/users/{GITHUB_USERNAME}/repos?per_page=100&sort=updated") or []
    public_repos = [r for r in repos if not r.get("fork")]
    lines = []
    for repo in public_repos[:MAX_REPOS]:
        name = repo.get("name", "")
        desc = (repo.get("description") or "").strip()
        stars = repo.get("stargazers_count", 0)
        lang = repo.get("language") or ""
        html_url = repo.get("html_url")
        parts = [f"[{name}]({html_url})"]
        info = []
        if desc:
            info.append(desc)
        if lang:
            info.append(lang)
        if stars:
            info.append(f"⭐ {stars}")
        if info:
            parts.append(": " + " · ".join(info))
        lines.append("- " + "".join(parts))
    if not lines:
        lines.append("- (No public repositories found)")
    return "\n".join(lines)


def format_activity():
    events = github_get(f"{API_BASE}/users/{GITHUB_USERNAME}/events/public?per_page=30") or []
    lines = []
    for e in events:
        et = e.get("type")
        repo = (e.get("repo") or {}).get("name", "")
        created = e.get("created_at", "")
        try:
            when = dt.datetime.fromisoformat(created.replace("Z", "+00:00")).date().isoformat()
        except Exception:
            when = created
        summary = None
        if et == "PushEvent":
            count = len((e.get("payload") or {}).get("commits", []) or [])
            summary = f"pushed {count} commit(s) to {repo}"
        elif et == "PullRequestEvent":
            action = (e.get("payload") or {}).get("action", "")
            pr = (e.get("payload") or {}).get("pull_request") or {}
            num = pr.get("number")
            summary = f"{action} PR #{num} in {repo}"
        elif et == "IssuesEvent":
            action = (e.get("payload") or {}).get("action", "")
            issue = (e.get("payload") or {}).get("issue") or {}
            num = issue.get("number")
            summary = f"{action} issue #{num} in {repo}"
        elif et == "CreateEvent":
            ref_type = (e.get("payload") or {}).get("ref_type", "")
            ref = (e.get("payload") or {}).get("ref", "")
            summary = f"created {ref_type} {ref} in {repo}"
        elif et == "ForkEvent":
            summary = f"forked {repo}"
        else:
            summary = f"{et} in {repo}"
        lines.append(f"- {when}: {summary}")
        if len(lines) >= MAX_EVENTS:
            break
    if not lines:
        lines.append("- (No recent public activity)")
    return "\n".join(lines)


def format_languages():
    # Aggregate languages across top updated repos
    repos = github_get(f"{API_BASE}/users/{GITHUB_USERNAME}/repos?per_page=100&sort=updated") or []
    public_repos = [r for r in repos if not r.get("fork")]
    totals = {}
    for repo in public_repos[:20]:
        langs_url = repo.get("languages_url")
        if not langs_url:
            continue
        lang_map = github_get(langs_url) or {}
        for lang, bytes_count in lang_map.items():
            totals[lang] = totals.get(lang, 0) + int(bytes_count)
    if not totals:
        return "- (No language data)"
    total_bytes = sum(totals.values()) or 1
    # Sort by bytes desc and show top 6
    ordered = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:6]
    lines = []
    for lang, bytes_count in ordered:
        pct = 100.0 * bytes_count / total_bytes
        lines.append(f"- {lang}: {pct:.1f}%")
    return "\n".join(lines)


def replace_block(text: str, marker: str, new_content: str) -> str:
    pattern = rf"(<!-- {re.escape(marker)}:START -->)(.*?)(<!-- {re.escape(marker)}:END -->)"
    return re.sub(pattern, rf"\1\n{new_content}\n\3", text, flags=re.S)


def main() -> int:
    readme = README_PATH.read_text(encoding="utf-8")

    projects = format_projects()
    activity = format_activity()
    languages = format_languages()
    updated = dt.date.today().isoformat()

    readme = replace_block(readme, "PROJECTS", projects)
    readme = replace_block(readme, "ACTIVITY", activity)
    readme = replace_block(readme, "LANGUAGES", languages)
    readme = replace_block(readme, "UPDATED", updated)

    README_PATH.write_text(readme, encoding="utf-8")
    print("README updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())