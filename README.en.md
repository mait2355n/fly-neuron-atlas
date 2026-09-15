# Fly Neuron Atlas

An evidence and data snapshot of completed analyses of fly neural connectivity,
activity, and motor function, covering 16 research bundles through 2026-09-15.
The detailed findings are in Japanese; table headers and runnable tools are in English.

## Included results

- An atlas of all **815 motor-annotated neurons** in MaleCNS v1.0, with 330,888 direct incoming edges (total weight 3,224,310).
- **2,155 shared upstream candidates**, defined relative to 166 selected motor neurons in 42 muscle groups, with individual edge weight ≥10 and at least two distinct target groups.
- All direct incoming and outgoing edges for **40 selected candidates**: 39,909 incoming and 323,398 outgoing edges.
- Reanalysis tables for **23 DNa01/DNa02 voltage recordings, 33 channels**, representing 53,855 seconds of distributed voltage data. Technical eligibility after exclusions is 51,816.18 seconds; this is not a physiological quality certification.
- Documented navigation and experience-dependent response analyses, corrections, negative results, and explicit unresolved questions.

## Quick start

```sh
python scripts/verify.py
python scripts/reproduce.py
```

Python 3.10+; standard library only. Commands are read-only, emit JSON, and exit 0
on agreement or 1 on inconsistency. Reaggregation checks edge counts, per-cell
totals, the exact shared-candidate set, threshold sensitivity, and annotation
exclusion. Saved activity correlations are read from tables by this command;
they are not recomputed from raw voltage.

For an optional voltage rerun, see [reproduction instructions](docs/reproducing.md).
Raw voltage files are fetched separately by immutable Dataverse file IDs and
checked against recorded size and MD5. They are not bundled here.

## Reading the evidence

Start with the [completed-work catalog](docs/coverage.md),
[body and activity findings](docs/findings-body-and-activity.md),
[navigation and learning findings](docs/findings-navigation-and-learning.md),
[data dictionary](docs/data-dictionary.md), and [limitations](docs/limitations.md).

An anatomical connection is not a firing event, intervention effect, or muscle
force. MaleCNS IDs identify a reconstructed male specimen; physiological data
come from other specimens, often females. Similar type names do not establish
physical identity. Unobserved edges remain unknown. This project does not claim
a complete functional decomposition of the fly nervous system, a homologous
cerebrum/cerebellum split, or demonstrated general learning in the selected cells.

Original software is MIT; original documentation and curation contributions are
CC BY 4.0. Upstream terms and credits remain applicable. See
[third-party notices](THIRD_PARTY_NOTICES.md), [provenance](data/provenance.json),
and [citation metadata](CITATION.cff). Cite the underlying datasets and papers as
well as this curation.
