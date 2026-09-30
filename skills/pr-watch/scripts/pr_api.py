#!/usr/bin/env python3
"""Write to a pull request: reactions, comments, review-thread replies.

    pr_api.py react       owner/repo <comment_id> eyes
    pr_api.py unreact     owner/repo <comment_id> eyes
    pr_api.py reply       owner/repo <pr> "text"
    pr_api.py reply-thread owner/repo <pr> <comment_id> "text"
    pr_api.py checks      owner/repo <sha>            # failing checks for a commit
    pr_api.py annotations owner/repo <check_run_id>   # why a check failed

Ids of comments written here are appended to written-ids.txt next to this script,
which watch_pr.py --self-ids reads when the token and the watched account are the
same. Nothing is added to the comment body.
"""
import json
import os
import sys
import urllib.error
import urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))
WRITTEN = os.path.join(DIR, "written-ids.txt")
API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip() or \
    open(os.path.expanduser("~/.config/gh-prs-token")).read().strip()


def call(method, path, payload=None):
    req = urllib.request.Request(
        f"{API}{path}", method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "pr-api",
            **({"Content-Type": "application/json"} if payload is not None else {}),
        })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:300]}")


def record(comment_id):
    with open(WRITTEN, "a") as f:
        f.write(f"{comment_id}\n")


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, repo = sys.argv[1], sys.argv[2]
    rest = sys.argv[3:]

    if cmd == "react":
        cid, content = rest[0], rest[1]
        out = call("POST", f"/repos/{repo}/issues/comments/{cid}/reactions", {"content": content})
        print(out.get("id"))
    elif cmd == "unreact":
        cid, content = rest[0], rest[1]
        for r in call("GET", f"/repos/{repo}/issues/comments/{cid}/reactions"):
            if r["content"] == content:
                call("DELETE", f"/repos/{repo}/issues/comments/{cid}/reactions/{r['id']}")
                print("removed")
                return
        print("no such reaction")
    elif cmd == "reply":
        pr, body = rest[0], rest[1]
        out = call("POST", f"/repos/{repo}/issues/{pr}/comments", {"body": body})
        record(out["id"])
        print(out["html_url"])
    elif cmd == "reply-thread":
        pr, cid, body = rest[0], rest[1], rest[2]
        out = call("POST", f"/repos/{repo}/pulls/{pr}/comments",
                   {"body": body, "in_reply_to": int(cid)})
        record(out["id"])
        print(out["html_url"])
    elif cmd == "checks":
        for c in call("GET", f"/repos/{repo}/commits/{rest[0]}/check-runs?per_page=100").get("check_runs", []):
            if c["conclusion"] not in ("success", "skipped", "neutral", None):
                print(c["conclusion"], "|", c["name"], "|", c["id"], "|", c["html_url"])
    elif cmd == "annotations":
        for a in call("GET", f"/repos/{repo}/check-runs/{rest[0]}/annotations"):
            print(a.get("path"), a.get("start_line"), "|", a.get("annotation_level"), "|",
                  (a.get("message") or "")[:300])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
