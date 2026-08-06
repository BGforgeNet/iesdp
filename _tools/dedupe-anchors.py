#!/usr/bin/env python3
"""Find anchor names defined twice in one page, and drop the repeats it can safely drop.

An anchor has to be unique within a page: define one twice and the second is unreachable, so every
link to it lands on the first.

A page names an anchor two ways - name= on an <a>, or id= on any element - and both share one
namespace, so both have to be counted. One element carrying name="x" id="x" is the old dual-anchor
idiom and is a single anchor, not two; counting the attributes rather than the elements reports
those as duplicates that are not there.

Only a repeated `<a name="x">text</a>` is edited, and only in the sources: its text stays and the
anchor goes, which is what the page already did in practice. Anything else is reported instead of
guessed at - a repeat caused by a typo wants the name corrected rather than deleted, and a repeat
coming out of a template wants fixing in the template.

Which is why --site exists. Anchors written by a layout or include (an action's number, an opcode's
opNNN) are not in any source file and only collide once rendered, so they cannot be found here at
all; point --site at a built site to see those. That output is generated and is never edited.

Reports by default; --apply writes the source files.
"""

import argparse
import collections
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

SCAN_SUFFIXES = {".htm", ".html", ".md", ".yml", ".yaml"}
SKIP_DIRS = {".git", "_site", ".jekyll-cache", ".sass-cache", "_tools", "vendor", "node_modules"}

TAG = re.compile(r"<[a-zA-Z][\w-]*\b[^>]*>")
NAME = re.compile(r'\bname="([^"]*)"', re.I)
ID = re.compile(r'\bid="([^"]*)"', re.I)
# The one shape that can be dropped without deciding anything: an anchor wrapping only its text.
PLAIN_ANCHOR = re.compile(r'<a\s+name="([^"]*)"\s*>(.*?)</a>', re.S)


def anchors(text):
    """[(position, name)] in document order, one entry per anchor an element declares."""
    found = []
    for tag in TAG.finditer(text):
        n, i = NAME.search(tag.group(0)), ID.search(tag.group(0))
        for value in dict.fromkeys(v.group(1) for v in (n, i) if v):
            found.append((tag.start(), value))
    return found


def duplicates(text):
    """[(position, name)] for every anchor whose name was already declared earlier in the page."""
    seen, dupes = set(), []
    for pos, name in anchors(text):
        if name in seen:
            dupes.append((pos, name))
        else:
            seen.add(name)
    return dupes


def process(text):
    """Return (new_text, stripped, left_alone) - the repeats removed, and those needing a look."""
    stripped, left_alone, out, last = [], [], [], 0
    for pos, name in duplicates(text):
        m = PLAIN_ANCHOR.match(text, pos)
        line = text.count("\n", 0, pos) + 1
        if not m or m.group(1) != name:
            left_alone.append((line, name))
            continue
        out.append(text[last:m.start()])
        out.append(m.group(2))
        last = m.end()
        stripped.append((line, name))
    out.append(text[last:])
    return "".join(out), stripped, left_alone


def scan_files():
    for path in sorted(REPO.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        rel = path.relative_to(REPO)
        if SKIP_DIRS.intersection(rel.parts):
            continue
        yield path, rel


def audit_site(root, limit):
    """Report duplicates in a built site. Generated output is never edited."""
    pages = collections.Counter()
    shown = 0
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".htm", ".html"}:
            continue
        names = [n for _, n in anchors(path.read_text(encoding="utf-8", errors="replace"))]
        dupes = sorted(k for k, c in collections.Counter(names).items() if c > 1)
        if not dupes:
            continue
        pages[str(path.relative_to(root))] = len(dupes)
        if shown < limit:
            shown += 1
            print(f"  {path.relative_to(root)}: {len(dupes)} -> {dupes[:10]}")
    total = sum(pages.values())
    print(f"\n  {total} anchor names defined twice, across {len(pages)} pages")
    if total:
        print("  These are rendered pages: fix them where they are written, in the layout,")
        print("  the include, or the source page - not in the build output.")
    return 1 if total else 0


def main():
    parser = argparse.ArgumentParser(description="Find anchor names defined twice in one page.")
    parser.add_argument("--apply", action="store_true", help="write the changes (default: report only)")
    parser.add_argument("--site", metavar="DIR", help="audit a built site instead (report only)")
    parser.add_argument("--limit", type=int, default=60, help="report lines to print (default: 60)")
    args = parser.parse_args()

    if args.site:
        return audit_site(args.site, args.limit)

    report, needs_look, files = [], [], 0
    for path, rel in scan_files():
        text = path.read_text(encoding="utf-8")
        new, stripped, left_alone = process(text)
        needs_look.extend((rel, line, name) for line, name in left_alone)
        if not stripped:
            continue
        files += 1
        report.extend(f'  {rel}:{line}  name="{name}"' for line, name in stripped)
        if args.apply:
            path.write_text(new, encoding="utf-8")

    print(f"  repeated anchors that can be dropped: {len(report)} in {files} files")
    for line in report[:args.limit]:
        print(line)
    if len(report) > args.limit:
        print(f"  ... ({len(report) - args.limit} more)")

    if needs_look:
        print(f"\n  {len(needs_look)} repeats left alone - not a plain <a name=...>, so the fix is a")
        print("  judgement (correct the name, or change whatever writes it):")
        for rel, line, name in needs_look[:args.limit]:
            print(f'    {rel}:{line}  "{name}"')

    if args.apply and report:
        print(f"\n  stripped {len(report)} repeats.")
    elif report:
        print("\n  Re-run with --apply to write them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
