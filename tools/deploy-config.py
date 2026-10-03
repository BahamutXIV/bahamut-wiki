"""Deploy protected wiki configuration from the tracked wiki-config directory."""

from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path, PurePosixPath

import requests

import wiki


TRANSIENT_HTTP_STATUSES = (429, 500, 502, 503, 504)
TRANSIENT_API_CODES = ("ratelimited", "readonly", "readonly_lag")
RETRY_ATTEMPTS = 3


def tracked_config_names() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "wiki-config"],
        cwd=wiki.REPO_ROOT,
        capture_output=True,
        check=True,
        timeout=15,
    )
    names: list[str] = []
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        path = PurePosixPath(raw_path.decode("utf-8"))
        if (
            len(path.parts) == 2
            and path.parts[0] == "wiki-config"
            and Path(path.name).suffix.lower() in wiki.CONFIG_SUFFIXES
        ):
            names.append(path.name)
    return names


def select_files(filenames: list[str], every: bool) -> list[Path]:
    if every and filenames:
        raise ValueError("Use --all or explicit filenames, not both")
    if not every and not filenames:
        raise ValueError("Give --all or at least one configuration filename")
    tracked_names = set(tracked_config_names())
    selected_names = tracked_names if every else filenames
    files = sorted(
        {wiki.resolve_config_path(name) for name in selected_names},
        key=lambda path: path.name.casefold(),
    )
    untracked = [path.name for path in files if path.name not in tracked_names]
    if untracked:
        raise ValueError(f"Configuration file is not tracked by Git: {untracked[0]}")
    if not files:
        raise ValueError("No configuration files found")
    titles: dict[str, Path] = {}
    for path in files:
        title = wiki.page_for_config_filename(path.name)
        namespace, _, page = title.partition(":")
        page = " ".join(page.split())
        normalized = f"{namespace.casefold()}:{page[:1].upper()}{page[1:]}"
        if normalized in titles:
            raise ValueError(
                f"Duplicate wiki title: {titles[normalized].name} and {path.name}"
            )
        titles[normalized] = path
        path.read_text(encoding="utf-8")
    return files


def _deploy_with_retry(
    client: wiki.WikiClient,
    path: Path,
    summary: str,
) -> str:
    title = wiki.page_for_config_filename(path.name)
    text = path.read_text(encoding="utf-8")
    base_known = False
    base_revid: int | None = None
    attempt = 1
    while True:
        try:
            current = client.get_page_with_revid(title)
            if current is not None and wiki.page_text_matches(current[0], text):
                print(f"SKIP  `{title}` already matches")
                return "unchanged"

            current_revid = current[1] if current is not None else None
            if not base_known:
                base_known = True
                base_revid = current_revid
            elif current_revid != base_revid:
                raise wiki.WikiEditError(
                    {
                        "code": "intervening-edit",
                        "title": title,
                        "expected_revid": base_revid,
                        "current_revid": current_revid,
                    }
                )

            result = client.edit_page(
                title,
                text,
                summary,
                baserevid=current_revid,
                createonly=current is None,
            )
            print(f"PUSH  `{title}` -> rev {result.get('newrevid', '?')}")
            return "deployed"
        except requests.HTTPError as error:
            status = error.response.status_code if error.response is not None else None
            if status not in TRANSIENT_HTTP_STATUSES:
                raise
            failure = f"HTTP {status}"
        except wiki.WikiEditError as error:
            if error.api_code not in TRANSIENT_API_CODES:
                raise
            failure = f"MediaWiki {error.api_code}"

        if attempt == RETRY_ATTEMPTS:
            raise RuntimeError(
                f"Deployment failed for {path.name} after {RETRY_ATTEMPTS} attempts: {failure}"
            )
        wait = 1.5 * attempt
        print(f"RETRY {path.name}: {failure}, waiting {wait:.1f}s")
        time.sleep(wait)
        attempt += 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="Filenames under wiki-config/")
    parser.add_argument(
        "--all", action="store_true", help="Select every tracked config source"
    )
    parser.add_argument(
        "--execute", action="store_true", help="Write the selected pages"
    )
    parser.add_argument(
        "--summary",
        default="config: deploy from GitHub",
        help="Edit summary recorded on each wiki revision",
    )
    args = parser.parse_args()

    try:
        files = select_files(args.files, args.all)
    except (OSError, ValueError) as error:
        print(error)
        return 1

    if not args.execute:
        print(f"DRY RUN - no network calls. {len(files)} file(s) selected:")
        for path in files:
            print(f"  {path.name} -> {wiki.page_for_config_filename(path.name)}")
        print("Pass --execute to deploy.")
        return 0

    client = wiki.make_client()
    deployed = 0
    unchanged = 0
    for path in files:
        try:
            result = _deploy_with_retry(client, path, args.summary)
            if result == "deployed":
                deployed += 1
            else:
                unchanged += 1
        except (
            OSError,
            UnicodeError,
            requests.RequestException,
            RuntimeError,
        ) as error:
            print(f"FAIL  {path.name}: {error}")
            print(
                f"done: deployed={deployed} unchanged={unchanged} "
                f"failed=1 selected={len(files)}"
            )
            return 1

    print(
        f"done: deployed={deployed} unchanged={unchanged} "
        f"failed=0 selected={len(files)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
