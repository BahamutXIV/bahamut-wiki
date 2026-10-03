# Repository and wiki structure

This guide explains what belongs in the repository and how the wiki's
navigation and templates are organized.

## GitHub and Miraheze

Articles, categories, ordinary file pages, and other pages open to community
edits are maintained on Miraheze. GitHub holds the tools, repository docs,
CSS, interface pages, modules, templates, and Bahamut branding used
by ManageWiki.

Configuration is deployed manually from tracked files to Miraheze.
Changes are not copied back from the wiki. The repository does not import, mirror, back up, or
synchronize ordinary wiki content.

Keep repository changes independent of other checkouts. Do not commit exports, client installers, raw
client data, unapproved game media, credentials, or private maintainer files.

## Repository layout

| Path | Contents |
|---|---|
| `.github/` | Hosted checks and contribution templates |
| `docs/` | Repository policies and wiki structure |
| `tools/` | Comparison and deployment tools, with tests |
| `wiki-config/` | MediaWiki source and branding |

See the [tool guide](../tools/README.md) for commands, authentication, filename
mapping, and checks that prevent conflicting edits. The [configuration guide](../wiki-config/README.md)
describes which source files belong here.

## Navigation

`wiki-config/MediaWiki_Sidebar.mediawiki` defines the sidebar. It starts with
MediaWiki's native navigation group, followed by Content and World. Category
links need a leading colon to link to the category without categorizing the
interface page. `Trials` links to a mainspace page.

Sidebar labels must match their targets and link only to existing pages.
Leave planned pages out of navigation. Keep navigation focused on
Final Fantasy XIV 1.x.

Console Games Wiki provided a reference for navigation and category structure,
not game facts or prose.

## Templates and page layout

Templates and modules provide reusable page layouts. Empty fields mean
unknown, never zero. Their documentation is part of the source and
must match their behavior.

Place summary templates near the start of an article. Keep the description
short when the card already identifies the subject. On monster and attribute
pages, put section headings and tables below the summary. Place recipe tables
under Crafting, or Acquisition/Crafting when the page describes several ways
to obtain something. Omit empty sections.

On quest pages, put requirements, rewards, and chain navigation above the
Walkthrough, Journal, and Dialogue tabs. Open Walkthrough by default. Put NPC
services and levequest objectives before long background or dialogue sections.

Put class, dungeon, company, race, and geography navigation at the end of an
article, above its categories. Geography navigation links to major places and
categories. Keep links to containing areas and lists of nearby places in their articles
rather than repeating a full geography directory on every landmark.

## Branding

`wiki-config/assets/` contains only site branding created by BahamutXIV and
supplied through ManageWiki. It is not an upload folder for ordinary `File:` pages.
