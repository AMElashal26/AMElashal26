#!/usr/bin/env python3
import os
import re
import sys
import json
import pathlib
import datetime as dt
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

README_PATH = pathlib.Path(__file__).resolve().parents[1] / "README.md"
FEATURED_REPOS_PATH = pathlib.Path(__file__).resolve().parent / "featured_repos.json"
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "AMElashal26")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")  # optional
API_BASE = "https://api.github.com"

REQUEST_TIMEOUT = 15
MAX_REPOS = 6
MAX_RECENT_REPOS = 5
MAX_EVENTS = 5


def github_get(url: str):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-updater"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
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


def fetch_public_repos():
    repos = github_get(f"{API_BASE}/users/{GITHUB_USERNAME}/repos?per_page=100&sort=updated") or []
    public_repos = [r for r in repos if not r.get("fork")]
    return sorted(public_repos, key=lambda r: r.get("pushed_at") or "", reverse=True)


def load_featured_config():
    if not FEATURED_REPOS_PATH.exists():
        return []
    try:
        data = json.loads(FEATURED_REPOS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict) and item.get("repo")]
    except Exception as e:
        print(f"Failed to parse {FEATURED_REPOS_PATH}: {e}", file=sys.stderr)
    return []


def format_projects(public_repos):
    repo_by_name = {r.get("name", "").lower(): r for r in public_repos if r.get("name")}
    featured = load_featured_config()
    lines = []
    seen = set()

    for item in featured:
        repo_name = item["repo"]
        repo = repo_by_name.get(repo_name.lower())

        desc = item.get("highlight") or ((repo or {}).get("description") or "").strip() or "Project overview"
        stars = (repo or {}).get("stargazers_count", 0)
        domain = item.get("domain", "general")
        maturity = item.get("maturity", "active")
        impact = item.get("impact", "medium")
        display_name = (repo or {}).get("name") or repo_name
        html_url = (repo or {}).get("html_url") or f"https://github.com/{GITHUB_USERNAME}/{repo_name}"

        line = (
            f"- [{display_name}]({html_url}): {desc} "
            f"· domain: {domain} · maturity: {maturity} · impact: {impact}"
        )
        if stars:
            line += f" · ⭐ {stars}"
        lines.append(line)
        seen.add(repo_name.lower())
        if len(lines) >= MAX_REPOS:
            break

    for repo in public_repos:
        name = repo.get("name", "")
        if not name or name.lower() in seen:
            continue
        desc = (repo.get("description") or "").strip()
        lang = repo.get("language") or ""
        stars = repo.get("stargazers_count", 0)
        parts = [f"[{name}]({repo.get('html_url')})"]
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
        if len(lines) >= MAX_REPOS:
            break

    if not lines:
        lines.append("- (No public repositories found)")
    return "\n".join(lines)


def format_recent_repos(public_repos):
    lines = []
    for repo in public_repos[:MAX_RECENT_REPOS]:
        pushed = repo.get("pushed_at")
        try:
            when = dt.datetime.fromisoformat((pushed or "").replace("Z", "+00:00")).date().isoformat()
        except Exception:
            when = pushed or "-"
        lang = repo.get("language") or "n/a"
        lines.append(f"- {when}: [{repo.get('name')}]({repo.get('html_url')}) ({lang})")
    if not lines:
        lines.append("- (No recently updated repositories)")
    return "\n".join(lines)


def format_activity():
    events = github_get(f"{API_BASE}/users/{GITHUB_USERNAME}/events/public?per_page=30") or []
    lines = []
    for event in events:
        et = event.get("type")
        repo = (event.get("repo") or {}).get("name", "")
        created = event.get("created_at", "")
        try:
            when = dt.datetime.fromisoformat(created.replace("Z", "+00:00")).date().isoformat()
        except Exception:
            when = created

        if et == "PushEvent":
            count = len((event.get("payload") or {}).get("commits", []) or [])
            summary = f"pushed {count} commit(s) to {repo}"
        elif et == "PullRequestEvent":
            action = (event.get("payload") or {}).get("action", "")
            pr = (event.get("payload") or {}).get("pull_request") or {}
            summary = f"{action} PR #{pr.get('number')} in {repo}"
        elif et == "IssuesEvent":
            action = (event.get("payload") or {}).get("action", "")
            issue = (event.get("payload") or {}).get("issue") or {}
            summary = f"{action} issue #{issue.get('number')} in {repo}"
        elif et == "CreateEvent":
            ref_type = (event.get("payload") or {}).get("ref_type", "")
            ref = (event.get("payload") or {}).get("ref", "")
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


def format_languages(public_repos):
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
    ordered = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:6]
    lines = [f"- {lang}: {100.0 * bytes_count / total_bytes:.1f}%" for lang, bytes_count in ordered]
    return "\n".join(lines)


def replace_block(text: str, marker: str, new_content: str) -> str:
    pattern = rf"(<!-- {re.escape(marker)}:START -->)(.*?)(<!-- {re.escape(marker)}:END -->)"
    return re.sub(pattern, rf"\1\n{new_content}\n\3", text, flags=re.S)


def main() -> int:
    readme = README_PATH.read_text(encoding="utf-8")

    public_repos = fetch_public_repos()
    projects = format_projects(public_repos)
    recent_repos = format_recent_repos(public_repos)
    activity = format_activity()
    languages = format_languages(public_repos)
    updated = dt.date.today().isoformat()

    readme = replace_block(readme, "PROJECTS", projects)
    readme = replace_block(readme, "RECENT_REPOS", recent_repos)
    readme = replace_block(readme, "ACTIVITY", activity)
    readme = replace_block(readme, "LANGUAGES", languages)
    readme = replace_block(readme, "UPDATED", updated)

    README_PATH.write_text(readme, encoding="utf-8")
    print("README updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
