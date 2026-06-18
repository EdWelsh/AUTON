"""`auton-do "<goal>"` — speak a goal, AUTON does the steps (terminal, headless)."""

from __future__ import annotations

import argparse
import sys

from .approval import always_allow, terminal_approval
from .runner import Operator
from .tools import SMTPConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="auton-do",
        description="Tell AUTON a goal; it plans and runs the steps with real tools.",
    )
    parser.add_argument("goal", nargs="+", help="what you want done, in plain English")
    parser.add_argument("--brain", choices=["auto", "llm", "rule"], default="auto")
    parser.add_argument("--model", help="override the brain, e.g. 'use chatgpt' / 'ollama/llama3.1:8b'")
    parser.add_argument("--yes", action="store_true", help="auto-approve irreversible actions (use with care)")
    parser.add_argument("--smtp-host", default="localhost")
    parser.add_argument("--smtp-port", type=int, default=1025)
    parser.add_argument("--from", dest="sender", default="auton@localhost")
    args = parser.parse_args(argv)

    goal = " ".join(args.goal)
    approval = always_allow if args.yes else terminal_approval
    smtp = SMTPConfig(host=args.smtp_host, port=args.smtp_port, sender=args.sender)

    op = Operator(approval=approval, smtp=smtp)
    print(f"AUTON: working on — {goal}\n")
    result = op.run(goal, brain=args.brain, model_request=args.model)

    print(f"\n[brain: {result.brain}]  [workspace: {result.workspace}]")
    if result.actions:
        print("Steps AUTON took:")
        for a in result.actions:
            print(f"  • {a}")
    print(f"\n{result.summary}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
