---
name: matrix-hook
description: Matrix DM notifications from Claude Code hooks - a message to @admin on matrix.jhak.cz whenever Claude is blocked (permission prompt, question dialog) or finishes a task. Use when the user invokes /matrix-hook, wants to set up, test, enable or disable these notifications, or asks why one did not arrive.
---

# Matrix notifications on blocked / done

`scripts/notify.py` is a hook command: it reads the hook JSON on stdin and sends a DM
from the token's account to `@admin:<server>` (server taken from the token's own user id).
It always exits 0, so a Matrix outage never blocks Claude.

## Events

| Hook | Matcher | Message |
|------|---------|---------|
| `Notification` | `permission_prompt\|elicitation_dialog` | 🔐 / ⏸️ + Claude's notification text |
| `Stop` | - | ✅ Task done + start of the last assistant message |

Every message is prefixed with `[<project dir> @ <host>]` and capped at 600 chars.
`idle_prompt` is left out - it duplicates `Stop` a minute later.

## Setup

1. Token of a bot/user account on matrix.jhak.cz in `~/.config/matrix-token`, mode 600.
   Create the file, chmod it, write the token last; never echo it into the transcript.
   No token file → the hook silently does nothing.
2. Hooks in `~/.claude/settings.json` (already in this repo's `claude/settings.json`):

```json
"hooks": {
  "Notification": [{"matcher": "permission_prompt|elicitation_dialog",
    "hooks": [{"type": "command", "command": "python3 ~/.claude/skills/matrix-hook/scripts/notify.py", "timeout": 15}]}],
  "Stop": [{"hooks": [{"type": "command", "command": "python3 ~/.claude/skills/matrix-hook/scripts/notify.py", "timeout": 15}]}]
}
```

3. Test: `python3 ~/.claude/skills/matrix-hook/scripts/notify.py </dev/null` sends a test
   message. Errors are printed to stderr.

The first send creates an unencrypted DM room, invites the target, records it in `m.direct`
and caches the room id in `~/.cache/claude-matrix-hook.json`. Delete the cache to force a
new lookup. The target must accept the invite once.

## Overrides (env)

`MATRIX_HOMESERVER` (default `https://matrix.jhak.cz`), `MATRIX_TOKEN_FILE`,
`MATRIX_TO` (localpart or full `@user:server`, default `admin`).

## Disabling

Remove the two hook entries, or `"disableAllHooks": true` temporarily.
