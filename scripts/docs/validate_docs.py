#!/usr/bin/env python3
"""Validate CT docs structure for canonical documentation governance."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
README = DOCS / "README.md"

CANONICAL_DOCS = [
    DOCS / "overview" / "project-context.md",
    DOCS / "continuous-model" / "pn-single.md",
    DOCS / "visualization" / "ui-guide.md",
    DOCS / "training" / "training-guide.md",
    DOCS / "td-petri" / "td-petri-guide.md",
]

REQUIRED_SECTIONS = [
    "## Abstract",
    "## Scope",
    "## Architecture or Data Flow",
    "## Interfaces",
    "## Behavior Rules",
    "## Examples",
    "## Edge Cases",
    "## Related Docs",
    "## Change Notes",
]

STALE_KEYWORDS = ["Env_PN_Single_PlaceObs", "--place-obs"]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_canonical_exists() -> list[str]:
    errors: list[str] = []
    for doc in CANONICAL_DOCS:
        if not doc.exists():
            errors.append(f"缺失主文档: {doc.relative_to(ROOT)}")
    return errors


def check_required_sections() -> list[str]:
    errors: list[str] = []
    for doc in CANONICAL_DOCS:
        if not doc.exists():
            continue
        text = read_text(doc)
        for section in REQUIRED_SECTIONS:
            if section not in text:
                errors.append(f"{doc.relative_to(ROOT)} 缺少章节: {section}")
    return errors


def check_index_coverage() -> list[str]:
    errors: list[str] = []
    if not README.exists():
        return ["缺失 docs/README.md"]
    readme = read_text(README)
    for doc in CANONICAL_DOCS:
        rel = doc.relative_to(DOCS).as_posix()
        if rel not in readme:
            errors.append(f"docs/README.md 未索引主文档: {rel}")
    return errors


def iter_markdown_files() -> list[Path]:
    return sorted(DOCS.rglob("*.md"))


def check_links() -> list[str]:
    errors: list[str] = []
    link_pat = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for file in iter_markdown_files():
        text = read_text(file)
        for m in link_pat.finditer(text):
            target = m.group(1).strip()
            if not target:
                continue
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            base = unquote(target.split("#", 1)[0])
            if not base:
                continue
            if ":" in base and not base.startswith("./") and not base.startswith("../"):
                # Skip absolute windows paths in legacy docs.
                continue
            p = (file.parent / base).resolve()
            if not p.exists():
                errors.append(
                    f"坏链接: {file.relative_to(ROOT)} -> {target}"
                )
    return errors


def check_stale_keywords() -> list[str]:
    errors: list[str] = []
    for doc in CANONICAL_DOCS:
        if not doc.exists():
            continue
        text = read_text(doc)
        for kw in STALE_KEYWORDS:
            if kw in text:
                errors.append(f"主文档包含过时关键词 '{kw}': {doc.relative_to(ROOT)}")
    return errors


def main() -> int:
    checks = [
        ("主文档存在", check_canonical_exists),
        ("主文档章节完整", check_required_sections),
        ("索引覆盖", check_index_coverage),
        ("Markdown 链接", check_links),
        ("过时关键词", check_stale_keywords),
    ]

    all_errors: list[str] = []
    for name, fn in checks:
        errs = fn()
        if errs:
            print(f"[FAIL] {name}")
            for e in errs:
                print(f"  - {e}")
            all_errors.extend(errs)
        else:
            print(f"[PASS] {name}")

    if all_errors:
        print(f"\n验证失败，共 {len(all_errors)} 项问题。")
        return 1

    print("\n验证通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
