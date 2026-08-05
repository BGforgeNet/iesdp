#!/usr/bin/env python3
"""Remove <code> markup from links whose text is not code.

The site had accumulated two habits for linking: `<code><a href=...>text</a></code>` and
`<a href=...><code>text</code></a>`. Both render the link in a monospace face, which is only
meaningful when the link text is a machine token (a script call, an IDS symbol, a resource
filename). For a human-readable field label such as "Explosion Frequency" it is noise.

This script rewrites the simple one-link-per-<code> shapes:

    text is code   ->  <a href=...><code>text</code></a>   (nesting normalised, link outermost)
    text is prose  ->  <a href=...>text</a>                (<code> dropped)

A <code> element holding anything besides a single link - a formula such as
`<code><a>new duration</a>(ticks) = <a>Gametime</a>(ticks)</code>` - is code as a whole and is
left alone.

Classification uses the heuristics in CODE_PATTERNS for unambiguous tokens; every other single
word is decided by _tools/code-link-words.txt, which is authoritative and also overrides the
heuristics. Texts missing from that file are reported and left untouched rather than guessed at.

Reports by default; --apply writes the files.
"""

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORDS_FILE = Path(__file__).resolve().parent / "code-link-words.txt"

SCAN_SUFFIXES = {".htm", ".html", ".md", ".yml", ".yaml"}
SKIP_DIRS = {".git", "_site", ".jekyll-cache", ".sass-cache", "_tools", "vendor", "node_modules"}
# CONTRIBUTING.md quotes both nestings as examples of the linking convention; rewriting the
# examples would contradict the prose around them.
SKIP_FILES = {"CONTRIBUTING.md"}

# <code> wrapping exactly one link, and nothing else. [^<>]* is what keeps mixed content
# (a second link, a formula around the link) from matching.
CODE_OUTSIDE = re.compile(r"<code>(<a\b[^>]*>)([^<>]*)</a></code>")
LINK_OUTSIDE = re.compile(r"(<a\b[^>]*>)<code>([^<>]*)</code></a>")

# Resource extensions the engine uses; a bare "name.ext" link text is a file, hence code.
RESOURCE_EXT = (
    "2da|ids|itm|spl|cre|are|bcs|bs|eff|pro|vvc|bam|tis|wed|mos|pvrz|sto|wmp|gam|chu|dlg|"
    "mve|acm|wav|bif|key|tlk|src|ini|baf|d|tp2|tra"
)

CODE_PATTERNS = (
    re.compile(r"\([^)]*\)$"),                       # script call:  MakeUnselectable(), Range()
    re.compile(rf"^[\w.-]+\.(?:{RESOURCE_EXT})$", re.I),  # resource:  RNDSCROL.2DA, difflev.ids
    re.compile(r"^0[xX][0-9A-Fa-f]+$"),              # offset:      0x4047
    re.compile(r"^[A-Z][A-Z0-9_-]+$"),               # IDS symbol:  TRANSLUCENT, GIANT_YAGA-SHURA
    re.compile(r"^BIT\d+$"),                         # flag bit:    BIT15
    re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$"),  # field key:   resist_dispel
    re.compile(r" (?:=|==|>=|<=|!=) "),              # expression:  resist_dispel = BIT2
)

CODE, PROSE, REVIEW = "code", "prose", "review"


def load_words():
    """Parse code-link-words.txt: `<verdict><TAB><text>[<TAB># comment]`, blank lines ignored.

    Fields are split on tabs rather than at the first '#', because a link text may itself contain
    one ("# Repetitions" is a real field label here).
    """
    words = {}
    if not WORDS_FILE.exists():
        return words
    for lineno, raw in enumerate(WORDS_FILE.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        fields = raw.split("\t")
        verdict, text = fields[0], fields[1] if len(fields) > 1 else ""
        if verdict not in (CODE, PROSE) or not text:
            sys.exit(f"{WORDS_FILE.name}:{lineno}: expected 'code<TAB>text' or 'prose<TAB>text'")
        words[text] = verdict
    return words


def classify(text, words):
    """Wordlist wins over the heuristics; an undecidable text is reported, never guessed."""
    if text in words:
        return words[text]
    if any(p.search(text) for p in CODE_PATTERNS):
        return CODE
    if " " in text:
        return PROSE
    return REVIEW


def rewrite_line(line, words, stats, review):
    """Return the line with both nestings normalised, recording what each match was judged."""

    def replace(match):
        anchor, text = match.group(1), match.group(2)
        verdict = classify(text, words)
        stats[verdict] = stats.get(verdict, 0) + 1
        if verdict == REVIEW:
            review.setdefault(text, set()).add(anchor)
            return match.group(0)
        if verdict == CODE:
            return f"{anchor}<code>{text}</code></a>"
        return f"{anchor}{text}</a>"

    # LINK_OUTSIDE first: CODE_OUTSIDE emits the link-outermost form, which the other pattern
    # would otherwise match a second time and count twice.
    return CODE_OUTSIDE.sub(replace, LINK_OUTSIDE.sub(replace, line))


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
        description="Remove <code> markup from links whose text is not code.")
    parser.add_argument("--apply", action="store_true", help="write the changes (default: report only)")
    parser.add_argument("--list-review", action="store_true",
                        help="emit undecidable texts as code-link-words.txt stubs and exit")
    parser.add_argument("--limit", type=int, default=15, help="preview lines to print (default: 15)")
    args = parser.parse_args()

    words = load_words()
    stats, review, changes = {}, {}, []

    for path, rel in scan_files():
        original = path.read_text(encoding="utf-8")
        lines = original.splitlines(keepends=True)
        out = []
        for lineno, line in enumerate(lines, 1):
            new = rewrite_line(line, words, stats, review)
            if new != line:
                changes.append((rel, lineno, line.strip(), new.strip()))
            out.append(new)
        updated = "".join(out)
        if args.apply and updated != original:
            path.write_text(updated, encoding="utf-8")

    if args.list_review:
        for text in sorted(review):
            hrefs = " ".join(sorted(review[text]))
            print(f"code\t{text}\t# {hrefs[:160]}")
        return 0

    print(f"  strip: {stats.get(PROSE, 0)}   keep: {stats.get(CODE, 0)}   review: {stats.get(REVIEW, 0)}")
    for rel, lineno, before, after in changes[:args.limit]:
        print(f"\n  {rel}:{lineno}\n  - {before}\n  + {after}")
    if len(changes) > args.limit:
        print(f"\n  ... ({len(changes) - args.limit} more lines)")

    if review:
        print(f"\n  {len(review)} link texts are not in {WORDS_FILE.name} and were left untouched:")
        print("   ", ", ".join(sorted(review)[:20]) + (" ..." if len(review) > 20 else ""))
        print(f"    Run --list-review to emit stubs, decide each, append to {WORDS_FILE.name}.")

    if not args.apply and changes:
        print(f"\n  {len(changes)} lines would change. Re-run with --apply to write them.")
    elif args.apply:
        print(f"\n  wrote {len({c[0] for c in changes})} files ({len(changes)} lines).")
    return 1 if review else 0


if __name__ == "__main__":
    sys.exit(main())
