#!/usr/bin/env python3
"""Claude Code hook: send a Matrix DM when Claude is blocked or done.

For PermissionRequest and Stop it then waits for the target's reply and answers the hook
with it. Reads the hook JSON from stdin. Never fails the hook - errors go to stderr, exit 0.
"""
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HOMESERVER = os.environ.get("MATRIX_HOMESERVER", "https://matrix.jhak.cz")
TOKEN_FILE = os.path.expanduser(os.environ.get("MATRIX_TOKEN_FILE", "~/.config/matrix-token"))
TO_LOCALPART = os.environ.get("MATRIX_TO", "admin")
CACHE_FILE = os.path.expanduser("~/.cache/claude-matrix-hook.json")
MAX_LEN = 600
WAIT = int(os.environ.get("MATRIX_WAIT", "180"))
ALLOW = {"y", "yes", "a", "ano", "ok"}
DENY = {"n", "no", "ne"}


def api(token, method, path, body=None, timeout=5):
    req = urllib.request.Request(
        HOMESERVER + "/_matrix/client/v3" + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def q(s):
    return urllib.parse.quote(s, safe="")


def target_mxid(token):
    me = api(token, "GET", "/account/whoami")["user_id"]
    if TO_LOCALPART.startswith("@"):
        return TO_LOCALPART, me
    # server name may differ from the homeserver host (well-known delegation)
    return "@%s:%s" % (TO_LOCALPART, me.split(":", 1)[1]), me


def dm_room(token):
    try:
        with open(CACHE_FILE) as f:
            cache = json.load(f)
        if cache.get("to") == TO_LOCALPART and cache.get("hs") == HOMESERVER:
            return cache["room_id"]
    except (OSError, ValueError, KeyError):
        pass

    to, me = target_mxid(token)
    direct = {}
    try:
        direct = api(token, "GET", "/user/%s/account_data/m.direct" % q(me))
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    joined = set(api(token, "GET", "/joined_rooms")["joined_rooms"])
    room_id = next((r for r in direct.get(to, []) if r in joined), None)
    if not room_id:
        room_id = api(token, "POST", "/createRoom", {
            "is_direct": True,
            "invite": [to],
            "preset": "trusted_private_chat",
        })["room_id"]
        direct.setdefault(to, []).append(room_id)
        api(token, "PUT", "/user/%s/account_data/m.direct" % q(me), direct)

    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump({"to": TO_LOCALPART, "hs": HOMESERVER, "room_id": room_id}, f)
    return room_id


def build_message(ev):
    name = ev.get("hook_event_name", "")
    project = os.path.basename(ev.get("cwd") or os.getcwd())
    where = "[%s @ %s]" % (project, socket.gethostname().split(".")[0])
    if name == "PermissionRequest":
        inp = ev.get("tool_input") or {}
        detail = inp.get("command") or inp.get("file_path") or inp.get("url") or json.dumps(inp)
        text = "🔐 %s %s: %s" % (where, ev.get("tool_name", "tool"), detail)
    elif name == "Notification":
        kind = ev.get("notification_type", "")
        icon = "🔐" if kind == "permission_prompt" else "⏸️"
        text = "%s %s %s" % (icon, where, ev.get("message", "Claude needs your attention"))
    elif name == "Stop":
        last = (ev.get("last_assistant_message") or "").strip()
        text = "✅ %s Task done" % where
        if last:
            text += "\n\n" + last
    else:
        text = "ℹ️ %s %s" % (where, name or "event")
    return text if len(text) <= MAX_LEN else text[:MAX_LEN - 1] + "…"


def send(token, text):
    """Send text, return the room id."""
    room = dm_room(token)
    path = "/rooms/%s/send/m.room.message/%s" % (q(room), uuid.uuid4().hex)
    try:
        api(token, "PUT", path, {"msgtype": "m.text", "body": text})
    except urllib.error.HTTPError as e:
        if e.code != 403:
            raise
        # left or forgotten room - drop the cache and retry once with a fresh lookup
        os.remove(CACHE_FILE)
        room = dm_room(token)
        api(token, "PUT", "/rooms/%s/send/m.room.message/%s" % (q(room), uuid.uuid4().hex),
            {"msgtype": "m.text", "body": text})
    return room


def sync(token, room, since=None, timeout_ms=0):
    filt = json.dumps({"room": {"rooms": [room], "timeline": {"limit": 50 if since else 0}},
                       "presence": {"not_types": ["*"]}, "account_data": {"not_types": ["*"]}})
    path = "/sync?timeout=%d&filter=%s" % (timeout_ms, q(filt))
    if since:
        path += "&since=" + q(since)
    return api(token, "GET", path, timeout=timeout_ms / 1000 + 10)


def wait_reply(token, room, since, sender):
    """First text message from sender after `since`, or None after WAIT seconds."""
    deadline = time.time() + WAIT
    while (left := deadline - time.time()) > 0:
        r = sync(token, room, since, int(min(left, 30) * 1000))
        since = r["next_batch"]
        timeline = r.get("rooms", {}).get("join", {}).get(room, {}).get("timeline", {})
        for e in timeline.get("events", []):
            body = (e.get("content") or {}).get("body", "").strip()
            if e.get("type") == "m.room.message" and e.get("sender") == sender and body:
                return body
    return None


def decide(name, reply):
    if name == "Stop":
        return {"decision": "block", "reason": "Reply from the user via Matrix: " + reply}
    word, _, rest = reply.partition(" ")
    word = word.lower().rstrip(".!,")
    if word in ALLOW:
        decision = {"behavior": "allow"}
    else:
        # anything that is not a plain yes is a deny; free text is passed to Claude as the reason
        msg = rest.strip() if word in DENY else reply
        decision = {"behavior": "deny", "message": msg or "Denied by the user via Matrix"}
    return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}


def main():
    try:
        with open(TOKEN_FILE) as f:
            token = f.read().strip()
    except OSError:
        return
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    ev = json.loads(raw) if raw.strip() else {"hook_event_name": "Test", "cwd": os.getcwd()}
    name = ev.get("hook_event_name")
    text = build_message(ev)
    if name not in ("PermissionRequest", "Stop"):
        send(token, text)
        return
    hint = "y / n [reason]" if name == "PermissionRequest" else "a reply continues the session"
    # ❓ up front marks messages that wait for an answer; the rest are info only
    text = "❓ %s\n\n↩️ Reply: %s (%d min)" % (text, hint, WAIT // 60)
    sender = target_mxid(token)[0]
    # take the sync position before sending so older messages are never read as the answer
    since = sync(token, dm_room(token))["next_batch"]
    room = send(token, text)
    reply = wait_reply(token, room, since, sender)
    if reply:
        print(json.dumps(decide(name, reply)))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("matrix-hook: %s" % e, file=sys.stderr)
    sys.exit(0)
