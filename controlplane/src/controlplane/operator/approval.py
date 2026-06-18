"""Approval gates for irreversible actions (plan + confirm before sending/paying)."""

from __future__ import annotations

import sys


def terminal_approval(action: str, detail: str) -> bool:
    """Show the exact irreversible action and wait for an explicit yes."""
    print(f"\n⚠  AUTON wants to perform an irreversible action: {action}", file=sys.stderr)
    print("---", file=sys.stderr)
    print(detail, file=sys.stderr)
    print("---", file=sys.stderr)
    try:
        answer = input("Proceed? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def always_deny(action: str, detail: str) -> bool:
    """Safe default for non-interactive contexts: never act irreversibly."""
    return False


def always_allow(action: str, detail: str) -> bool:
    """Auto-approve (tests / explicit --yes). Use deliberately."""
    return True
