#!/usr/bin/env python3
"""Quota check for the fable-orchestration routing policy.

Reads the Codex (ChatGPT plan) rate limits through `codex app-server`
(`account/rateLimits/read`) and combines them with the Claude-side status the
main loop reads from the session (get_session -> external_metadata.rate_limit_info).
Prints JSON with both sides and a routing mode.

Usage:
  python3 quota_check.py [--claude-status allowed|allowed_warning|rejected] [--claude-overage]

Modes:
  balanced     both sides healthy: GPT-suitable lanes go to Codex, the rest to Claude
  gpt-first    Claude is warning or on overage: send every delegable lane to Codex
  claude-first Codex usage is high (>= 70%): Codex only for second opinions
  claude-only  Codex not logged in, unreachable, or at its limit
  gpt-only     Claude is rejected (limit reached): Codex carries all delegated work
"""
import argparse
import json
import select
import shutil
import subprocess
import sys
import time

HIGH = 70   # usage percent at which a side is treated as running low
LIMIT = 90  # usage percent at which a side is treated as exhausted


def read_codex_limits(timeout=25):
    if not shutil.which("codex"):
        return {"available": False, "reason": "codex CLI not installed"}
    status = subprocess.run(["codex", "login", "status"], capture_output=True, text=True)
    out = (status.stdout + status.stderr).strip().splitlines()
    login = out[-1] if out else ""
    if "ChatGPT" not in login:
        return {"available": False, "reason": f"not logged in with ChatGPT ({login or 'no status'})"}
    p = subprocess.Popen(["codex", "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def send(obj):
        p.stdin.write(json.dumps(obj) + "\n")
        p.stdin.flush()

    def wait(msg_id):
        end = time.time() + timeout
        while time.time() < end:
            ready, _, _ = select.select([p.stdout], [], [], 1)
            if not ready:
                continue
            line = p.stdout.readline()
            if not line:
                return None
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") == msg_id:
                return msg
        return None

    try:
        send({"method": "initialize", "id": 1,
              "params": {"clientInfo": {"name": "quota-check", "version": "0.1"}}})
        wait(1)
        send({"method": "initialized"})
        send({"method": "account/rateLimits/read", "id": 2})
        resp = wait(2)
    finally:
        p.kill()
    if not resp or "result" not in resp:
        return {"available": False, "reason": f"rate limit read failed: {resp}"}
    rl = resp["result"].get("rateLimits") or {}
    prim = rl.get("primary") or {}
    sec = rl.get("secondary") or {}
    return {
        "available": True,
        "plan": rl.get("planType"),
        "five_hour_used_percent": prim.get("usedPercent"),
        "five_hour_resets_at": prim.get("resetsAt"),
        "weekly_used_percent": sec.get("usedPercent"),
        "weekly_resets_at": sec.get("resetsAt"),
        "limit_reached": rl.get("rateLimitReachedType"),
        "reset_credits_available": (resp["result"].get("rateLimitResetCredits") or {}).get("availableCount"),
    }


def decide(codex, claude_status, claude_overage):
    if not codex.get("available"):
        return "claude-only", codex.get("reason")
    used = max(codex.get("five_hour_used_percent") or 0, codex.get("weekly_used_percent") or 0)
    codex_out = bool(codex.get("limit_reached")) or used >= LIMIT
    if claude_status == "rejected":
        return ("gpt-only", "Claude limit reached") if not codex_out else ("claude-only", "both sides at limit; pause or wait for reset")
    if codex_out:
        return "claude-only", f"Codex usage {used}% or limit reached"
    if claude_status == "allowed_warning" or claude_overage:
        return "gpt-first", "Claude warning or overage"
    if used >= HIGH:
        return "claude-first", f"Codex usage {used}%"
    return "balanced", f"both healthy (Codex max usage {used}%)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claude-status", default="unknown",
                    help="rate_limit_info.status from get_session (allowed, allowed_warning, rejected)")
    ap.add_argument("--claude-overage", action="store_true",
                    help="rate_limit_info.isUsingOverage is true")
    args = ap.parse_args()
    codex = read_codex_limits()
    mode, why = decide(codex, args.claude_status, args.claude_overage)
    json.dump({"mode": mode, "why": why, "codex": codex,
               "claude": {"status": args.claude_status, "overage": args.claude_overage}},
              sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
