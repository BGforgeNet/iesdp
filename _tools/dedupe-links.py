#!/usr/bin/env python3
"""Unlink repeated links, keeping the first occurrence in each block.

Descriptions often link the same target several times in a row - "when using Rectangular AoE ...
projectiles using Rectangular AoE without ..." - which makes a passage harder to read without
telling the reader anything new. One link per block is enough.

A block is a list item together with its nested sub-list, or a paragraph outside any list. Two
rules decide a repeat inside one block:

  - A repeat in the *same* item as the first link is always redundant, however long the item.
  - A repeat in a sibling or child item is unlinked only when that item is a one-liner
    (--max-item-chars, default 200). A large paragraph keeps its own link, because a reader
    arriving there shouldn't have to scan back up the list for it.

Repeats in a later block are always kept, so a long description still offers the link where a
reader picks it up.

Two links are the same only when both the target and the visible text match: the same anchor
labelled differently ("Delayed Trigger" and "Triggered by Condition" both point at AreaFlags_BIT2)
is two distinct pieces of information, not a duplicate.

Handles both content shapes: HTML pages, where blocks are <li> and <p> elements, and the markdown
`desc:` block scalars in _data, where they are bullets and runs of prose. Anchor definitions
(<a name=...> with no href) are never touched.

Reports by default; --apply writes the files.
"""

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

SCAN_SUFFIXES = {".htm", ".html", ".md", ".yml", ".yaml"}
SKIP_DIRS = {".git", "_site", ".jekyll-cache", ".sass-cache", "_tools", "vendor", "node_modules"}
# CONTRIBUTING.md's examples deliberately repeat one link to contrast right and wrong forms.
SKIP_FILES = {"CONTRIBUTING.md"}

LINK = re.compile(r'<a\s[^>]*\bhref="[^"]*"[^>]*>.*?</a>', re.S)
HREF = re.compile(r'\bhref="([^"]*)"')
TAGS = re.compile(r"<[^>]+>")
BULLET = re.compile(r"^(\s*)[-*]\s")
VOID = {"br", "img", "hr", "input", "meta", "link"}
ITEM_TAGS = ("li", "p")


def visible_text(markup):
    """The text as a reader sees it - markup and line wrapping collapsed away."""
    return " ".join(TAGS.sub("", markup).split())


def line_offsets(text):
    starts, pos = [], 0
    for line in text.splitlines(keepends=True):
        starts.append(pos)
        pos += len(line)
    starts.append(pos)
    return starts


class ItemFinder(HTMLParser):
    """Spans of <li>/<p> elements: the outermost ones are blocks, all of them are items."""

    def __init__(self, starts, length):
        super().__init__(convert_charrefs=True)
        self.starts, self.length = starts, length
        self.stack, self.blocks, self.items = [], [], []

    def char_offset(self):
        line, col = self.getpos()
        return self.starts[line - 1] + col

    def handle_starttag(self, tag, attrs):
        if tag in ITEM_TAGS:
            nested = any(t in ITEM_TAGS for t, _ in self.stack)
            self.stack.append((tag, (self.char_offset(), nested)))
        elif tag not in VOID:
            self.stack.append((tag, None))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                self._record(self.stack[i][1], self.char_offset())
                del self.stack[i:]
                return

    def close(self):
        super().close()
        # An unclosed <li> - legal HTML, and present in these pages - runs to the end of the file.
        for _, mark in self.stack:
            self._record(mark, self.length)

    def _record(self, mark, end):
        if mark is None:
            return
        start, nested = mark
        self.items.append((start, end))
        if not nested:
            self.blocks.append((start, end))


def html_spans(text):
    finder = ItemFinder(line_offsets(text), len(text))
    finder.feed(text)
    finder.close()
    return finder.blocks, finder.items


