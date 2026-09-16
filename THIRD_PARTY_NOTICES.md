# Upstream data and code

Original software is MIT. Original prose and original contributions to curated
tables are CC BY 4.0. These grants do not replace the terms of upstream material.
The initial snapshot was prepared on 2026-09-15 and expanded on 2026-09-16; source-specific information is in
[data/sources.json](data/sources.json) and [docs/sources.md](docs/sources.md).

The September 16 additions have scoped inventories in
[circuits/PUBLICATION.json](circuits/PUBLICATION.json) and
[research/2026-09-16/PROVENANCE.json](research/2026-09-16/PROVENANCE.json).
Normalized circuit inputs retain the MaleCNS attribution and CC BY 4.0 terms.
The Basnak component table retains its dataset attribution and CC BY 4.0 terms.
Kim and Dan raw data and row-level derived tables are excluded under the existing
packaging policy for noncommercial source datasets. Plitt notebook outputs are
not redistributed: article terms do not establish a separate grant for the
unlicensed source repository. Independent factual prose cites the primary works.

|Material used here|Upstream terms|Credit and treatment|
|---|---|---|
|MaleCNS v1.0 annotations and connectome|CC BY 4.0|Berg et al. (2026); MaleCNS collaboration, FlyEM/HHMI Janelia, Cambridge, MRC LMB and Google Research. Selected, projected, grouped and compressed; dataset/version retained|
|Rayshubskiy DNa01/DNa02 dataset, Dataverse 10.7910/DVN/0NCLP1 v1.2|CC0 1.0|Rayshubskiy, Holtz, Wilson and colleagues (2025). Independently detected spikes and computed descriptive statistics; no original MAT bundled|
|Wilson Lab secondary-analysis algorithm|MIT, copyright 2025 Wilson Lab|Full notice at [licenses/Wilson-Lab-MIT.txt](licenses/Wilson-Lab-MIT.txt). Voltage normalization in scripts/ephys_core.py transcribes the fixed source semantics; paths and orchestration are adapted|
|Mussells Pires navigation data, Zenodo10145317|CC BY 4.0|Mussells Pires et al. (2024). Selected-record summaries, intervention means and model-prediction errors; no source code or H5 bundled|
|Huang/Schnitzer voltage data, Zenodo10998457|CC BY 4.0|Huang, Luo et al. (2024). Corrected baseline and response summary with duplicate-record caveat|
|Agrawal proprioception data, Zenodo4307018 / Dryad k3j9kd55t|CC0 1.0|Agrawal et al. (2020). Joint-response and calcium-angle summaries; physiological specimens differ from MaleCNS|
|Other cited papers and anatomical references|Terms remain with each source|Independent factual summaries and citation links. No article full text, publisher figures or supplementary PDFs are redistributed|

The [MIT source for Wilson Lab](https://github.com/wilson-lab/rayshubskiy_elife_102230_secondary_analysis_code/blob/7e2895349266b5cc5fa1bf53ad56e8ecc6c842e8/LICENSE)
is pinned at commit `7e2895349266b5cc5fa1bf53ad56e8ecc6c842e8`.

Dan's simulated model results are discussed with a citation to the MIT-licensed
model, but its source code is not bundled. Dan's experimental activity data
(Figshare25655817.v1) and Isakov's recovery dataset (Zenodo51322) use CC BY-NC 4.0;
their data files and row-level derived tables are omitted from this release.
Independent factual descriptions do not grant rights to those upstream assets.
Chen's repository declares Apache 2.0, but a separate data-specific grant was not
confirmed; its synchronized data files are also omitted.

Third-party body models, mesh assets, paper images and narrated videos are not
part of this distribution. References in the completed-work catalog identify
what was done; they do not imply that those assets are included or relicensed.

When redistributing tables, preserve their source IDs, dataset version,
limitations, upstream credits and license links; identify changes. Do not imply
that the source authors endorse this curation or its interpretations.
