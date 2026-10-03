# Comments and prose

These rules cover Python comments, repository docs, and text in wiki
configuration. See the [policy index](README.md) for related guidance.

## Useful comments

Keep comments that explain something the code, names, tests, or surrounding
text cannot make clear:

- Safety constraints and conditions that must hold before a write.
- MediaWiki API or file format quirks.
- Source references and field mappings.
- Command behavior that is not clear from its signature.
- Test setup and the failure it guards against.

Keep identifiers and required values exact. Prefer a short comment beside the
relevant code. Put longer explanations in the guide that owns the topic and
link to it. Remove debugging history, progress notes, next steps, and comments
that repeat the code.

Length and punctuation are guidelines. Clarity, correctness, and source details
matter more.

For example, keep a safety constraint:

```python
# Only --execute may write the selected pages.
```

Remove a comment that repeats the code:

```python
# Increment the index.
index += 1
```

## Help and command output

Docstrings used by argument parsers, help text, output, and errors are part of
the tool's public interface. Review wording changes with the same care as
command changes. Where the code does not explain them, keep the reasons for
preview defaults, explicit execution flags, revision checks, checks for missing
pages, and API validation.

## Documentation and wiki text

Use direct sentences. Avoid stacked modifiers, awkward compounds, filler, and
metaphors that obscure the instruction. For example, write "Place this infobox
at the start of the page" rather than packing the location into its name.
Keep ordinary hyphenated terms when they are useful. Do not alter identifiers,
CSS classes, page titles, field names, or quoted game text to remove hyphens.

Describe current behavior and link to the tool or configuration guide rather
than repeating it. Remove retired paths, maintainer status reports, and
assistant narration. Do not claim that a repository file proves the wiki's
live state.

Text in templates, modules, interface pages, and CSS can appear on
the public wiki. Preserve behavior notes, field meanings, and source details
that an editor could not otherwise infer. Ordinary article-writing rules do
not belong in this repository's public docs.
