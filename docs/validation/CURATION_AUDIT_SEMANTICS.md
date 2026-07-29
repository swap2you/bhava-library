# Curation audit-table semantics

## Taxonomy relations

`taxonomy_relations` may remain empty. Curation v1.1 intentionally uses a flat,
multi-dimensional controlled vocabulary; an empty table does not imply a failed
taxonomy load. Relations should be added only when a reviewed hierarchy is
adopted.

## Human classification reviews

`classification_reviews` remains empty until a human reviewer records a real
decision. Automated rules and command runs must never create synthetic reviewer
names or decisions.

## Machine curation runs and events

The following commands create one `curation_runs` row and paired
`curation_events` (`started` plus `completed` or `failed`):

- `classify`
- `enrich`
- `build-views`
- `sunday-school`
- `candidates`
- `integrity`

`stats_json` records the actual command result. Failure records contain only the
exception type and message. These rows are operational audit evidence and do
not represent human doctrinal, rights, age, or product approval.
