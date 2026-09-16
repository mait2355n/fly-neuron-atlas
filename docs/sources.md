# 出典と取得先

以下は公表成果を読むための一次入口。接続、公開実測、介入、模型、文献上の型対応を分ける。資料の利用条件を確認した日付は2026年9月15日。各表のsource_idsは[data/sources.json](../data/sources.json)に対応する。

9月16日追加分の出典・取得版・再配布範囲は、[経験・方位の公開記録](../research/2026-09-16/PROVENANCE.json)と[回路入力の公開記録](../circuits/PUBLICATION.json)に分けた。以下の旧表のsource_idsと来歴は保持する。

## 主な資料

|ID|原論文・データ|利用条件と用途|
|---|---|---|
|`malecns`|[MaleCNS v1.0 annotation and connectome data](https://doi.org/10.1016/j.cell.2026.08.015) / [data](https://male-cns.janelia.org/download/)|CC-BY-4.0。Dataset license is not a license for neuPrint software, site source code, or third-party FlyWire/hemibrain transformed assets. Do not mix specimens or versions.|
|`rayshubskiy-data`|[Rayshubskiy et al. steering electrophysiology](https://doi.org/10.7554/eLife.102230.3) / [data](https://doi.org/10.7910/DVN/0NCLP1)|CC0-1.0。Dataset license and code license are separate. DNa code-derived implementation must retain Wilson Lab MIT notice. Keep 23 MAT, 33 channels and biological specimens distinct.|
|`huang`|[Huang, Luo et al. voltage traces](https://doi.org/10.1038/s41586-024-07819-w) / [data](https://zenodo.org/records/10998457)|CC-BY-4.0。Use completed 96-record tables, not baseline 76-record table. Preserve duplicate/numeric-source cautions from discrepancy-resolution analysis.|
|`mccurdy`|[McCurdy et al. reversal-learning Source Data](https://doi.org/10.1038/s41467-021-21388-w) / [data](https://www.nature.com/articles/s41467-021-21388-w)|CC-BY-4.0。Author is McCurdy et al., not Zhao et al. Preserve corrected 19-value window and source inconsistencies; this check does not license unrelated publisher assets.|
|`pires`|[Mussells Pires et al. navigation data](https://doi.org/10.1038/s41586-023-07006-3) / [data](https://zenodo.org/records/10145317)|CC-BY-4.0。Pires code archive 10.5281/zenodo.10232698 v1.0.0 also explicitly CC BY 4.0; translated/adapted upstream code must not be labelled solely MIT. EPG and FC2 are separate fly groups.|
|`agrawal`|[Agrawal et al. proprioception physiology and behavior](https://doi.org/10.7554/eLife.60299) / [data](https://zenodo.org/records/4307018)|CC0-1.0。Passive female T1 physiology and decapitated left foreleg interventions do not identify six right T2 MaleCNS candidates.|
|`durrieu`|[Durrieu et al. affordance experiments and silencing screen](https://doi.org/10.64898/2026.04.28.721021) / [data](https://doi.org/10.7910/DVN/91R87T)|CC0-1.0。Data CC0 does not transfer to article PDF (local record says CC BY-NC 4.0). No article or upstream code copying is proposed. Screen records may use an older pinned version; preserve source manifest.|
|`rozenfeld`|[Rozenfeld and Parnas activity/archive data](https://doi.org/10.1126/sciadv.adq3016) / [data](https://zenodo.org/records/13764295)|CC-BY-4.0。The dataset archive includes upstream code. Copying/translation of it needs CC BY notices; raw code is not included in the allowlist.|
|`dan_model`|[Dan et al. navigation model](https://doi.org/10.1016/j.neuron.2024.04.036) / [data](https://github.com/HermundstadLab/flyVisualLearning/tree/09fd7101772567eafbe390a01f84944adc711c08)|MIT。Simulation output is not biological recording. Zenodo v1.0 archive11062515 lists CC BY 4.0; use the exact pinned GitHub code license instead of conflating archive records.|
|`dan_activity`|[Dan et al. behavioral and calcium imaging data v1](https://doi.org/10.1016/j.neuron.2024.04.036) / [data](https://doi.org/10.25378/janelia.25655817.v1)|CC-BY-NC-4.0。Do not relabel upstream fragments/derived copied numeric arrays CC BY 4.0. This is a conservative packaging recommendation, not a legal conclusion that every independent computed fact inherits NC.|
|`isakov`|[Isakov and Buchanan locomotion recovery data](https://zenodo.org/records/51322) / [data](https://doi.org/10.5281/zenodo.51322)|CC-BY-NC-4.0。Exclude thresholded_frames and numerical-table reuse from default CC BY allowlist. Own factual prose summary with primary citation can remain; no inference that pure facts are copyrighted is made.|
|`chen`|[Chen et al. synchronized GLM input ZIPs](https://doi.org/10.1038/s41593-023-01281-z) / [data](https://github.com/NeLy-EPFL/Ascending_neuron_screen_analysis_pipeline/tree/1dd7cbdc347f5484e22ff4ab1a5f4f132b397c76/02_Fig2_output_of_published_version/glm_input_files)|Apache-2.0_repository; separate_data_specific_grant_not_verified。Do not silently MIT-license copied Apache source. If included under repository Apache grant, retain Apache license and any applicable notices/changes; numeric-table default allowlist omits this family pending parent scope decision.|
|`rayshubskiy-code`|[Wilson Lab secondary analysis code](https://github.com/wilson-lab/rayshubskiy_elife_102230_secondary_analysis_code/tree/7e2895349266b5cc5fa1bf53ad56e8ecc6c842e8)|MIT。|
|`muscle-atlas`|[Azevedo et al. (2024), motor system muscle atlas](https://doi.org/10.1038/s41586-024-07389-x) / [data](https://faculty.washington.edu/tuthill/docs/azevedo24_appendix.pdf)|引用と独自の事実整理。Literature-backed anatomical mappings, with original curation; no article PDF or figure copy distributed. Different specimens remain separate.|

## 生理・介入の文献

|対応キー|一次資料|
|---|---|
|Rayshubskiy2025|[原資料](https://doi.org/10.7554/eLife.102230.3)|
|Yang2024|[原資料](https://doi.org/10.1016/j.cell.2024.08.033)|
|Feng2020|[原資料](https://doi.org/10.1038/s41467-020-19936-x)|
|Sapkal2024|[原資料](https://doi.org/10.1038/s41586-024-07854-7)|
|Dallmann2025|[原資料](https://doi.org/10.1038/s41586-025-09554-2)|
|Syed|[原資料](https://elifesciences.org/articles/106446)|
|Cheong2026|[原資料](https://doi.org/10.7554/eLife.96084.3)|

## 全身の筋対応表で使う資料キー

表中の短い資料キーは下表へ対応する。未査読・未読部分・型への橋渡しに関する留保は、元の取得範囲に従う。今回全論文を再取得したという意味ではない。

|キー|一次資料|利用範囲|
|---|---|---|
|GOR24|Gorko et al. 2024, [Motor neurons generate pose-targeted movements via proprioceptive sculpting](https://doi.org/10.1038/s41586-024-07222-5)|Fig1–4、本文・Methods、ED7。単一頸MN刺激/記録、初期姿勢、LNC介入、筋表|
|AZE24|Azevedo et al. 2024, [Connectomic reconstruction of a female Drosophila ventral nerve cord](https://doi.org/10.1038/s41586-024-07389-x)|Fig4、ED5、wingMN identification Methods。翼筋とTTMの分離、筋線維/MN対応|
|MANC|Cheong et al. 2026, [Organization of circuits linking descending input to motor output in the Drosophila Male Adult Nerve Cord connectome](https://doi.org/10.7554/eLife.96084.3)|Fig6、Introduction、MN identification Methods。wing/haltere/neckの筋対応と未同定範囲|
|EHR23|Ehrhardt et al. 2023, [Single-cell type analysis of wing premotor circuits in the ventral nerve cord of Drosophila melanogaster](https://pmc.ncbi.nlm.nih.gov/articles/PMC10312520/)|筋染色・splitGAL4/MCFOによるwing/haltereMN同定の記述 使用版は2023年preprint。|
|WHI22|Whitehead et al. 2022, [Neuromuscular embodiment of feedback control elements in Drosophila flight](https://doi.org/10.1126/sciadv.abo7461)|Fig1–4・Methods。自由飛翔pitch外乱、b1/b2介入、PI模型|
|HUR23|Hürkey et al. 2023, [Gap junctions desynchronize a neural circuit to stabilize insect flight](https://doi.org/10.1038/s41586-023-06099-0)|Fig1–4・記録/遺伝操作/模型の本文Methods。DLM5MNの電気的結合と発火分散|
|DIC19|Dickerson et al. 2019, [Flies regulate wing motion via active control of a dual-function gyroscope](https://doi.org/10.1016/j.cub.2019.08.065)|Fig1–4・Methods。平均棍筋/感覚Ca、MN群操作、翼筋電図|
|NAM22|Namiki et al. 2022, [A population of descending neurons that regulate the flight motor of Drosophila](https://doi.org/10.1016/j.cub.2022.01.008)|DNg02集団光刺激・細胞数・翼拍振幅、視覚刺激中の機能撮像|
|ACH19|Ache et al. 2019, [State-dependent decoupling of sensory and motor circuits underlies behavioral flexibility in Drosophila](https://doi.org/10.1038/s41593-019-0413-4)|Fig1–6・状態依存記録/光刺激/抑制Methods。DNp07/10着陸の脚伸展|
|SUV23|Suver et al. 2023, [Active antennal movements in Drosophila can tune wind encoding](https://doi.org/10.1016/j.cub.2023.01.020)|Fig1–4・Methods。能動/受動関節、筋1/4MN群と筋3直接操作、風姿勢/flick|
|OZD26|Özdil et al. 2026, [Centralized brain networks controlling antennal grooming coordination](https://doi.org/10.1038/s41467-026-72152-x)|頭・触角・前脚の拘束/切除/神経操作、aMNとheadpitchMNを出力にするFlyWire模型Methods|
|MCK20|McKellar et al. 2020, [Controlling motor neurons of every muscle for fly proboscis reaching](https://doi.org/10.7554/eLife.54978)|Table1、Fig6–9、筋・MN同定と運動操作Methods|
|CUI24pre|Cui et al. 2024-09-03 v1, [A gut-brain-gut interoceptive circuit loop gates sugar ingestion in Drosophila](https://doi.org/10.1101/2024.09.02.610892)|Fig5–6・Methods。Gr43a→IN1→CEM、嗉嚢入口への糖液流入をCEM操作で変える 未査読版として扱う。|
|GUS26|2026 Cell, [The complete gustatory connectome of adult Drosophila reveals how taste guides feeding, foraging, and social behavior](https://www.sciencedirect.com/science/article/pii/S0092867426009438)|web索引が返したFig6 feeding motor出力部。CEM分離、新MN2Db/MN4b、MNx01–05、MN12V対応欠測 検索索引で得た出力部分のみ。全文未読。|
|FEN22|Fenk et al. 2022, [Muscles that move the retina augment compound eye vision in Drosophila](https://doi.org/10.1038/s41586-022-05317-5)|Fig1・4、Methods/ED10。MOT/MOSと網膜MN操作・gap crossing 個々のMaleCNS rm型への筋対応は未検証。|
|BANC26|2026, [Distributed control circuits across a brain-and-cord connectome](https://doi.org/10.1038/s41586-026-10735-w)|Fig3–5、effector typing・静的影響計算Methods。頭部感覚、眼/触角/頸/翅の共有出力、末梢標的の欠測|
|EIC25|2025, [Comparative connectomics of Drosophila descending and ascending neurons](https://doi.org/10.1038/s41586-025-08925-z)|異なるEM標本間の型照合という方法文脈|

## 資料と結果を引用する

研究成果を利用する場合は、成果集の版と該当する原論文・データセットの版を併記する。元表のセル・図番号がある場合は保持する。原データの再配布許可、論文本文の利用条件、模型コードの利用条件はそれぞれ独立して扱う。

[データの加工履歴](../data/provenance.json)には各公開表の元研究ファイルとSHA-256を残した。これは出所の識別情報で、未同梱の私的ファイルを読者が持つことを前提にした実行手順ではない。
