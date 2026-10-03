# Wiki Configuration

This directory holds the wiki's CSS, interface pages, modules,
templates, and Bahamut branding. Pages open to community edits belong on Miraheze.

## Files

- `MediaWiki_Common.css`: site styles.
- `MediaWiki_Sidebar.mediawiki`: sidebar navigation, following the
  [wiki structure guide](../docs/wiki-structure.md).
- `MediaWiki_Tabberneue-tabber-category.mediawiki`: a single hyphen that tells
  TabberNeue to suppress its tracking category.
- `Template_*.mediawiki` and `Module_Recipe.mediawiki`: reusable page layouts.
  Empty template fields mean unknown, never zero.
- [assets/](assets/README.md): Bahamut branding used by ManageWiki.

Files used for deployment contain raw MediaWiki source, without frontmatter.
Do not add articles, categories, ordinary file pages, credentials, or local
exports here.

## Comparing and deploying

The [tool guide](../tools/README.md) explains how filenames map to wiki titles,
how to compare source with the live page, and how to preview a deployment.