def yaml_spans(text):
    """Spans inside `desc: |-` scalars: top-level bullets and prose runs are blocks, every
    bullet at any depth is an item.

    The YAML sequence dash sits at the mapping's own indent and is not a markdown bullet, so
    only lines indented deeper than the `desc:` key are considered.
    """
    starts = line_offsets(text)
    lines = text.splitlines(keepends=True)
    blocks, items, i = [], [], 0

    while i < len(lines):
        m = re.match(r"^(\s*)-?\s*desc:\s*[|>][-+]?\s*$", lines[i])
        if not m:
            i += 1
            continue
        key_indent = len(m.group(1))
        i += 1
        block_start, base, open_items = None, None, []
        while i < len(lines):
            line = lines[i]
            indent = len(line) - len(line.lstrip())
            if line.strip() and indent <= key_indent:
                break
            bullet = BULLET.match(line)
            if bullet:
                ind = len(bullet.group(1))
                while open_items and open_items[-1][1] >= ind:
                    items.append((starts[open_items.pop()[0]], starts[i]))
                open_items.append((i, ind))
                if base is None or ind <= base:
                    if block_start is not None:
                        blocks.append((starts[block_start], starts[i]))
                    block_start, base = i, ind
            elif not line.strip() and base is None and block_start is not None:
                blocks.append((starts[block_start], starts[i]))
                block_start = None
            elif line.strip() and block_start is None:
                block_start, base = i, None
            i += 1
        end = starts[i]
        for start, _ in open_items:
            items.append((starts[start], end))
        if block_start is not None:
            blocks.append((starts[block_start], end))
    return blocks, items


def innermost(spans, offset):
    """The tightest span containing offset, or None."""
    found = None
    for start, end in spans:
        if start <= offset < end and (found is None or start > found[0] or end < found[1]):
            found = (start, end)
    return found


def own_length(text, span, spans):
    """Visible length of an item's own text, excluding any nested items.

    A bullet that introduces a sub-list reads as a one-liner even though its element encloses
    every child, so the children must not count towards its size.
    """
    start, end = span
    nested = [s for s, e in spans if start < s < end]
    return len(visible_text(text[start:min(nested) if nested else end]))


def process(path, text, max_item_chars):
    """Return (new_text, [(line, href, label, reason)]) for every link unlinked."""
    blocks, items = (html_spans if path.suffix.lower() in (".htm", ".html") else yaml_spans)(text)
    seen, removed, out, last = {}, [], [], 0

    for m in LINK.finditer(text):
        block = innermost(blocks, m.start())
        if block is None:
            continue
        href_match = HREF.search(m.group(0))
        if not href_match:
            continue
        key = (block, href_match.group(1), visible_text(m.group(0)))
        item = innermost(items, m.start()) or block

        if key not in seen:
            seen[key] = item
            continue
        if seen[key] == item:
            reason = "same item"
        elif own_length(text, item, items) <= max_item_chars:
            reason = "one-liner"
        else:
            # Large sibling paragraph: it keeps this link, and becomes the reference for any
            # further repeat inside it.
            seen[key] = item
            continue

        inner = m.group(0)[m.group(0).index(">") + 1:-len("</a>")]
        out.append(text[last:m.start()])
        out.append(inner)
        last = m.end()
        removed.append((text.count("\n", 0, m.start()) + 1, key[1], key[2], reason))

    out.append(text[last:])
    return "".join(out), removed


def scan_files():
    for path in sorted(REPO.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        rel = path.relative_to(REPO)
        if SKIP_DIRS.intersection(rel.parts) or rel.name in SKIP_FILES:
            continue
        yield path, rel


def main():
    parser = argparse.ArgumentParser(
        description="Unlink repeated links, keeping the first occurrence in each block.")
    parser.add_argument("--apply", action="store_true", help="write the changes (default: report only)")
    parser.add_argument("--max-item-chars", type=int, default=200,
                        help="an item this short counts as a one-liner (default: 200)")
    parser.add_argument("--limit", type=int, default=25, help="report lines to print (default: 25)")
    args = parser.parse_args()

    report, files, reasons = [], 0, {}
    for path, rel in scan_files():
        text = path.read_text(encoding="utf-8")
        if "<a " not in text:
            continue
        new, removed = process(path, text, args.max_item_chars)
        if not removed:
            continue
        files += 1
        for line, href, label, reason in removed:
            reasons[reason] = reasons.get(reason, 0) + 1
            report.append(f"  {rel}:{line}  [{reason}] {label!r} -> {href}")
        if args.apply:
            path.write_text(new, encoding="utf-8")

    tally = ", ".join(f"{n} {r}" for r, n in sorted(reasons.items()))
    print(f"  redundant links: {len(report)} in {files} files ({tally})")
    for line in report[:args.limit]:
        print(line)
    if len(report) > args.limit:
        print(f"  ... ({len(report) - args.limit} more)")
    if args.apply:
        print(f"\n  unlinked {len(report)} repeats.")
    elif report:
        print("\n  Re-run with --apply to write them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
