"""Runtime bundle: hook scripts, MCP servers, and skills shipped inside the CLI.

All assets ship inside this directory so the system installs in one shot with
`pip install cartographer-cli[embed,ui]`. Nothing is downloaded at runtime.

RUNTIME_DIR is the canonical path to this directory. All code that needs to
reference bundled assets (skill files, MCP server scripts) should use it.
"""

from pathlib import Path

RUNTIME_DIR: Path = Path(__file__).parent
SKILLS_DIR: Path = RUNTIME_DIR / "skills"
