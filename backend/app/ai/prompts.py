"""Prompt repository (ai-contracts §18; orchestration §39).

Prompts are versioned Markdown files with a YAML header declaring role, authority, expected
schema, restrictions and output budget. The system message for a role is assembled as:

    # role: <name>                 ← first line; FakeModelProvider keys fixtures on it
    <common role rules>
    <role prompt body>
    <output schema, when structured>

and its hash is stored on every ModelRun so behaviour changes can be traced to a prompt change.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from app.ai.roles import RoleSpec

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
HEADER = re.compile(r"^---\n(.*?)\n---\n", re.S)


class PromptError(ValueError):
    pass


@dataclass(frozen=True)
class Prompt:
    id: str
    version: int
    header: dict[str, Any]
    body: str
    path: Path

    @property
    def hash(self) -> str:
        return hashlib.sha256(
            (self.body + json.dumps(self.header, sort_keys=True)).encode()
        ).hexdigest()


def compact_schema(model: type[BaseModel]) -> str:
    schema = model.model_json_schema()
    defs = schema.get("$defs", {})

    def render(node: dict[str, Any], indent: int) -> str:
        if "$ref" in node:
            node = defs[node["$ref"].split("/")[-1]]
        if "anyOf" in node:
            parts = [render(n, indent) for n in node["anyOf"]]
            return "|".join(dict.fromkeys(parts))
        if "enum" in node:
            return "|".join(json.dumps(v) for v in node["enum"])
        t = node.get("type")
        if t == "object" and "properties" in node:
            pad = "  " * (indent + 1)
            req = set(node.get("required", []))
            lines = []
            for name, sub in node["properties"].items():
                opt = "" if name in req else "?"
                lines.append(f'{pad}"{name}"{opt}: {render(sub, indent + 1)}')
            return "{\n" + ",\n".join(lines) + "\n" + "  " * indent + "}"
        if t == "object":
            return "{}"
        if t == "array":
            return "[" + render(node.get("items", {}), indent) + "]"
        if t == "null":
            return "null"
        return t or "any"

    return render(schema, 0) + "\n(? marks optional keys; omit them or use null)"


class PromptRepository:
    def __init__(self, root: Path = PROMPTS_DIR) -> None:
        self.root = root
        self._cache: dict[tuple[str, int], Prompt] = {}
        self._index: dict[str, dict[int, Path]] = {}
        for path in root.rglob("*_v*.md"):
            m = re.match(r"(.+)_v(\d+)\.md$", path.name)
            if m:
                self._index.setdefault(m.group(1), {})[int(m.group(2))] = path

    def versions(self, prompt_id: str) -> list[int]:
        return sorted(self._index.get(prompt_id, {}))

    def get(self, prompt_id: str, version: int | None = None) -> Prompt:
        versions = self._index.get(prompt_id)
        if not versions:
            raise PromptError(f"no prompt {prompt_id!r} under {self.root}")
        version = version or max(versions)
        key = (prompt_id, version)
        if key not in self._cache:
            path = versions.get(version)
            if path is None:
                raise PromptError(f"prompt {prompt_id!r} has no version {version}")
            text = path.read_text(encoding="utf-8")
            m = HEADER.match(text)
            if not m:
                raise PromptError(f"{path.name}: missing YAML header")
            header = yaml.safe_load(m.group(1)) or {}
            if header.get("id") != prompt_id or int(header.get("version", 0)) != version:
                raise PromptError(f"{path.name}: header id/version do not match the filename")
            self._cache[key] = Prompt(prompt_id, version, header, text[m.end() :].strip(), path)
        return self._cache[key]

    def common_rules(self) -> Prompt:
        return self.get("common_role_rules")

    @staticmethod
    def schema_text(model: type[BaseModel]) -> str:
        """A compact skeleton (types, enums, optionality) — a fraction of the tokens of the
        full JSON schema, which matters at 280 prompt tokens/s."""
        return "Output JSON shape (follow exactly; no extra keys):\n" + compact_schema(model)

    def system_text(self, spec: RoleSpec, *, version: int | None = None) -> tuple[str, Prompt]:
        p = self.get(spec.prompt_id, version)
        parts = [f"# role: {spec.name}", self.common_rules().body, p.body]
        if spec.output_model is not None:
            parts.append(self.schema_text(spec.output_model))
        return "\n\n".join(parts), p
