"""Shared MediaWiki client and tracked configuration paths."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = (
    "bahamut-wiki/1.0 (config-deploy, https://github.com/BahamutXIV/bahamut-wiki)"
)
CONFIG_NAMESPACES = ("MediaWiki", "Module", "Template")
CONFIG_SUFFIXES = (".mediawiki", ".css", ".js")


class WikiEditError(RuntimeError):
    """A refused MediaWiki edit, retaining the API error code."""

    def __init__(self, error: dict[str, Any]) -> None:
        self.api_code = str(error.get("code", ""))
        super().__init__(f"Edit failed: {error}")


def _api_result(response: requests.Response) -> dict[str, Any]:
    result = response.json()
    if "error" in result:
        raise WikiEditError(result["error"])
    return result


def load_env() -> tuple[str, str, str]:
    load_dotenv(REPO_ROOT / ".env")
    user = os.environ.get("WIKI_USER")
    password = os.environ.get("WIKI_BOT_PASS")
    api_url = os.environ.get("WIKI_API_URL")
    if not (user and password and api_url):
        raise SystemExit(
            "Missing WIKI_USER, WIKI_BOT_PASS, or WIKI_API_URL. "
            "Copy .env.example to .env and fill them in."
        )
    try:
        parsed_url = urlsplit(api_url)
    except ValueError:
        raise SystemExit("WIKI_API_URL must be a valid HTTPS URL.") from None
    if parsed_url.scheme.lower() != "https" or not parsed_url.netloc:
        raise SystemExit("WIKI_API_URL must be a valid HTTPS URL.")
    return user, password, api_url


class WikiClient:
    def __init__(self, user: str, password: str, api_url: str) -> None:
        self.api_url = api_url
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._login(user, password)

    def _request(self, method: str, **kwargs: Any) -> requests.Response:
        response = self.session.request(
            method,
            self.api_url,
            timeout=30,
            allow_redirects=False,
            **kwargs,
        )
        if response.status_code in range(300, 400):
            raise SystemExit("WIKI_API_URL redirected. Use the direct HTTPS API URL.")
        response.raise_for_status()
        return response

    def _login(self, user: str, password: str) -> None:
        token = self._get_token("login")
        response = self._request(
            "POST",
            data={
                "action": "login",
                "lgname": user,
                "lgpassword": password,
                "lgtoken": token,
                "format": "json",
            },
        )
        result = response.json().get("login", {})
        if result.get("result") != "Success":
            raise SystemExit(f"Login failed: {result}")

    def _get_token(self, kind: str) -> str:
        response = self._request(
            "GET",
            params={
                "action": "query",
                "meta": "tokens",
                "type": kind,
                "format": "json",
            },
        )
        result = _api_result(response)
        return result["query"]["tokens"][f"{kind}token"]

    def get_page_with_revid(self, title: str) -> tuple[str, int] | None:
        """Return the current page content and revision, or None if missing."""
        response = self._request(
            "GET",
            params={
                "action": "query",
                "prop": "revisions",
                "rvprop": "content|ids",
                "rvslots": "main",
                "titles": title,
                "format": "json",
                "formatversion": "2",
            },
        )
        result = _api_result(response)
        pages = result.get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing"):
            return None
        revision = pages[0]["revisions"][0]
        return revision["slots"]["main"]["content"], revision["revid"]

    def edit_page(
        self,
        title: str,
        text: str,
        summary: str,
        *,
        baserevid: int | None = None,
        createonly: bool = False,
    ) -> dict[str, Any]:
        """Write one page using revision and page existence checks."""
        data: dict[str, Any] = {
            "action": "edit",
            "title": title,
            "text": text,
            "summary": summary,
            "token": self._get_token("csrf"),
            "format": "json",
            "bot": 1,
        }
        if baserevid is not None:
            data["baserevid"] = baserevid
            data["nocreate"] = 1
        if createonly:
            data["createonly"] = 1
        response = self._request("POST", data=data)
        result = _api_result(response)
        edit = result.get("edit", {})
        if edit.get("result") != "Success":
            raise WikiEditError({"code": "unexpected-response", "response": result})
        return edit


def config_dir() -> Path:
    return REPO_ROOT / "wiki-config"


def page_for_config_filename(filename: str) -> str:
    """Derive a protected wiki title from one configuration filename."""
    name = Path(filename).name
    suffix = Path(name).suffix.lower()
    if suffix not in CONFIG_SUFFIXES:
        raise ValueError(f"Unsupported configuration extension: {name}")
    stem = Path(name).stem if suffix == ".mediawiki" else name
    for namespace in CONFIG_NAMESPACES:
        prefix = f"{namespace}_"
        if stem.startswith(prefix) and len(stem) > len(prefix):
            return f"{namespace}:" + stem[len(prefix) :].replace("_", " ")
    expected = ", ".join(f"{namespace}_" for namespace in CONFIG_NAMESPACES)
    raise ValueError(f"Configuration filename must begin with one of: {expected}")


def page_text_matches(left: str, right: str) -> bool:
    """Compare source after removing trailing newlines, as MediaWiki does."""
    return left.rstrip("\n") == right.rstrip("\n")


def resolve_config_path(filename: str) -> Path:
    """Resolve one direct child of wiki-config and reject path traversal."""
    relative = Path(filename)
    if relative.is_absolute() or relative.parent != Path("."):
        raise ValueError("Configuration files must be direct children of wiki-config/")
    page_for_config_filename(relative.name)
    root = config_dir().resolve()
    path = (root / relative.name).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError("Configuration path resolves outside wiki-config/") from error
    if path.parent != root:
        raise ValueError("Configuration files must be direct children of wiki-config/")
    if not path.is_file():
        raise ValueError(f"Configuration file not found: {path}")
    return path


def make_client() -> WikiClient:
    return WikiClient(*load_env())
