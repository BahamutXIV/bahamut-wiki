"""Compare one tracked wiki configuration file with its live page."""

from __future__ import annotations

import argparse
import difflib

import wiki


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", help="Filename under wiki-config/")
    args = parser.parse_args()

    try:
        source = wiki.resolve_config_path(args.file)
        title = wiki.page_for_config_filename(source.name)
    except ValueError as error:
        print(error)
        return 1

    current = wiki.make_client().get_page_with_revid(title)
    if current is None:
        print(f"Page not found on wiki: `{title}`")
        return 1

    live_text, _ = current
    repo_text = source.read_text(encoding="utf-8")
    if wiki.page_text_matches(live_text, repo_text):
        print(f"No diff: `{title}` matches repo source.")
        return 0
    diff = list(
        difflib.unified_diff(
            live_text.splitlines(keepends=True),
            repo_text.splitlines(keepends=True),
            fromfile=f"wiki:{title}",
            tofile=f"repo:{source.name}",
        )
    )
    print("".join(diff), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
