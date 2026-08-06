#!/usr/bin/env python3
"""Give every row of a hand-written offset table an anchor, so any field can be linked to.

The data-driven tables get theirs from _includes/offset_list.md. The pages that spell their
tables out in HTML need the anchor written into the markup, which is what this does: each row
gets id="<section>_0x<OFFSET>", the same shape the hand-written anchors already use
(CREV1_0_Header_0x10), with the section taken from the fileHeader above the table.

Twelve pages label their fields with a bare offset instead (pro_v1's <a name="0x216">) and have
no name on the section heading. SECTION_NAMES supplies one for those, and the bare anchors are
left where they are - links to them keep working, and the row id is an addition, not a
replacement.

A row is skipped when its id would collide with another row in the same section, which happens
for two different reasons and neither is safe to guess at. Either the page states one offset
twice - an error in the offsets - or the section heading covers several tables that each start
at zero, in which case the tables need headings of their own before their rows can be told
apart. The report lists the skips; both causes want a person to look.

Reports by default; --apply writes the files.
"""

import argparse
import collections
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAGES = "file_formats/**/*.htm"

# Sections whose heading carries no anchor. Named after the format and the section, following
# the convention the anchored pages already use (tlkv1_Header, itmv1_Extended_Header).
SECTION_NAMES = {
    ("bmp.htm", "General Description"): "bmp_Header",
    ("bmp_v5.htm", "General Description"): "bmpv5_Header",
    ("plt_v1.htm", "Header"): "pltv1_Header",
    ("plt_v1.htm", "Body"): "pltv1_Body",
    ("pro_v1.htm", "Detailed Description"): "prov1_Header",
    ("tis_v1.htm", "Header"): "tisv1_Header",
    ("toh.htm", "Header"): "toh_Header",
    ("toh.htm", "Strref Entries"): "toh_Entry",
    ("toh_v2.htm", "Header"): "tohv2_Header",
    ("toh_v2.htm", "Strref Entries"): "tohv2_Entry",
    ("tot.htm", "Detailed Description"): "tot_Header",
    ("var.htm", "Dead entry"): "var_Dead_entry",
    ("var.htm", "Variable definition sections"): "var_Variable",
    ("vvc_v1.htm", "Detailed Description"): "vvcv1_Header",
    ("wavc_v1.htm", "Detailed Description"): "wavcv1_Header",
    ("wfx_v1.htm", "Detailed Description"): "wfxv1_Header",
}

HEADER_DIV = re.compile(r'<div class="fileHeader"[^>]*>(.*?)</div>', re.S | re.I)
ANCHOR = re.compile(r'<a\s+(?:name|id)="([^"]+)"', re.I)
TAGS = re.compile(r"<[^>]+>")
ROW = re.compile(r'<tr\b([^>]*)>(\s*<td[^>]*>\s*(0x[0-9A-Fa-f]+)\s*</td>)', re.I)


def sections(text):
    """[(start, end, anchor_or_None, label, span_of_inner_html)] for each fileHeader div."""
    out = []
    for m in HEADER_DIV.finditer(text):
        a = ANCHOR.search(m.group(1))
        label = " ".join(TAGS.sub(" ", m.group(1)).split())
        out.append([m.start(), None, a.group(1) if a else None, label, m.span(1)])
    for i, s in enumerate(out):
        s[1] = out[i + 1][0] if i + 1 < len(out) else len(text)
    return out


