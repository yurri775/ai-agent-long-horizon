"""Allowlisted tools for the agent.

Every file operation is sandboxed to ./workspace — the agent cannot read or write
anywhere else on disk. This is a lightweight sandbox; for true isolation (running
untrusted code) swap in E2B or a Docker container (see README).

Each tool exposes:
  - a JSON schema in TOOLS (sent to Claude)
  - a Python implementation in TOOL_FUNCS
  - RISKY_TOOLS: tools that require human confirmation before running
"""

from __future__ import annotations

import ast
import operator
from pathlib import Path

WORKSPACE = Path(__file__).parent / "workspace"


def _safe_path(filename: str) -> Path:
    """Resolve a path and refuse anything that escapes the workspace."""
    WORKSPACE.mkdir(exist_ok=True)
    root = WORKSPACE.resolve()
    target = (root / filename).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path '{filename}' escapes the workspace sandbox")
    return target


# --------------------------------------------------------------------------- #
# Tool implementations                                                         #
# --------------------------------------------------------------------------- #
def write_file(filename: str, content: str) -> str:
    path = _safe_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {filename}."


def read_file(filename: str) -> str:
    path = _safe_path(filename)
    if not path.exists():
        return f"File not found: {filename}"
    return path.read_text(encoding="utf-8")


def list_files() -> str:
    WORKSPACE.mkdir(exist_ok=True)
    files = [str(p.relative_to(WORKSPACE)) for p in WORKSPACE.rglob("*") if p.is_file()]
    return "\n".join(sorted(files)) or "(workspace is empty)"


_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError("unsupported expression")


def calculator(expression: str) -> str:
    """Evaluate a plain arithmetic expression (no names, no calls)."""
    try:
        tree = ast.parse(expression, mode="eval")
        return str(_eval_node(tree.body))
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"


# --------------------------------------------------------------------------- #
# Registry                                                                     #
# --------------------------------------------------------------------------- #
TOOL_FUNCS = {
    "write_file": write_file,
    "read_file": read_file,
    "list_files": list_files,
    "calculator": calculator,
}

RISKY_TOOLS = {"write_file"}  # ask a human before these

TOOLS = [
    {
        "name": "write_file",
        "description": "Write text to a file in the workspace (overwrites if it exists).",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "path inside the workspace"},
                "content": {"type": "string", "description": "the text to write"},
            },
            "required": ["filename", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a text file from the workspace.",
        "input_schema": {
            "type": "object",
            "properties": {"filename": {"type": "string"}},
            "required": ["filename"],
        },
    },
    {
        "name": "list_files",
        "description": "List all files currently in the workspace.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "calculator",
        "description": "Evaluate a basic arithmetic expression, e.g. '17 * 23'.",
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    },
]


def run_tool(name: str, tool_input: dict) -> str:
    """Dispatch a tool call to its implementation (allowlist-enforced)."""
    if name not in TOOL_FUNCS:
        return f"Error: tool '{name}' is not allowed."
    try:
        return TOOL_FUNCS[name](**tool_input)
    except Exception as exc:  # noqa: BLE001
        return f"Error running {name}: {exc}"
