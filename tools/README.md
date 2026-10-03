# Wiki tools

These Python tools compare and deploy wiki configuration.
Pages open to community edits stay on Miraheze.

Run the commands below from the repository root.

## Setup

Use Python 3.12, matching CI. Create a virtual environment:

```text
python -m venv tools/.venv
```

Activate it using the command for your shell, then install the dependencies:

```text
python -m pip install -r tools/requirements.txt
```

## Checks

The tests use temporary files and mocked API responses. They do not need
credentials, network access, a wiki export, or a set of articles.

After setup, run the same checks as CI:

```text
python -m ruff check --no-cache tools
python -m ruff format --check --no-cache tools
python -m unittest discover -s tools/tests
python tools/deploy-config.py --all
```

`tools/requirements.txt` pins Ruff. The root `ruff.toml` selects the Python
error rules `E` and `F`, with `E501` disabled because the formatter owns
wrapping. Ruff respects `.gitignore`, including local tooling and virtual
environments. Apply formatting with `python -m ruff format --no-cache tools`
before running the checks.

Add or update tests when changing Python behavior. Pull requests must pass
the hosted `Repository Checks` job in
[`.github/workflows/checks.yml`](../.github/workflows/checks.yml).

## Configuration filenames

Source files must sit directly in `wiki-config/`, not in a subdirectory.
Deployment accepts only files tracked by Git with a `MediaWiki_`, `Module_`, or `Template_`
prefix and a `.mediawiki`, `.css`, or `.js` extension.

The prefix becomes the wiki namespace, and underscores in the rest of the
name become spaces. The `.mediawiki` extension is removed; `.css` and `.js`
stay in the title. For example, `Template_Item.mediawiki` becomes
`Template:Item`, while `MediaWiki_Common.css` becomes `MediaWiki:Common.css`.

## Compare and deploy

Set up [authentication](#authentication) before comparing with the live wiki
or deploying. Deployment previews do not use the network or need credentials.

Compare one file with its live page:

```text
python tools/diff-wiki.py Template_Item.mediawiki
```

Preview one file or all configuration:

```text
python tools/deploy-config.py Template_Item.mediawiki
python tools/deploy-config.py --all
```

Review the raw source and its differences from the live page, then preview the
selected files. Use `--execute` only after that review:

```text
python tools/deploy-config.py Template_Item.mediawiki --execute
```

Use `--summary "describe the change"` to set the wiki edit summary. The default
is `config: deploy from GitHub`.

Deployment copies tracked source to Miraheze. It skips pages that already
match, checks the live revision to avoid overwriting concurrent edits, and
uses a create-only check when a page is missing.

### Failures and retries

The tool makes up to three attempts for HTTP 429, 500, 502, 503, and 504
responses, or MediaWiki rate-limit and read-only responses. Other failures
stop the batch and return a nonzero exit code. Pages written before a failure
remain changed.

Check the reported failure and review any conflicting live edits before
retrying. A rerun skips matching pages, but it reads the live revision again;
a fresh run is not a substitute for reviewing the current diff.

The tools do not import articles, synchronize content back to GitHub, upload
assets, or make automatic backups. Edit ordinary pages and manage the wiki on
Miraheze.

## Authentication

Copy `.env.example` to `.env` at the repository root. Fill in `WIKI_USER`,
`WIKI_BOT_PASS`, and `WIKI_API_URL`. Use a revocable bot password with only the
permissions needed to edit configuration.

Never commit `.env` or include credentials in configuration files, command
arguments, logs, or issue reports. Use a direct HTTPS API URL; the tools do
not follow redirects.
