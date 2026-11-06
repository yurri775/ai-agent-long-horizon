"""A tiny test set for the agent.

Each task has a `check()` that inspects the workspace afterwards and returns True/False.
Run it to get a pass rate — the agent's equivalent of unit tests.

Usage:
    python tasks.py                 # runs all tasks with --auto, prints a pass rate
"""

from __future__ import annotations

from pathlib import Path

import agent
import tools

WORKSPACE = tools.WORKSPACE


def _read(name):
    path = WORKSPACE / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


TASKS = [
    {
        "task": "Write a file named hello.txt whose content is exactly: Hello, world!",
        "check": lambda: _read("hello.txt").strip() == "Hello, world!",
    },
    {
        "task": "Compute 17 * 23 using the calculator tool and write only the number "
                "to a file named product.txt.",
        "check": lambda: "391" in _read("product.txt"),
    },
    {
        "task": "Create notes.md with a markdown H1 title '# Notes' on the first line, "
                "then read it back to confirm it is correct.",
        "check": lambda: _read("notes.md").lstrip().startswith("# Notes"),
    },
]


def main():
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).parent / ".env")
    except ImportError:
        pass

    passed = 0
    for i, case in enumerate(TASKS, 1):
        print(f"\n### Task {i}/{len(TASKS)}: {case['task']}")
        agent.run(case["task"], max_steps=8, auto=True, verbose=True)
        ok = False
        try:
            ok = bool(case["check"]())
        except Exception as exc:  # noqa: BLE001
            print(f"  check raised: {exc}")
        passed += int(ok)
        print(f"  → {'PASS ✓' if ok else 'FAIL ✗'}")

    print("\n" + "─" * 60)
    print(f"Pass rate: {passed}/{len(TASKS)} = {passed / len(TASKS) * 100:.0f}%")


if __name__ == "__main__":
    main()
