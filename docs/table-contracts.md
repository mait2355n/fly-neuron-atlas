# Saved-table contracts

`python3 scripts/verify.py` checks file hashes, provenance shapes and the
structural/activity contracts below. `python3 scripts/reproduce.py` applies the
same contracts before recomputing the published summary. Both commands are
read-only, use the Python standard library, and read text as UTF-8.

A matching checksum identifies a saved file. The table contracts check specified
relationships within those files; they do not establish upstream completeness,
raw-voltage reproduction or biological function.

## Identity and scalar rules

The contracts in [table_contracts.py](../scripts/table_contracts.py) cover
`motor_atlas`, `motor_groups`, `shared_candidates`, `studied_cells`,
`studied_totals`, `annotation_sensitivity`, the three connectivity tables, and
activity `inventory`, `channels` and `pairs`. Other provenance tables receive
the existing shape, source-reference and hash checks.

| Table | Required identity or combination |
| --- | --- |
| Atlas, candidates, studied cells | Unique body ID within the dataset in `snapshot.json`; explicit dataset fields must match that dataset |
| Motor groups, annotation sensitivity | Unique body ID in the same snapshot; group members reference atlas cells and sensitivity rows cover exactly the candidate IDs |
| Connectivity | Unique directed `(dataset, bodyId_pre, bodyId_post)`; tables without a dataset column inherit the declared snapshot dataset |
| Studied totals | Exactly one `(target_bodyId, direction, threshold)` for every studied cell, incoming/outgoing direction and threshold 1, 3, 5, 10 |
| Activity inventory | Unique `fly` and a nonduplicated ordered list of supported neuron labels |
| Activity channels | Exactly the inventory's `(fly, neuron)` identities, including channel position, neuron type and side |
| Activity pairs | Exactly the expected `(fly, signal, target)` identities for usable two-channel records |

Body IDs and structural counts are canonical decimal integers. Edge `weight` is
positive; `weightHP` and `weightHR` are nonnegative integers. Declared Boolean
fields use `True` or `False`, and checked state/direction/threshold fields have
explicit allowed values. Used durations and correlations must be finite, with
nonnegative durations and correlations in [-1, 1]. A missing or invalid scalar
fails its contract; it is never replaced by zero.

Studied rows must equal the candidate rows whose full-I/O state is complete.
Group references must exist. Each edge's declared target endpoint must belong
to the motor or studied scope of its table. Reproduction also recomputes the
per-cell totals, candidate groups and annotation sensitivity values.

## Equality of directed edges

Each comparison checks the complete edge set in the jointly observed scope and
the three saved weights (`weight`, `weightHP`, `weightHR`) for every edge:

| Tables compared | Jointly observed scope |
| --- | --- |
| Motor inputs and studied outgoing | Studied source, motor target |
| Studied incoming and studied outgoing | Studied source, studied target |
| Motor inputs and studied incoming | Any source, target belonging to both motor and studied sets |

A missing edge or changed weight fails even when totals still agree. The report
includes the number of edges on each side, missing-edge counts, conflicting
weights and up to five examples. An empty joint scope is reported as
`no_overlapping_observations`; it does not assert zero connectivity outside the
observed scope. Unobserved edges remain unknown.

## Activity series and principal summary

Inventory order assigns the first label to `ephys_A` and the second to `ephys_B`.
For a usable two-channel record, pairs must contain the first channel's rate
against the second channel's rate, `A_minus_B` against `yaw`, and `A_plus_B`
against `yaw`. Pair kind must agree with the two neuron types. Duplicate keys,
wrong targets, missing series and equal-count substitutions fail.

The principal DNa02 summary explicitly selects `target=yaw` and requires both
`A_minus_B` and `A_plus_B` for `a2_d_08`, `a2_d_12` and `a2_d_13`. The selected
pairs and channels must be eligible for the principal summary. An excluded
channel cannot satisfy that requirement; nonfinite correlation values cannot
enter the reported summary.

## Generated reanalysis artifacts

When `data/reanalysis/PROVENANCE.json` exists, verify also reads its `entries`
through the original provenance-validation path. Each entry declares a
repository-relative `path`, `source_ids` from `data/sources.json`, and either
`format=json` with ordered `top_level_keys`, or CSV `columns` and `rows`.
The original `tables` report count stays unchanged; `generated_artifacts`
reports the number of these additional entries. If the optional file is absent,
`generated_artifacts` is zero and the original checks still apply.

Generated CSV entries can additionally declare:

| Field | Contract |
| --- | --- |
| `primary_key` | Nonempty list of column names; each row must have nonblank key values and a unique tuple |
| `identity_reference` | Repository-relative CSV path; requires `primary_key` and exactly the same set of key tuples as that reference |
| `finite_columns` | List of required numeric columns; blank, nonnumeric, NaN and infinite values fail |

The reference table must also have valid, unique key tuples. Matching identities
does not require matching numerical values: the reanalysis can produce revised
measurements for the same identified records. Tables that declare only a
primary key make no finite-value claim about their other columns. PNG files
remain covered by the manifest and are not provenance entries.

[Generated-provenance tests](../tests/test_generated_provenance.py) refresh
fixture hashes and row counts before changing identities or required values.
They verify that the public CLI rejects duplicate keys, different-fly
substitutions and nonfinite required values even when integrity metadata agrees.

## Reports and evidence limits

Both reports add a `table_contracts` object containing `status`, named `checks`,
up to 30 failure messages, and `edge_comparisons`. Reproduction also includes
the named contract checks in its top-level `checks`. `checks` maps names to
Booleans; edge counts are integers, weight fields are string lists, and examples
contain a key plus the left/right weight arrays (or null for an absent edge).
The inherited `schema_version` is `fly-neuron-atlas-integrity/v1` for verify and
`fly-neuron-atlas-reproduction/v1` for reproduce. Normal reports go to stdout,
with `status=pass` and exit 0 or `status=fail` and exit 1. Verify supplies
`failures`; reproduce supplies recomputed `results`.

Unreadable or malformed required input goes to stderr as
`{"status":"error","message":"..."}` and exits 1. The caller can use the
message or failed check to locate the offending input; repairing that input is
a separate action. These commands do not assign human acceptance.

[Contract tests](../tests/test_table_contracts.py) use small independently
specified tables and refreshed fixture hashes to challenge equal-total weight
changes, missing edges, duplicate identities, wrong labels and targets, invalid
scalars and principal-summary exclusion. Representative public CLI tests cover
reproduction of the saved snapshot and verification of a weight conflict after
refreshing fixture hashes. These tests establish detection for the exercised
saved-table faults; they do not validate voltage analysis or human acceptance.
