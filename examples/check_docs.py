"""Check public Markdown links, JSON examples and configuration syntax offline."""

import json
import re
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    markdown = sorted(root.glob("*.md")) + sorted((root / "docs").rglob("*.md"))
    links = 0
    for path in markdown:
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", text):
            parsed = urlsplit(target)
            if parsed.scheme or not parsed.path:
                continue
            destination = (path.parent / unquote(parsed.path)).resolve()
            if not destination.is_relative_to(root) or any(
                part in {".local", ".integration"} for part in destination.relative_to(root).parts
            ):
                raise RuntimeError(f"Public link escapes public content: {path.name}: {target}")
            if not destination.exists():
                raise RuntimeError(f"Broken link: {path.relative_to(root)}: {target}")
            links += 1
        for block in re.findall(r"```json\s*\n(.*?)\n```", text, re.S):
            json.loads(block)
        for block in re.findall(r"```toml\s*\n(.*?)\n```", text, re.S):
            tomllib.loads(block)
    for path in (root / "docs").rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
    json.loads((root / "examples/inspector-config.json").read_text(encoding="utf-8"))
    for path in (root / "examples").glob("*.toml"):
        tomllib.loads(path.read_text(encoding="utf-8"))
    print(f"Documentation: {len(markdown)} Markdown files, {links} local links; JSON/TOML valid.")


if __name__ == "__main__":
    main()
