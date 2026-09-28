"""Claude-based KG enrichment: calls `claude -p` to extract semantic relationships.

Falls back silently if the `claude` CLI is not on PATH or the call fails.
No model is loaded locally; uses the user's existing Claude Code installation.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass
class EnrichmentResult:
    summary: str = ""
    implements: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)


_PROMPT = """\
Analyze the following source file and extract its knowledge graph relationships.
Return ONLY valid JSON — no markdown fences, no explanation.

File: {path}

```
{text}
```

JSON schema (all fields required, use empty lists if nothing applies):
{{
  "summary": "one sentence describing what this file does",
  "implements": ["spec name, feature name, or requirement ID this file fulfils"],
  "depends_on": ["conceptual dependencies beyond direct imports (other components, services, data models)"],
  "relationships": [
    {{"type": "validates|renders|persists|orchestrates|produces|consumes|configures|extends", "target": "what it acts on"}}
  ]
}}"""

_MAX_FILE_CHARS = 12_000  # ~3k tokens, well inside context
_TIMEOUT = 60


def is_available() -> bool:
    return shutil.which("claude") is not None


def enrich(path: str, text: str) -> EnrichmentResult:
    """Call `claude -p` to extract semantic KG relationships from a file.

    Returns an empty EnrichmentResult on any failure so callers never have to
    handle exceptions from this function.
    """
    if not is_available():
        return EnrichmentResult()

    prompt = _PROMPT.format(path=path, text=text[:_MAX_FILE_CHARS])

    try:
        proc = subprocess.run(
            ["claude", "-p"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return EnrichmentResult()

    if proc.returncode != 0:
        return EnrichmentResult()

    raw = proc.stdout.strip()
    # Strip markdown fences in case Claude wraps the JSON anyway
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:])
        raw = raw.rsplit("```", 1)[0].strip()

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return EnrichmentResult()

    return EnrichmentResult(
        summary=str(data.get("summary", "")),
        implements=list(data.get("implements", [])),
        depends_on=list(data.get("depends_on", [])),
        relationships=[r for r in data.get("relationships", []) if isinstance(r, dict)],
    )
