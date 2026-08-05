#!/usr/bin/env python3
"""Drop repeated <a name=...> definitions, keeping the first in each page.

An anchor name has to be unique within a page: when it is defined twice, the second definition is
unreachable and every link to it lands on the first. The duplicates here are all one opcode or IDS
number carrying several names - four spellings of trigger 0x40A8, SLOT_AMMO and SLOT_AMMO0 both at
11, LONG_BOW and MAGE_ALL both at 202 - so the first definition is the one links already resolve to
and the one they mean.

The later definitions keep their text and lose only the anchor, which is what the page already does
in practice. This is not the tool for a duplicate caused by a *typo* - one section misnamed after
another - because there the fix is to correct the name, not to delete it; check the report before
applying.

Reports by default; --apply writes the files.
"""

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

SCAN_SUFFIXES = {".htm", ".html", ".md", ".yml", ".yaml"}
SKIP_DIRS = {".git", "_site", ".jekyll-cache", ".sass-cache", "_tools", "vendor", "node_modules"}

# An anchor definition: <a name="..."> ... </a>, with no href (that would be a link, not a target).
ANCHOR = re.compile(r'<a\s+name="([^"]*)"\s*>(.*?)</a>', re.S)


def process(text):
    """Return (new_text, [(line, name)]) for each duplicate definition stripped."""
    seen, removed, out, last = set(), [], [], 0
    for m in ANCHOR.finditer(text):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            continue
        out.append(text[last:m.start()])
        out.append(m.group(2))
        last = m.end()
        removed.append((text.count("\n", 0, m.start()) + 1, name))
    out.append(text[last:])
    return "".join(out), removed


def scan_files():
    for path in sorted(REPO.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        rel = path.relative_to(REPO)
        if SKIP_DIRS.intersection(rel.parts):
            continue
        yield path, rel


def main():
    parser = argparse.ArgumentParser(
        description="Drop repeated <a name=...> definitions, keeping the first in each page.")
    parser.add_argument("--apply", action="store_true", help="write the changes (default: report only)")
    parser.add_argument("--limit", type=int, default=60, help="report lines to print (default: 60)")
    args = parser.parse_args()

    report, files = [], 0
    for path, rel in scan_files():
        text = path.read_text(encoding="utf-8")
        if "<a name=" not in text:
            continue
        new, removed = process(text)
        if not removed:
            continue
        files += 1
        report.extend(f"  {rel}:{line}  name=\"{name}\"" for line, name in removed)
        if args.apply:
            path.write_text(new, encoding="utf-8")

    print(f"  duplicate anchor definitions: {len(report)} in {files} files")
    for line in report[:args.limit]:
        print(line)
    if len(report) > args.limit:
        print(f"  ... ({len(report) - args.limit} more)")
    if args.apply:
        print(f"\n  stripped {len(report)} duplicates.")
    elif report:
        print("\n  Re-run with --apply to write them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