def process(path, text):
    """Return (new_text, added_rows, added_sections, collisions, unnamed)."""
    secs = sections(text)
    added_sections, unnamed = [], []

    # Name any section that lacks an anchor but has rows under it, so its rows get a prefix.
    for s in secs:
        if s[2] is not None:
            continue
        if not ROW.search(text[s[0]:s[1]]):
            continue
        name = SECTION_NAMES.get((path.name, s[3]))
        if name is None:
            unnamed.append(s[3])
            continue
        s[2] = name
        added_sections.append((name, s[3]))

    # Row ids, innermost section first. Built as edits so offsets stay valid.
    edits, added_rows, collisions, stripped = [], [], [], []
    # Seed with the ids already in the file, so a second run cannot hand a row an anchor that an
    # earlier run already gave to another row.
    used = collections.Counter(re.findall(r'<tr id="([^"]+)"', text))
    for m in ROW.finditer(text):
        prefix = None
        for s in secs:
            if s[0] < m.start() < s[1]:
                prefix = s[2]
        if not prefix or re.search(r"\bid=", m.group(1), re.I):
            continue
        anchor = f"{prefix}_0x{int(m.group(3), 16):X}"
        used[anchor] += 1
        if used[anchor] > 1:
            collisions.append((anchor, m.group(3)))
            continue
        edits.append((m.start(1) if m.group(1) else m.start() + 3, anchor))
        added_rows.append(anchor)
        # The row may already carry this exact anchor by hand. Two of the same name is one too
        # many, and the row id now covers it, so the hand-written one goes (its text stays).
        row_end = text.find("</tr>", m.end())
        dup = re.compile(r'<a name="' + re.escape(anchor) + r'"\s*>(.*?)</a>', re.S)
        for d in dup.finditer(text, m.end(), row_end if row_end > 0 else len(text)):
            stripped.append((d.span(), d.group(1)))

    # Apply section anchors and row ids in one back-to-front pass, so earlier spans stay valid.
    out = text
    pieces = []
    for name, label in added_sections:
        for s in secs:
            if s[2] == name:
                pieces.append((s[4], f'<a name="{name}">{text[s[4][0]:s[4][1]].strip()}</a>'))
                break
    for pos, anchor in edits:
        pieces.append(((pos, pos), f' id="{anchor}"'))
    for span, inner in stripped:
        pieces.append((span, inner))

    for (start, end), replacement in sorted(pieces, key=lambda p: -p[0][0]):
        out = out[:start] + replacement + out[end:]

    return out, added_rows, added_sections, collisions, unnamed, len(stripped)


def main():
    parser = argparse.ArgumentParser(
        description="Give every hand-written offset-table row an anchor.")
    parser.add_argument("--apply", action="store_true", help="write the changes (default: report only)")
    parser.add_argument("--limit", type=int, default=12, help="report lines to print (default: 12)")
    args = parser.parse_args()

    rows = secs = strips = 0
    files, all_collisions, all_unnamed = [], [], []
    for path in sorted(REPO.glob(PAGES)):
        text = path.read_text(encoding="utf-8")
        new, added_rows, added_sections, collisions, unnamed, nstrip = process(path, text)
        strips += nstrip
        all_collisions += [(path.name,) + c for c in collisions]
        all_unnamed += [(path.name, u) for u in unnamed]
        if not added_rows and not added_sections:
            continue
        rows += len(added_rows)
        secs += len(added_sections)
        files.append((str(path.relative_to(REPO)), len(added_rows), len(added_sections)))
        if args.apply:
            path.write_text(new, encoding="utf-8")

    print(f"  rows given an anchor: {rows}   section anchors added: {secs}   redundant anchors dropped: {strips}   files: {len(files)}")
    for f, n, s in sorted(files, key=lambda x: -x[1])[:args.limit]:
        print(f"    {n:4} rows{f'  +{s} section' if s else '':<13} {f}")
    if len(files) > args.limit:
        print(f"    ... ({len(files) - args.limit} more files)")
    if all_collisions:
        print(f"\n  {len(all_collisions)} rows skipped - the id would repeat one already used in")
        print("  the same section, either a wrong offset or several tables under one heading:")
        for name, anchor, off in all_collisions[:10]:
            print(f"    {name}  {anchor}  (cell reads {off})")
    if all_unnamed:
        print(f"\n  {len(all_unnamed)} sections have rows but no anchor and no entry in SECTION_NAMES:")
        for n, u in all_unnamed[:10]:
            print(f"    {n}  {u!r}")
    if not args.apply and rows:
        print("\n  Re-run with --apply to write them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
