"""A long-horizon agent: plan → act → check, with guardrails.

The agent runs a tool-use loop against the Claude API until the task is done or a
guardrail stops it. Guardrails:
  - allowlist   : it can only call tools defined in tools.py
  - sandbox     : file tools are confined to ./workspace
  - max_steps   : hard cap on loop iterations
  - budget      : hard cap on total tokens spent
  - human gate  : risky tools ask for confirmation (unless --auto)
  - logging     : every step is written to logs/run-<ts>.jsonl

CLI:
    python agent.py "Research X and write a short report to report.md"
    python agent.py "..." --auto --max-steps 15 --budget 80000
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import tools

HERE = Path(__file__).parent
LOG_DIR = HERE / "logs"

MODEL = "claude-haiku-5-5"  # override via env in your own runs if you like

SYSTEM_PROMPT = (
    "You are an autonomous agent that completes multi-step tasks.\n"
    "Work in three phases:\n"
    "1. PLAN  — briefly outline the steps you will take.\n"
    "2. ACT   — use the available tools, one step at a time.\n"
    "3. CHECK — before finishing, verify your work (e.g. read back files you wrote).\n"
    "When the task is fully done, reply with a short final summary and no tool calls."
)


def _log(logfile, record):
    with open(logfile, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _confirm(name, tool_input):
    print(f"\n⚠  The agent wants to run a risky tool: {name}({tool_input})")
    return input("   Allow? [y/N] ").strip().lower() == "y"


def run(task, max_steps=10, budget=50_000, auto=False, verbose=True):
    """Run the agent loop. Returns the final text answer (or a stop reason)."""
    from anthropic import Anthropic

    client = Anthropic()  # reads ANTHROPIC_API_KEY
    LOG_DIR.mkdir(exist_ok=True)
    logfile = LOG_DIR / f"run-{int(time.time())}.jsonl"
    _log(logfile, {"event": "start", "task": task, "max_steps": max_steps, "budget": budget})

    messages = [{"role": "user", "content": task}]
    spent = 0

    for step in range(1, max_steps + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=tools.TOOLS,
            messages=messages,
        )
        spent += response.usage.input_tokens + response.usage.output_tokens

        used_tools = [b.name for b in response.content if b.type == "tool_use"]
        _log(logfile, {"event": "step", "n": step, "stop_reason": response.stop_reason,
                       "tokens": spent, "tools": used_tools})
        if verbose:
            print(f"[step {step}] stop={response.stop_reason} tokens={spent} tools={used_tools}")

        if spent > budget:
            _log(logfile, {"event": "stopped", "reason": "budget_exceeded", "tokens": spent})
            return f"Stopped: token budget exceeded ({spent} > {budget})."

        if response.stop_reason != "tool_use":
            final = "".join(b.text for b in response.content if b.type == "text").strip()
            _log(logfile, {"event": "done", "steps": step, "tokens": spent})
            return final

        # Execute every tool call in this turn.
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name in tools.RISKY_TOOLS and not auto and not _confirm(block.name, block.input):
                output = "Denied by human."
            else:
                output = tools.run_tool(block.name, block.input)
            _log(logfile, {"event": "tool", "name": block.name, "input": block.input,
                           "output": output[:500]})
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
        messages.append({"role": "user", "content": results})

    _log(logfile, {"event": "stopped", "reason": "max_steps", "tokens": spent})
    return f"Stopped: reached max steps ({max_steps})."


def main():
    try:
        from dotenv import load_dotenv

        load_dotenv(HERE / ".env")
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", help="the task for the agent to complete")
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--budget", type=int, default=50_000, help="max total tokens")
    parser.add_argument("--auto", action="store_true", help="skip human confirmation")
    args = parser.parse_args()

    result = run(args.task, max_steps=args.max_steps, budget=args.budget, auto=args.auto)
    print("\n" + "=" * 60)
    print(result)


if __name__ == "__main__":
    main()
