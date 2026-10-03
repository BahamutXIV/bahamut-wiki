"""Regression tests for protected wiki configuration tooling."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import wiki  # noqa: E402


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS_DIR / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


deploy_config = load_script("deploy-config")
diff_wiki = load_script("diff-wiki")


class ConfigPathTests(unittest.TestCase):
    def test_supported_filenames_map_to_protected_titles(self) -> None:
        cases = {
            "MediaWiki_Common.css": "MediaWiki:Common.css",
            "MediaWiki_Common.js": "MediaWiki:Common.js",
            "MediaWiki_Sidebar.mediawiki": "MediaWiki:Sidebar",
            "Module_Recipe.mediawiki": "Module:Recipe",
            "Template_Grand_Companies.mediawiki": "Template:Grand Companies",
        }
        for filename, title in cases.items():
            self.assertEqual(title, wiki.page_for_config_filename(filename))

    def test_community_namespace_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "must begin"):
            wiki.page_for_config_filename("Category_Quests.mediawiki")

    def test_unsupported_extension_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            wiki.page_for_config_filename("Template_Item.txt")

    def test_path_outside_config_root_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "direct children"):
            wiki.resolve_config_path("../Template_Item.mediawiki")

    def test_absolute_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "direct children"):
            wiki.resolve_config_path(str(Path.cwd() / "Template_Item.mediawiki"))

    def test_symlink_outside_config_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "wiki-config"
            root.mkdir()
            outside = Path(temp_dir) / "Template_Outside.mediawiki"
            outside.write_text("body\n", encoding="utf-8")
            link = root / "Template_Link.mediawiki"
            try:
                link.symlink_to(outside)
            except OSError as error:
                if getattr(error, "winerror", None) == 1314:
                    self.skipTest("Creating symlinks requires Windows developer mode")
                raise
            with patch.object(wiki, "config_dir", return_value=root):
                with self.assertRaisesRegex(ValueError, "resolves outside"):
                    wiki.resolve_config_path(link.name)

    def test_missing_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(wiki, "config_dir", return_value=Path(temp_dir)):
                with self.assertRaisesRegex(ValueError, "not found"):
                    wiki.resolve_config_path("Template_Item.mediawiki")


class EnvironmentTests(unittest.TestCase):
    def _load(self, api_url: str) -> tuple[str, str, str]:
        values = {
            "WIKI_USER": "user",
            "WIKI_BOT_PASS": "password",
            "WIKI_API_URL": api_url,
        }
        with (
            patch.object(wiki, "load_dotenv"),
            patch.dict(wiki.os.environ, values, clear=True),
        ):
            return wiki.load_env()

    def test_https_api_url_is_accepted(self) -> None:
        self.assertEqual(
            ("user", "password", "https://example.test/api.php"),
            self._load("https://example.test/api.php"),
        )

    def test_http_api_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(SystemExit, "valid HTTPS URL"):
            self._load("http://example.test/api.php")

    def test_malformed_api_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(SystemExit, "valid HTTPS URL"):
            self._load("https://[bad")


class WikiClientTests(unittest.TestCase):
    def _client(self) -> wiki.WikiClient:
        client = wiki.WikiClient.__new__(wiki.WikiClient)
        client.api_url = "https://example.test/api.php"
        client.session = Mock()
        return client

    def test_api_requests_do_not_follow_redirects(self) -> None:
        client = self._client()
        response = Mock(status_code=307)
        client.session.request.return_value = response
        with self.assertRaisesRegex(SystemExit, "direct HTTPS API URL"):
            client._request("POST", data={"lgpassword": "password"})
        self.assertFalse(client.session.request.call_args.kwargs["allow_redirects"])

    def test_revision_read_returns_content_and_id(self) -> None:
        client = self._client()
        response = Mock()
        response.json.return_value = {
            "query": {
                "pages": [
                    {
                        "revisions": [
                            {"revid": 77, "slots": {"main": {"content": "body"}}}
                        ]
                    }
                ]
            }
        }
        client.session.request.return_value = response
        self.assertEqual(("body", 77), client.get_page_with_revid("Template:Item"))

    def test_revision_read_returns_none_for_missing_page(self) -> None:
        client = self._client()
        response = Mock()
        response.json.return_value = {"query": {"pages": [{"missing": True}]}}
        client.session.request.return_value = response
        self.assertIsNone(client.get_page_with_revid("Template:Missing"))

    def test_token_query_error_retains_api_code(self) -> None:
        client = self._client()
        response = Mock()
        response.json.return_value = {"error": {"code": "readonly"}}
        client.session.request.return_value = response
        with self.assertRaises(wiki.WikiEditError) as raised:
            client._get_token("csrf")
        self.assertEqual("readonly", raised.exception.api_code)

    def test_revision_query_error_retains_api_code(self) -> None:
        client = self._client()
        response = Mock()
        response.json.return_value = {"error": {"code": "readonly"}}
        client.session.request.return_value = response
        with self.assertRaises(wiki.WikiEditError) as raised:
            client.get_page_with_revid("Template:Item")
        self.assertEqual("readonly", raised.exception.api_code)

    def test_edit_sends_revision_guard(self) -> None:
        client = self._client()
        client._get_token = Mock(return_value="token")
        response = Mock()
        response.json.return_value = {"edit": {"result": "Success", "newrevid": 78}}
        client.session.request.return_value = response
        client.edit_page("Template:Item", "body", "summary", baserevid=77)
        data = client.session.request.call_args.kwargs["data"]
        self.assertEqual(77, data["baserevid"])
        self.assertEqual(1, data["nocreate"])
        self.assertNotIn("createonly", data)

    def test_edit_sends_create_only_guard(self) -> None:
        client = self._client()
        client._get_token = Mock(return_value="token")
        response = Mock()
        response.json.return_value = {"edit": {"result": "Success", "newrevid": 1}}
        client.session.request.return_value = response
        client.edit_page("Template:Item", "body", "summary", createonly=True)
        data = client.session.request.call_args.kwargs["data"]
        self.assertEqual(1, data["createonly"])
        self.assertNotIn("baserevid", data)
        self.assertNotIn("nocreate", data)

    def test_edit_error_retains_api_code(self) -> None:
        client = self._client()
        client._get_token = Mock(return_value="token")
        response = Mock()
        response.json.return_value = {"error": {"code": "editconflict"}}
        client.session.request.return_value = response
        with self.assertRaises(wiki.WikiEditError) as raised:
            client.edit_page("Template:Item", "body", "summary", baserevid=77)
        self.assertEqual("editconflict", raised.exception.api_code)

    def test_edit_requires_an_explicit_success_result(self) -> None:
        client = self._client()
        client._get_token = Mock(return_value="token")
        response = Mock()
        response.json.return_value = {"edit": {}}
        client.session.request.return_value = response
        with self.assertRaises(wiki.WikiEditError) as raised:
            client.edit_page("Template:Item", "body", "summary", baserevid=77)
        self.assertEqual("unexpected-response", raised.exception.api_code)


class DeploySelectionTests(unittest.TestCase):
    def _config_dir(self, temp_dir: str) -> Path:
        root = Path(temp_dir)
        (root / "Template_Item.mediawiki").write_text("item\n", encoding="utf-8")
        (root / "MediaWiki_Common.css").write_text("css\n", encoding="utf-8")
        (root / "MediaWiki_Common.js").write_text("js\n", encoding="utf-8")
        (root / "README.md").write_text("docs\n", encoding="utf-8")
        return root

    def test_all_selects_only_configuration_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._config_dir(temp_dir)
            with (
                patch.object(wiki, "config_dir", return_value=root),
                patch.object(
                    deploy_config,
                    "tracked_config_names",
                    return_value=[
                        "Template_Item.mediawiki",
                        "MediaWiki_Common.css",
                        "MediaWiki_Common.js",
                    ],
                ),
            ):
                selected = deploy_config.select_files([], True)
        self.assertEqual(
            ["MediaWiki_Common.css", "MediaWiki_Common.js", "Template_Item.mediawiki"],
            [path.name for path in selected],
        )

    def test_explicit_selection_is_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._config_dir(temp_dir)
            with (
                patch.object(wiki, "config_dir", return_value=root),
                patch.object(
                    deploy_config,
                    "tracked_config_names",
                    return_value=["Template_Item.mediawiki"],
                ),
            ):
                selected = deploy_config.select_files(
                    ["Template_Item.mediawiki", "Template_Item.mediawiki"], False
                )
        self.assertEqual(["Template_Item.mediawiki"], [path.name for path in selected])

    def test_explicit_selection_rejects_an_untracked_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._config_dir(temp_dir)
            with (
                patch.object(wiki, "config_dir", return_value=root),
                patch.object(deploy_config, "tracked_config_names", return_value=[]),
            ):
                with self.assertRaisesRegex(ValueError, "not tracked by Git"):
                    deploy_config.select_files(["Template_Item.mediawiki"], False)

    def test_all_rejects_an_in_root_untracked_symlink_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "Template_Target.mediawiki"
            target.write_text("target\n", encoding="utf-8")
            link = root / "Template_Link.mediawiki"
            try:
                link.symlink_to(target)
            except OSError as error:
                if getattr(error, "winerror", None) != 1314:
                    raise
                original_resolve = Path.resolve

                def resolve(path: Path, strict: bool = False) -> Path:
                    if path == link:
                        return target
                    return original_resolve(path, strict=strict)

                resolver = patch.object(Path, "resolve", new=resolve)
            else:
                resolver = contextlib.nullcontext()
            with (
                resolver,
                patch.object(wiki, "config_dir", return_value=root),
                patch.object(
                    deploy_config,
                    "tracked_config_names",
                    return_value=["Template_Link.mediawiki"],
                ),
            ):
                with self.assertRaisesRegex(ValueError, "not tracked by Git"):
                    deploy_config.select_files([], True)

    def test_selection_requires_one_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "Give --all"):
            deploy_config.select_files([], False)
        with self.assertRaisesRegex(ValueError, "not both"):
            deploy_config.select_files(["Template_Item.mediawiki"], True)

    def test_duplicate_normalized_title_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "Template_Foo_Bar.mediawiki").write_text("one\n", encoding="utf-8")
            (root / "Template_Foo__Bar.mediawiki").write_text("two\n", encoding="utf-8")
            with (
                patch.object(wiki, "config_dir", return_value=root),
                patch.object(
                    deploy_config,
                    "tracked_config_names",
                    return_value=[
                        "Template_Foo_Bar.mediawiki",
                        "Template_Foo__Bar.mediawiki",
                    ],
                ),
            ):
                with self.assertRaisesRegex(ValueError, "Duplicate wiki title"):
                    deploy_config.select_files([], True)

    def test_all_rejects_an_unknown_configuration_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "Category_Bad.mediawiki").write_text("body\n", encoding="utf-8")
            with (
                patch.object(wiki, "config_dir", return_value=root),
                patch.object(
                    deploy_config,
                    "tracked_config_names",
                    return_value=["Category_Bad.mediawiki"],
                ),
            ):
                with self.assertRaisesRegex(ValueError, "must begin"):
                    deploy_config.select_files([], True)

    def test_tracked_names_ignore_non_config_and_nested_files(self) -> None:
        result = Mock(
            stdout=(
                b"wiki-config/Template_Item.mediawiki\0"
                b"wiki-config/README.md\0"
                b"wiki-config/nested/Template_Nested.mediawiki\0"
                b"publish-ready/Template_Old.mediawiki\0"
            )
        )
        with patch.object(deploy_config.subprocess, "run", return_value=result) as run:
            names = deploy_config.tracked_config_names()
        self.assertEqual(["Template_Item.mediawiki"], names)
        run.assert_called_once_with(
            ["git", "ls-files", "-z", "--", "wiki-config"],
            cwd=wiki.REPO_ROOT,
            capture_output=True,
            check=True,
            timeout=15,
        )

    def test_dry_run_makes_no_client(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._config_dir(temp_dir)
            stdout = io.StringIO()
            with (
                patch.object(wiki, "config_dir", return_value=root),
                patch.object(
                    deploy_config,
                    "tracked_config_names",
                    return_value=["Template_Item.mediawiki"],
                ),
                patch.object(wiki, "make_client") as make_client,
                patch.object(
                    sys, "argv", ["deploy-config.py", "Template_Item.mediawiki"]
                ),
                contextlib.redirect_stdout(stdout),
            ):
                result = deploy_config.main()
        self.assertEqual(0, result)
        make_client.assert_not_called()
        self.assertIn("DRY RUN - no network calls", stdout.getvalue())

    def test_execute_exits_nonzero_when_a_page_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._config_dir(temp_dir)
            make_client = Mock(return_value=Mock())
            deploy = Mock(side_effect=wiki.WikiEditError({"code": "permissiondenied"}))
            stdout = io.StringIO()
            with (
                patch.object(wiki, "config_dir", return_value=root),
                patch.object(
                    deploy_config,
                    "tracked_config_names",
                    return_value=["Template_Item.mediawiki"],
                ),
                patch.object(wiki, "make_client", make_client),
                patch.object(deploy_config, "_deploy_with_retry", deploy),
                patch.object(
                    sys,
                    "argv",
                    ["deploy-config.py", "Template_Item.mediawiki", "--execute"],
                ),
                contextlib.redirect_stdout(stdout),
            ):
                result = deploy_config.main()
        self.assertEqual(1, result)
        make_client.assert_called_once_with()
        deploy.assert_called_once()
        self.assertIn("failed=1", stdout.getvalue())

    def test_execute_stops_before_later_pages_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._config_dir(temp_dir)
            client = Mock()
            make_client = Mock(return_value=client)
            deploy = Mock(
                side_effect=[
                    "deployed",
                    wiki.WikiEditError({"code": "permissiondenied"}),
                ]
            )
            stdout = io.StringIO()
            with (
                patch.object(wiki, "config_dir", return_value=root),
                patch.object(
                    deploy_config,
                    "tracked_config_names",
                    return_value=[
                        "MediaWiki_Common.css",
                        "MediaWiki_Common.js",
                        "Template_Item.mediawiki",
                    ],
                ),
                patch.object(wiki, "make_client", make_client),
                patch.object(deploy_config, "_deploy_with_retry", deploy),
                patch.object(
                    sys,
                    "argv",
                    [
                        "deploy-config.py",
                        "--all",
                        "--execute",
                        "--summary",
                        "audit batch",
                    ],
                ),
                contextlib.redirect_stdout(stdout),
            ):
                result = deploy_config.main()
        self.assertEqual(1, result)
        make_client.assert_called_once_with()
        self.assertEqual(2, deploy.call_count)
        self.assertEqual(
            (client, root / "MediaWiki_Common.css", "audit batch"),
            deploy.call_args_list[0].args,
        )
        self.assertEqual({}, deploy.call_args_list[0].kwargs)
        self.assertEqual(
            (client, root / "MediaWiki_Common.js", "audit batch"),
            deploy.call_args_list[1].args,
        )
        self.assertEqual({}, deploy.call_args_list[1].kwargs)
        output = stdout.getvalue()
        self.assertIn("FAIL  MediaWiki_Common.js", output)
        self.assertEqual(
            "done: deployed=1 unchanged=0 failed=1 selected=3",
            output.splitlines()[-1],
        )

    def test_invalid_utf8_later_source_aborts_before_client_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._config_dir(temp_dir)
            (root / "Template_Item.mediawiki").write_bytes(b"\xff")
            make_client = Mock()
            deploy = Mock()
            stdout = io.StringIO()
            with (
                patch.object(wiki, "config_dir", return_value=root),
                patch.object(
                    deploy_config,
                    "tracked_config_names",
                    return_value=[
                        "MediaWiki_Common.css",
                        "MediaWiki_Common.js",
                        "Template_Item.mediawiki",
                    ],
                ),
                patch.object(wiki, "make_client", make_client),
                patch.object(deploy_config, "_deploy_with_retry", deploy),
                patch.object(sys, "argv", ["deploy-config.py", "--all", "--execute"]),
                contextlib.redirect_stdout(stdout),
            ):
                result = deploy_config.main()
        self.assertEqual(1, result)
        make_client.assert_not_called()
        deploy.assert_not_called()

    def test_execute_reports_mixed_success_and_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._config_dir(temp_dir)
            client = Mock()
            make_client = Mock(return_value=client)
            deploy = Mock(side_effect=["deployed", "unchanged", "deployed"])
            stdout = io.StringIO()
            with (
                patch.object(wiki, "config_dir", return_value=root),
                patch.object(
                    deploy_config,
                    "tracked_config_names",
                    return_value=[
                        "MediaWiki_Common.css",
                        "MediaWiki_Common.js",
                        "Template_Item.mediawiki",
                    ],
                ),
                patch.object(wiki, "make_client", make_client),
                patch.object(deploy_config, "_deploy_with_retry", deploy),
                patch.object(
                    sys,
                    "argv",
                    [
                        "deploy-config.py",
                        "--all",
                        "--execute",
                        "--summary",
                        "audit batch",
                    ],
                ),
                contextlib.redirect_stdout(stdout),
            ):
                result = deploy_config.main()
        self.assertEqual(0, result)
        make_client.assert_called_once_with()
        self.assertEqual(3, deploy.call_count)
        for call, filename in zip(
            deploy.call_args_list,
            ["MediaWiki_Common.css", "MediaWiki_Common.js", "Template_Item.mediawiki"],
        ):
            self.assertEqual((client, root / filename, "audit batch"), call.args)
            self.assertEqual({}, call.kwargs)
        output = stdout.getvalue()
        self.assertEqual(
            "done: deployed=2 unchanged=1 failed=0 selected=3",
            output.splitlines()[-1],
        )
        self.assertNotIn("FAIL  ", output)


class DeployGuardTests(unittest.TestCase):
    def _source(self, temp_dir: str, text: str = "repo\n") -> Path:
        path = Path(temp_dir) / "Template_Item.mediawiki"
        path.write_text(text, encoding="utf-8")
        return path

    def test_matching_page_is_not_written(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._source(temp_dir)
            client = Mock()
            client.get_page_with_revid.return_value = ("repo", 77)
            self.assertEqual(
                "unchanged",
                deploy_config._deploy_with_retry(client, source, "summary"),
            )
        client.edit_page.assert_not_called()

    def test_existing_page_uses_live_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._source(temp_dir)
            client = Mock()
            client.get_page_with_revid.return_value = ("old", 77)
            client.edit_page.return_value = {"newrevid": 78}
            self.assertEqual(
                "deployed",
                deploy_config._deploy_with_retry(client, source, "summary"),
            )
        self.assertEqual(77, client.edit_page.call_args.kwargs["baserevid"])
        self.assertFalse(client.edit_page.call_args.kwargs["createonly"])
        self.assertEqual(
            ("Template:Item", "repo\n", "summary"),
            client.edit_page.call_args.args,
        )
        self.assertEqual(1, client.edit_page.call_count)

    def test_missing_page_uses_create_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._source(temp_dir)
            client = Mock()
            client.get_page_with_revid.return_value = None
            client.edit_page.return_value = {"newrevid": 1}
            deploy_config._deploy_with_retry(client, source, "summary")
        self.assertIsNone(client.edit_page.call_args.kwargs["baserevid"])
        self.assertTrue(client.edit_page.call_args.kwargs["createonly"])


class DeployRetryTests(unittest.TestCase):
    def _http_error(self, status: int) -> requests.HTTPError:
        response = Mock(status_code=status)
        return requests.HTTPError(response=response)

    def _json_response(self, payload: dict[str, object]) -> Mock:
        response = Mock(status_code=200)
        response.json.return_value = payload
        return response

    def test_transient_query_failure_is_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "Template_Item.mediawiki"
            source.write_text("repo\n", encoding="utf-8")
            client = wiki.WikiClient.__new__(wiki.WikiClient)
            client.api_url = "https://example.test/api.php"
            client.session = Mock()
            client.session.request.side_effect = [
                self._json_response({"error": {"code": "readonly"}}),
                self._json_response(
                    {
                        "query": {
                            "pages": [
                                {
                                    "revisions": [
                                        {
                                            "revid": 77,
                                            "slots": {"main": {"content": "old"}},
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                ),
                self._json_response({"query": {"tokens": {"csrftoken": "token"}}}),
                self._json_response({"edit": {"result": "Success", "newrevid": 78}}),
            ]
            with patch.object(deploy_config.time, "sleep"):
                result = deploy_config._deploy_with_retry(client, source, "summary")
        self.assertEqual("deployed", result)
        self.assertEqual(4, client.session.request.call_count)

    def test_transient_http_failure_is_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "Template_Item.mediawiki"
            source.write_text("repo\n", encoding="utf-8")
            client = Mock()
            client.get_page_with_revid.return_value = ("old", 77)
            client.edit_page.side_effect = [
                self._http_error(503),
                {"result": "Success", "newrevid": 78},
            ]
            with patch.object(deploy_config.time, "sleep"):
                result = deploy_config._deploy_with_retry(client, source, "summary")
        self.assertEqual("deployed", result)
        self.assertEqual(2, client.get_page_with_revid.call_count)
        self.assertEqual(2, client.edit_page.call_count)

    def test_transient_api_failure_is_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "Template_Item.mediawiki"
            source.write_text("repo\n", encoding="utf-8")
            client = Mock()
            client.get_page_with_revid.return_value = ("old", 77)
            client.edit_page.side_effect = [
                wiki.WikiEditError({"code": "readonly"}),
                {"result": "Success", "newrevid": 78},
            ]
            with patch.object(deploy_config.time, "sleep"):
                deploy_config._deploy_with_retry(client, source, "summary")
        self.assertEqual(2, client.get_page_with_revid.call_count)
        self.assertEqual(2, client.edit_page.call_count)

    def test_retry_adopts_an_edit_that_already_landed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "Template_Item.mediawiki"
            source.write_text("repo\n", encoding="utf-8")
            client = Mock()
            client.get_page_with_revid.side_effect = [("old", 77), ("repo", 78)]
            client.edit_page.side_effect = self._http_error(503)
            with patch.object(deploy_config.time, "sleep"):
                result = deploy_config._deploy_with_retry(client, source, "summary")
        self.assertEqual("unchanged", result)
        self.assertEqual(2, client.get_page_with_revid.call_count)
        self.assertEqual(1, client.edit_page.call_count)

    def test_permanent_failure_is_not_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "Template_Item.mediawiki"
            source.write_text("repo\n", encoding="utf-8")
            client = Mock()
            client.get_page_with_revid.return_value = ("old", 77)
            client.edit_page.side_effect = self._http_error(400)
            with self.assertRaises(requests.HTTPError):
                deploy_config._deploy_with_retry(client, source, "summary")
        self.assertEqual(1, client.get_page_with_revid.call_count)
        self.assertEqual(1, client.edit_page.call_count)

    def test_edit_conflict_is_not_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "Template_Item.mediawiki"
            source.write_text("repo\n", encoding="utf-8")
            client = Mock()
            client.get_page_with_revid.return_value = ("old", 77)
            client.edit_page.side_effect = wiki.WikiEditError({"code": "editconflict"})
            with self.assertRaises(wiki.WikiEditError):
                deploy_config._deploy_with_retry(client, source, "summary")
        self.assertEqual(1, client.get_page_with_revid.call_count)
        self.assertEqual(1, client.edit_page.call_count)

    def test_retry_rejects_an_intervening_live_edit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "Template_Item.mediawiki"
            source.write_text("repo\n", encoding="utf-8")
            client = Mock()
            client.get_page_with_revid.side_effect = [("old", 77), ("other", 78)]
            client.edit_page.side_effect = self._http_error(503)
            with (
                patch.object(deploy_config.time, "sleep"),
                self.assertRaises(wiki.WikiEditError) as raised,
            ):
                deploy_config._deploy_with_retry(client, source, "summary")
        self.assertEqual("intervening-edit", raised.exception.api_code)
        self.assertEqual(2, client.get_page_with_revid.call_count)
        self.assertEqual(1, client.edit_page.call_count)

    def test_retries_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "Template_Item.mediawiki"
            source.write_text("repo\n", encoding="utf-8")
            client = Mock()
            client.get_page_with_revid.return_value = ("old", 77)
            client.edit_page.side_effect = self._http_error(503)
            with (
                patch.object(deploy_config.time, "sleep"),
                self.assertRaisesRegex(RuntimeError, "after 3 attempts"),
            ):
                deploy_config._deploy_with_retry(client, source, "summary")
        self.assertEqual(3, client.get_page_with_revid.call_count)
        self.assertEqual(3, client.edit_page.call_count)


class DiffWikiTests(unittest.TestCase):
    def test_missing_live_page_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "Template_Item.mediawiki").write_text("repo\n", encoding="utf-8")
            client = Mock()
            client.get_page_with_revid.return_value = None
            with (
                patch.object(wiki, "config_dir", return_value=root),
                patch.object(wiki, "make_client", return_value=client),
                patch.object(sys, "argv", ["diff-wiki.py", "Template_Item.mediawiki"]),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                result = diff_wiki.main()
        self.assertEqual(1, result)

    def test_difference_is_printed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "Template_Item.mediawiki").write_text("repo\n", encoding="utf-8")
            client = Mock()
            client.get_page_with_revid.return_value = ("live\n", 77)
            stdout = io.StringIO()
            with (
                patch.object(wiki, "config_dir", return_value=root),
                patch.object(wiki, "make_client", return_value=client),
                patch.object(sys, "argv", ["diff-wiki.py", "Template_Item.mediawiki"]),
                contextlib.redirect_stdout(stdout),
            ):
                result = diff_wiki.main()
        self.assertEqual(0, result)
        self.assertIn("-live", stdout.getvalue())
        self.assertIn("+repo", stdout.getvalue())

    def test_matching_page_reports_no_difference(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "Template_Item.mediawiki").write_text("repo\n", encoding="utf-8")
            client = Mock()
            client.get_page_with_revid.return_value = ("repo", 77)
            stdout = io.StringIO()
            with (
                patch.object(wiki, "config_dir", return_value=root),
                patch.object(wiki, "make_client", return_value=client),
                patch.object(sys, "argv", ["diff-wiki.py", "Template_Item.mediawiki"]),
                contextlib.redirect_stdout(stdout),
            ):
                result = diff_wiki.main()
        self.assertEqual(0, result)
        self.assertIn("matches repo source", stdout.getvalue())
