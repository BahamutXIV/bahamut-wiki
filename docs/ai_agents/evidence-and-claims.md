# Evidence and provenance

These rules cover factual claims and source records in repository docs, tools,
configuration, and Bahamut branding. Ordinary wiki content belongs
on Miraheze. See the [policy index](README.md) for related guidance.

## Recording sources

Keep enough detail for an editor to verify why a file exists or how it was made:

- CSS and interface comments explain behavior that is not obvious and name the markup
  or platform feature that uses the rule.
- The [branding guide](../../wiki-config/assets/README.md) records authorship,
  dimensions, color modes, and image transformations.
- Template and module comments explain fields and mappings where needed.
- Use SHA-256 when a claim depends on two files having identical bytes.

Layout, navigation, category, and styling references do not establish game
facts. Do not add external game media, assets derived from the client, raw captures, or
cached external sources to configuration.

## Making claims

State only what the source supports. Preserve uncertainty and values set
by hand. An empty template field means unknown, never zero.

A local path alone is not a citation. For a fact established in another
repository, use a stable `repository:path` reference. Add a row, symbol, or
section when useful. Public citations must not depend on a local absolute
path, branch, rewritten commit hash, or the date of a work session.

Keep dimensions, hashes, field positions, attempt limits, and other values
exact when precision matters. Rounded estimates are fine where appropriate;
label them as estimates when needed. Omit counts that merely describe how
many files or results were searched.

Tracked configuration shows what the repository specifies. Confirm live wiki
state with a separate, deliberate read or write result before reporting it.
