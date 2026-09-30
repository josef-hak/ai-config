---
name: pr-watch
description: Watch a GitHub pull request for new comments and act on each one - fix the code, commit, push, react and reply. Use when the user says to follow their comments on a PR, to keep watching a PR, or to fix whatever they comment there. Covers the token setup, the polling, and the reaction/reply protocol.
---

# Watching a PR and acting on its comments

The loop: a comment appears, you read it, fix the code, push, and say so on the PR.

## Token

Unauthenticated reads are 60 requests an hour per IP, which one watch exhausts; writing
needs a token anyway.

- Store it outside any repository, never echoed into the transcript:
  `~/.config/gh-prs-token`, mode 600. Create the file, chmod it, write the token last.
- A **fine-grained** token can comment without pushing: *Pull requests: read and write*,
  *Contents: no access*. Issue comments (the Conversation tab) may also need *Issues: read
  and write*. Merging needs Contents: write.
- Fine-grained tokens only reach repositories owned by the token's account, or org
  repositories the org approved. Without approval the token still reads public data at
  5000/hour but cannot write - draft the replies for the user instead.
- A classic token with `public_repo` writes to every public repository the account can
  write to. Prefer fine-grained; if the user picks classic, say what it covers.
- A classic token with **no scopes** lifts reading to 5000/hour and writes nothing - the
  right choice when only the watching matters.

## Two accounts

The token's account is what comments and reactions come from. When it differs from the
account being watched, report every comment except the token's own - `scripts/watch_pr.py`
resolves the token's login through `/user` and skips it. If the two are the same, pass
`--self-ids` and the watch skips the ids `scripts/pr_api.py` records after each write.

Never mark your own comments with a marker in the body - HTML comments are visible in the
raw markdown and in the API.

## Running the watch

```
python3 scripts/watch_pr.py --target <owner>/<repo>#<pr> [--target ...]
```

Run it through the Monitor tool with `persistent: true`, one target per PR that matters
(e.g. the upstream PR carrying the reviewers plus one in the user's fork). If both share
the same head branch, one push updates both.

The script polls one endpoint per cycle in rotation (issue comments, review comments,
reviews), uses ETags, and checks the free `/rate_limit` endpoint before spending anything,
waiting out the reset rather than hammering 403s. With a token it polls every 30s; without
one, every 150s.

Baseline: on first run every existing comment is recorded and ignored, so only what arrives
afterwards is reported. The state file lives next to the script; delete it to re-baseline.

## The protocol per comment

1. **React** as soon as you have read it: `pr_api.py react <repo> <comment_id> eyes` - the
   signal that the comment is being worked on.
2. **Fix** the code. Reproduce what the comment describes before believing it; read failing
   checks from the CI annotations (`/repos/{o}/{r}/check-runs/{id}/annotations`).
3. **Commit** one commit per comment, message in the repository's style, and **push** to the
   PR's head branch. Push explicitly (`git push <remote> HEAD:<branch>`) when the local
   branch tracks something else. Never force-push a branch under review without asking.
4. **Swap the reaction**: `pr_api.py unreact <repo> <comment_id> eyes` then
   `pr_api.py react <repo> <comment_id> rocket`. Eyes means in progress, rocket means pushed.
   GitHub allows only `+1 -1 laugh confused heart hooray rocket eyes` - there is no check mark.
5. **Reply** on the PR, starting with a tick: `pr_api.py reply <repo> <pr> "✅ Fixed in ..."`.
   Say what the cause was and what the fix does, name the commit, keep it short. Use
   `pr_api.py reply-thread <repo> <pr> <comment_id> "..."` to answer inside a review thread.

Report the same to the user in the chat, including the commit sha.

## When not to push

A comment that asks a question, disagrees with the approach, or needs a decision the user
has not made is not a fix. React, answer, and bring it to the user. The same goes for a
comment on someone else's review that the user has not endorsed.
