#!/usr/bin/env python3
"""Wait until a pull request exists for a head branch, then print its target.

    wait_for_pr.py --head <fork-owner>:<branch> --repo owner/repo [--repo owner/fork]

Polls every --interval seconds (60 with a token, 180 without) and exits 0 after
printing "owner/repo#N" for the first match - which is what pr-watch takes as a
--target. Exits 1 on timeout. The PR is expected to be opened by a human, so the
wait is long by design; run it in the background and let it wake you.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"


def token():
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"].strip()
    try:
        return open(os.path.expanduser("~/.config/gh-prs-token")).read().strip()
    except OSError:
        return ""


TOKEN = token()


def get(url):
    h = {"Accept": "application/vnd.github+json", "User-Agent": "take-issue"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"[wait] HTTP {e.code} on {url}", flush=True)
        return []
    except Exception as e:  # network blips must not end the wait
        print(f"[wait] {e}", flush=True)
        return []


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--head", required=True, help="<owner>:<branch> of the PR head")
    p.add_argument("--repo", action="append", required=True, help="repeatable: where to look")
    p.add_argument("--state", default="open", choices=["open", "all"])
    p.add_argument("--interval", type=int, default=60 if TOKEN else 180)
    p.add_argument("--timeout", type=int, default=86400, help="seconds; 0 waits forever")
    a = p.parse_args()

    deadline = time.time() + a.timeout if a.timeout else None
    while deadline is None or time.time() < deadline:
        for repo in a.repo:
            for pr in get(f"{API}/repos/{repo}/pulls?state={a.state}&head={a.head}&per_page=100"):
                print(f"{repo}#{pr['number']}  {pr['html_url']}")
                return 0
        time.sleep(a.interval)
    print("[wait] timed out", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
