---
name: take-issue
description: Take a GitHub issue end to end - read it, branch, implement it, push the branch to the user's fork, wait for the user to open the PR, then follow that PR's review comments. Use when the user points at an issue URL and says to take it, implement it, or work on it, typically as /take-issue <issue-url>. Hands off to the pr-watch skill once the PR exists.
---

# Taking an issue

Four phases: read the issue, implement it on a branch, push to the fork, then wait for the
PR and follow it. The user opens the PR - you never open it for them unless they ask.

## 1. Read the issue

```
python3 scripts/issue.py <issue-url>          # or owner/repo#N
```

Prints the title, labels, body and every comment. Read the comments too - the issue is
often narrowed or redefined there. If the issue leaves a real decision open (which API,
which behaviour on conflict), ask the user before writing code rather than guessing.

## 2. Branch

Work in the local clone of the repository the issue belongs to. Clones live under
`~/repos`, normally `~/repos/<repo>` - if the working directory is not that repository,
look there. If no clone is found, report it in the log and stop: do not clone, do not ask,
do not do anything else.

Start from an up-to-date upstream base:

```
git fetch <upstream-remote>
git switch -c issue-<N>-<short-slug> <upstream-remote>/<default-branch>
```

Never commit onto the default branch. If the tree is dirty, stop and ask - don't stash
someone else's work.

## 3. Implement

- Match the surrounding code; the issue is the spec, not an invitation to refactor.
- Run the repository's own tests/linters before pushing, and say in the chat what you ran.
- Commit in the repository's style. Reference the issue in the body (`Refs #<N>`), not as
  a `Fixes` line - whether it closes the issue is the PR author's call.

## 4. Push to the fork

```
git remote -v                                  # identify the fork remote
git push -u <fork-remote> HEAD:issue-<N>-<slug>
```

Push to the user's fork, never to upstream. If no fork remote exists, ask for its URL
instead of creating one. Then give the user the branch name and the compare link
(`https://github.com/<upstream>/compare/<default-branch>...<fork-owner>:<branch>`) so they
can open the PR, plus a short suggested PR title and body.

## 5. Wait for the PR

```
python3 scripts/wait_for_pr.py --head <fork-owner>:<branch> \
    --repo <upstream-owner>/<repo> --repo <fork-owner>/<repo>
```

Run it in the background; it polls until a PR with that head appears, prints
`owner/repo#N`, and exits - which wakes you. Checking both repositories covers a PR opened
upstream and one opened in the fork.

While waiting, do nothing else to the branch. If the user comes back with changes before
the PR exists, amend or add commits and push again - the wait keeps running.

## 6. Follow the PR

Once the PR number is known, switch to the **pr-watch** skill and watch that target (both
targets if the branch feeds two PRs). Everything after this point - reacting, fixing,
pushing, replying - is pr-watch's protocol; don't reimplement it here.
