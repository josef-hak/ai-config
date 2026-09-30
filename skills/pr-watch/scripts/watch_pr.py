#!/usr/bin/env python3
"""Watch pull requests for new comments and print one line per comment.

    watch_pr.py --target owner/repo#123 [--target owner/repo#456] [--self-ids]

One endpoint per cycle in rotation, ETags on every request, and the free
/rate_limit endpoint consulted before spending anything: unauthenticated GitHub
allows 60 requests an hour per IP, a token 5000. Comments written by the token's
own account are skipped, so the watch never reports its own writing as news.

State (ETags, the ids already seen) lives next to this script, one file per
target set; delete it to re-baseline.
"""
import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.expanduser("~/.config/gh-prs-token")
API = "https://api.github.com"


def token():
    """Env first, then a file outside any repository."""
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"].strip()
    try:
        return open(TOKEN_FILE).read().strip()
    except OSError:
        return ""


TOKEN = token()


def headers(extra=None):
    h = {"Accept": "application/vnd.github+json", "User-Agent": "pr-watch"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    h.update(extra or {})
    return h


def get(url, etag=None):
    """Returns (payload, etag). A 304 or an error yields ([], etag)."""
    req = urllib.request.Request(url, headers=headers({"If-None-Match": etag} if etag else None))
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode()), resp.headers.get("ETag", etag)
    except urllib.error.HTTPError as e:
        if e.code != 304:
            print(f"[watch] {url.rsplit('/', 2)[-2:]}: HTTP {e.code}", flush=True)
        return [], etag
    except Exception as e:  # network blips must not end the watch
        print(f"[watch] {e}", flush=True)
        return [], etag


def whoami():
    if not TOKEN:
        return ""
    d, _ = get(f"{API}/user")
    return d.get("login", "") if isinstance(d, dict) else ""


def budget():
    """Remaining core requests; asking does not itself cost anything."""
    d, _ = get(f"{API}/rate_limit")
    if isinstance(d, dict) and "rate" in d:
        return d["rate"]["remaining"], d["rate"]["reset"]
    return 1, 0


def endpoints(targets):
    out = []
    for repo, pr in targets:
        out.append((f"{repo}#{pr}:issue", f"{API}/repos/{repo}/issues/{pr}/comments?per_page=100"))
        out.append((f"{repo}#{pr}:review", f"{API}/repos/{repo}/pulls/{pr}/comments?per_page=100"))
        out.append((f"{repo}#{pr}:reviews", f"{API}/repos/{repo}/pulls/{pr}/reviews?per_page=100"))
    return out


def describe(kind, c, repo_pr):
    body = " ".join((c.get("body") or "").split())
    if not body:
        return None
    who = (c.get("user") or {}).get("login", "?")
    where = ""
    if kind.endswith(":review"):
        where = f" [{c.get('path')}:{c.get('line') or c.get('original_line')}]"
    elif kind.endswith(":reviews"):
        where = f" [review {c.get('state')}]"
    if len(body) > 600:
        body = body[:600] + " …"
    return f"NEW COMMENT on {repo_pr} by {who}{where} (id {c['id']}): {body} | {c.get('html_url')}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", action="append", required=True, help="owner/repo#number")
    ap.add_argument("--self-ids", action="store_true",
                    help="token and watched account are the same: skip ids recorded by pr_api.py")
    ap.add_argument("--interval", type=int, default=0)
    args = ap.parse_args()

    targets = []
    for t in args.target:
        repo, _, pr = t.partition("#")
        targets.append((repo, int(pr)))

    eps = endpoints(targets)
    interval = args.interval or (30 if TOKEN else 150)
    state_file = os.path.join(
        DIR, "watch-" + hashlib.sha1(" ".join(sorted(args.target)).encode()).hexdigest()[:10] + ".json")
    mine_file = os.path.join(DIR, "written-ids.txt")

    state = {"etag": {}, "seen": []}
    if os.path.exists(state_file):
        try:
            state = json.load(open(state_file))
        except Exception:
            pass
    seen = set(state.get("seen", []))

    def save():
        state["seen"] = sorted(seen)
        json.dump(state, open(state_file, "w"))

    def written():
        if not args.self_ids:
            return set()
        try:
            return {ln.strip() for ln in open(mine_file) if ln.strip()}
        except OSError:
            return set()

    me = whoami()

    if not seen:
        for kind, url in eps:
            payload, etag = get(url, state["etag"].get(kind))
            state["etag"][kind] = etag
            for c in payload:
                seen.add(f"{kind}:{c['id']}")
        save()
        print(f"[watch] watching {', '.join(args.target)} every {interval}s as "
              f"{me or 'anonymous'}, {len(seen)} existing comment(s) ignored", flush=True)

    i, warned = 0, False
    while True:
        remaining, reset = budget()
        if remaining < 3:
            if not warned:
                print(f"[watch] out of request budget, resuming in "
                      f"{max(0, int(reset - time.time()))}s", flush=True)
                warned = True
            time.sleep(max(30, min(600, int(reset - time.time()) + 5)))
            continue
        warned = False

        kind, url = eps[i % len(eps)]
        i += 1
        payload, etag = get(url, state["etag"].get(kind))
        state["etag"][kind] = etag
        skip = written()
        for c in payload:
            key = f"{kind}:{c['id']}"
            if key in seen:
                continue
            seen.add(key)
            if me and (c.get("user") or {}).get("login") == me:
                continue
            if str(c["id"]) in skip:
                continue
            out = describe(kind, c, kind.split(":")[0])
            if out:
                print(out, flush=True)
        save()
        time.sleep(interval)


if __name__ == "__main__":
    main()
