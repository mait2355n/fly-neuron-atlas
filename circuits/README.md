# 実神経回路の切出し・再接続

MaleCNS の5集合を、元の神経ID・有向辺・三種のシナプス集計・出所・外部境界を保って扱う。切出し、再接続、人工複製、結線変更を、Python 3.10以降の標準ライブラリだけで実行できる。

同じ経験を知覚・評価・思考・発話・即応・行動へ継続して使う人工主体に向け、実回路を構成候補として比較するための静的な操作基盤である。発火、筋運動、学習、人工主体の性能改善は測っていない。

## 同梱する5集合

|集合|選択細胞|内部辺|外部からの入力辺|外部への出力辺|
|---|---:|---:|---:|---:|
|[右T2・13A六候補](inputs/motor/six13a/set_manifest.json)|6|23|4,569|29,858|
|[制御候補41細胞](inputs/motor/control41/set_manifest.json)|41|242|39,947|324,328|
|[EPG・EL・選択ER型](inputs/learning/heading_epg_el_er/set_manifest.json)|131|13,267|30,328|90,905|
|[方位・目標・操舵の初期A](inputs/learning/initial_a/set_manifest.json)|220|7,981|63,444|338,606|
|[結果更新候補の初期B](inputs/learning/initial_b/set_manifest.json)|1,829|261,920|91,969|312,664|

`control41` は従来の制御候補40細胞に chief を含めた集合。`six13a` は右T2・13Aの六候補で、以前の共有入力解析に登場する「六細胞」という別集合と同一視しない。集合間には共有神経があるため、選択数の単純合計は固有細胞数ではない。共有を保った和集合を作る場合、原IDと注釈の表現差を別に扱う必要がある。ここには5集合をまとめる組立専用処理や過去の組立結果は同梱していない。

データ版は `male-cns:v1.0`、UUID `4b2087c0fbe046bfaf0d60bc970e3e5d`、tag `v1.0`、mutation `1006591300`。各入力の `coverage` は元の取得範囲の記録であり、最新データの状態や生体全体の完全性を示さない。

## 検証と実行

以下はリポジトリ直下で実行する。通信、認証、GPU、追加ライブラリは不要。

```sh
python3 circuits/tests/test_circuit_ops.py
python3 -m unittest discover -s circuits/tests -p test_publication.py -v
python3 circuits/verify_publication.py
python3 circuits/analyze_topology.py --output .local/circuit-publication/topology.json
```

最初のコマンドは手書きの小さな有向グラフを使う29試験で、正常操作と22件の不良条件を確かめる。次の8試験は、公開入力の破損・摘要欠落・来歴の誤表示・移設を検査する。試験用出力は `.local/circuit-publication/` または自動消去される一時フォルダに作る。

`verify_publication.py` は全5集合について、公開ファイルのSHA-256と大きさ、`verify-inputs`、`inspect`、元の構造摘要を検査する。さらに操作エンジンを呼ばないCSV集計で、ノード数・選択数・方向別辺数・weight総和を照合する。`analyze_topology.py` は別実装の強連結成分計算で、内部辺のweight閾値1・3・5・10に対する構造変化をJSONへ出す。到達可能性を活動・安定性・計算能力とは解釈しない。

一集合の検査と操作例:

```sh
python3 circuits/circuit_ops.py verify-inputs circuits/inputs/motor/six13a/set_manifest.json
python3 circuits/circuit_ops.py inspect circuits/inputs/motor/six13a/set_manifest.json
python3 circuits/circuit_ops.py demo circuits/inputs/motor/six13a/set_manifest.json --out .local/circuit-publication/six13a-demo
python3 circuits/circuit_ops.py verify-graph .local/circuit-publication/six13a-demo/reconnected
```

`demo` は既存の出力先を拒否する。再実行時は新しいディレクトリ名を指定する。内部・境界・再接続・内部weight10閾値・共有入力元の人工複製・可能な二辺終点交換を保存し、`RESULT.json` と `*_changes.json` に変更前後の摘要と理由を残す。入力辺と選択ノードの配列は書き換えない。大きい集合のdemoは各条件を保存するため、入力ファイルより多くのメモリと空き容量を使う。

## 再現できる範囲

`nodes.json` と `edges.csv.gz` は凍結束からバイト単位で保持した。`sources.json` は元の `id/path/sha256/size_bytes/role` を保持し、各記録に非同梱の明示を追加した。`set_manifest.json` には同梱3ファイルの摘要を追加した。変換前後のSHA-256、元の構造摘要、同梱ファイル目録は [PUBLICATION.json](PUBLICATION.json) にある。元の出所文字列・ノード注釈・取得範囲を構造摘要へ含めるため、全5集合で元版との内容一致を検査できる。

`sources.json` の経路と保存グラフの `source_refs` は、原研究アーカイブ内の資料を示す来歴文字列である。このcheckoutから開ける経路とは扱わない。取得時の要求・応答・注釈根拠は同梱しておらず、原照会の再実行や原応答からの正規化は、この配布だけでは再現できない。

公開入力の `verify-inputs` は同梱正規化ファイルを検査し、`sources_checked: 0`、`archival_sources_verified: false` を返す。`verify-graph` は保存された二ファイルの摘要と復号後の構造摘要を検査する。来歴参照先の存在や生物学的根拠まで再検証するコマンドではない。ローカル原資料を持つ従来形式の入力では、`verify-inputs` が元資料の大きさと摘要を検査する経路も残している。

未取得のweightHP/weightHRは空欄から `null` として保持する。Neuron標識なしSegmentを同定済みの神経へ昇格させず、weightを符号・利得・遅延・学習則へ読み替えない。外部相手どうしの全結線、感覚帰還、時系列活動、生理機能はこの静的入力だけでは定まらない。

入力は [INPUT_CONTRACT.md](INPUT_CONTRACT.md)、操作とCLIは [ENGINE_CONTRACT.md](ENGINE_CONTRACT.md) を参照。独自コードは [MIT](../LICENSE)、独自説明文は [CC BY 4.0](../LICENSE-DATA.md)、MaleCNS由来データの帰属と条件は [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) に従う。
