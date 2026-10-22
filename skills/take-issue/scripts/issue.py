#!/usr/bin/env python3
"""Print an issue - title, state, labels, body, comments - as plain text.

    issue.py https://github.com/owner/repo/issues/123
    issue.py owner/repo#123

Reads the token the same way as the pr-watch scripts: $GITHUB_TOKEN, else
~/.config/gh-prs-token. Works unauthenticated on public issues too.
"""
import json
import os
import re
import sys
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


def get(path):
    h = {"Accept": "application/vnd.github+json", "User-Agent": "take-issue"}
    tok = token()
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    try:
        with urllib.request.urlopen(urllib.request.Request(API + path, headers=h), timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:300]}")


def parse(ref):
    m = re.search(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)", ref) or \
        re.match(r"([^/]+)/([^#]+)#(\d+)$", ref)
    if not m:
        sys.exit("expected https://github.com/owner/repo/issues/N or owner/repo#N")
    return f"{m.group(1)}/{m.group(2)}", m.group(3)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    repo, num = parse(sys.argv[1])
    i = get(f"/repos/{repo}/issues/{num}")
    print(f"repo: {repo}")
    print(f"issue: #{num} {i['title']}")
    print(f"state: {i['state']}  author: {i['user']['login']}  "
          f"labels: {', '.join(l['name'] for l in i['labels']) or '-'}")
    print(f"\n{(i.get('body') or '').strip()}\n")
    for c in get(f"/repos/{repo}/issues/{num}/comments?per_page=100"):
        print(f"--- comment by {c['user']['login']} ({c['created_at']})")
        print((c.get("body") or "").strip())


if __name__ == "__main__":
    main()
