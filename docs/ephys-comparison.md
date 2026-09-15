# Compare saved electrophysiology results

`scripts/compare_ephys.py` is a standard-library-only comparison command. It
does not import the detector or recompute expected values from the generated
run. The default reference is the archived `data/activity` snapshot (v1).

```sh
python scripts/compare_ephys.py --generated .local/ephys --fly a2_d_08
python scripts/compare_ephys.py --generated .local/ephys --reference /path/to/reference
```

Use repeated `--fly` options for a subset. Without them, `RUN.json`'s explicit
`selected_flies` list selects the records; if absent, the reference inventory
selects all records. Unknown or repeated selections are errors. A generated
inventory never defines the expected population. Known records outside an
explicit subset are listed as ignored; unknown generated records fail.

| Table | Primary key |
| --- | --- |
| `inventory.csv` | `fly` |
| `channels.csv` | `fly, neuron` |
| `pairs.csv` | `fly, kind, signal, target` |
| `lag_curves.csv` | `fly, signal, target, lag_ms` |

All four files and their key headers must exist, including header-only tables
when no pair is estimable. Required scientific columns are declared in
`REQUIRED` in the script. All additional common columns are also compared,
except `processing_seconds`. Columns present on one side only are named in the
report; nonrequired supplemental columns are outside that comparison. This
allows a base run to be compared with the archive's supplemental channel
annotations without pretending to regenerate those annotations.

Duplicate keys, missing or extra rows, missing required columns and differing
cells produce `status: fail` and exit 1. Invalid selections, malformed CSV and
unreadable inputs produce JSON `status: error` and exit 2. Successful comparisons
produce JSON `status: pass` and exit 0. Argument syntax errors follow argparse's
stderr/exit-2 convention. Each differing cell retains both input strings, its
key, column and reason. JSON is emitted on stdout without nonstandard NaN tokens.

Finite numbers agree when `abs(generated-reference) <= atol + rtol*abs(reference)`.
Defaults are `--atol 1e-10 --rtol 1e-10`; keys and text labels require exact agreement
(integer `lag_ms` spellings are normalized). Negative or nonfinite tolerances
are rejected. Infinity never agrees, including infinity against itself.
Empty cells and NaN agree only in the per-table `NAN_COLUMNS` allowlist, printed
in each report: undefined correlations, lag peaks, no-stimulus rate, refractory
fraction and the named supplemental correlation summaries. Counts and timing
fields do not receive that equivalence. Two excluded rows can have jointly
absent measurements; their exclusion status remains visible in the report.

Numerical agreement and run completion are separate observations. `run_status`
is reported without turning an excluded or partial run into completed analysis.
The corrected epoch method can differ from v1 around clock resets; those
differences are reported with the same tolerances. Select an explicitly
versioned corrected reference using `--reference` when comparing like methods.
Agreement neither establishes biological correctness nor proves that a saved
reference is scientifically valid.

The JSON envelope has string `schema_version: fly-neuron-atlas-ephys-comparison/v1`
and string enum `status: pass|fail|error`. Comparisons include a `tables` object,
string arrays `selected_flies`, named tolerance numbers, source paths and
per-table details. Input errors include a string `message`. The process exit
code supplies the machine-readable failure category described above. To resolve
a failure, inspect its named keys/columns and both cell values; change the
reference only when a separately established reference version is intended.
`tests/test_ephys_compare.py` executes representative good, missing, extra,
duplicate, wrong-target, nonfinite and tolerance fixtures through this CLI.
