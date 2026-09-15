# Fly Neuron Atlas

ハエの神経接続・活動・身体作用を、根拠の種類を分けて調べた研究記録。2026年9月15日までの16研究束を整理した、再利用可能な成果集である。

[English overview](README.en.md) · [完了範囲](docs/coverage.md) · [研究成果](docs/findings-body-and-activity.md) · [再計算](docs/reproducing.md) · [データ辞書](docs/data-dictionary.md) · [出典](docs/sources.md)

2026年9月15日の実装修正：欠測・系列不足・表間不整合の検出と、時計区間ごとの独立処理を追加した。原電位23記録を再実行し、DNa02双側の主3記録は従来値と一致した。時計リセット2記録の変化、修正版の基礎表と追補解析は[修正内容と検証範囲](docs/audit-remediation.md)にある。`data/activity`は公開時の保存基線、`data/reanalysis`は版を分けた再解析結果である。

## 何が完了したか

|対象|完了した範囲|直接使えるもの|
|---|---|---|
|全身の運動出力|MaleCNS v1.0の運動ニューロン815個を目録化。全直接入力330,888辺、weight合計3,224,310を取得|[815個の統合表](data/motor_atlas.csv)、[入力辺](data/connectivity/motor_inputs.csv.gz)|
|共有する上流|166運動ニューロン・42筋群に対し、辺weight≥10で二群以上へ接続する2,155候補を分類|[全候補](data/shared_candidates.csv)、[筋群所属](data/motor_groups.csv)|
|個別の接続探索|共有候補40細胞の全直接入力39,909辺・全直接出力323,398辺を取得|[40細胞](data/studied_cells.csv)、[入出力分母](data/studied_totals.csv)|
|自然活動の再解析|公開DNa01/DNa02膜電位23記録・33チャンネル、配布時間53,855秒を処理|[記録目録](data/activity/inventory.csv)、[左右差・和の相関](data/activity/pairs.csv)|
|航法・経験更新|現在方位と目標の分離、PFL3の非線形読出し、匂い学習・反転の応答更新を、公開資料から比較・再計算|[航法と経験更新の成果](docs/findings-navigation-and-learning.md)|
|根拠の訂正|筋対応の競合、欠測、別標本・別型・閾値依存を明示し、共有候補の感度分析を実施|[注釈感度](data/annotation_sensitivity.csv)、[訂正と未解決](docs/limitations.md)|

815個全ての動作や発火が解明されたという意味ではない。接続図の個体、実験で記録した個体、文献の型対応を分ける。筋作用に名前が付いていても、そのMaleCNS細胞の活動が測定されたことにはならない。

## 手元で使う

Python 3.10以降で、追加の依存や認証なしに実行できる。

```sh
python scripts/verify.py
python scripts/reproduce.py
```

最初はファイルのハッシュ・表の形・参照を検査する。次は収録した辺から各運動ニューロンの入力、共有候補の番号集合、注釈除外の影響、40細胞の入出力を再集計する。JSONを標準出力へ返し、一致なら終了符号0、不一致なら1。生物学的機能の保証を返す検査ではない。

細胞番号から探す例：

```python
import csv
with open('data/studied_cells.csv', encoding='utf-8', newline='') as f:
    cell = next(r for r in csv.DictReader(f) if r['bodyId'] == '800687')
print(cell['preType'], cell['target_group_ids'], cell['full_io_state'])
```

公開膜電位からの発火再抽出も別手順で実行できる。原MAT計約5.51GBは配布元から取得する方式で、リポジトリには含まない。[原電位の再解析手順](docs/reproducing.md)

## 結果を読む際の境界

- `bodyId`は`male-cns:v1.0`内の識別子。異なるデータセットの番号、同じ型名、左右や胸節の類似を、同じ細胞の根拠にしない。
- `weight`は保存された化学シナプス接続の重み。発火率、作用符号、筋力、行動への寄与率ではない。
- 2,155は指定42群と辺閾値10の下での候補数。全神経系の共有細胞総数ではない。残る2,115候補の全入出力は未取得。
- 膜電位の技術的採用時間51,816.18秒は、生理品質を保証した時間ではない。発火は検出推定値で、著者が正解付けした時刻ではない。
- 特定の局所候補が未知条件でいつ活動し、経験で何を更新するかは未測定。全脳模型、自然歩行の再現、汎用学習能力は実証していない。

## 構成と引用

`docs/`は読み方と成果、`data/`は選定表と圧縮辺、`scripts/`は検査・再集計・任意の膜電位再解析。各表の元研究束、原ファイルSHA-256、公開時の変換、出典は[provenance.json](data/provenance.json)にある。原論文全文、認証情報、制作会話、第三者の身体模型・動画素材は含めていない。

独自コードは[MIT](LICENSE)、独自解説と整理表への独自寄与は[CC BY 4.0](LICENSE-DATA.md)。元データと借用アルゴリズムの条件は[第三者表示](THIRD_PARTY_NOTICES.md)を参照。利用時はこの成果集に加え、該当する原論文・データセットも引用する。[引用情報](CITATION.cff)
