# 正規化回路入力

各集合は `set_manifest.json`、`nodes.json`、`edges.csv.gz`、`sources.json` を持つ。公開版は元データのID・注釈・三重み・出所を保持した静的な入力である。

`set_manifest.json` の `schema_version` は `circuit-source-set/v1`。`dataset`、`snapshot`（`uuid/tag/latestMutationId`）、十進文字列の原 `selected_ids`、3ファイル名、取得範囲 `coverage`、留保 `notes` を持つ。`coverage` の internal / incoming / outgoing は `{status,basis}` で、status は `complete_incident_query`、`complete_induced`、`partial`、`not_acquired`。取得時の記録であり、公開時に原照会を再実行した証拠ではない。

`nodes.json` は原注釈の配列。最低限 `bodyId`、`type`、`is_neuron` を持つ。選択細胞の注釈を収め、辺に現れる未注釈の境界端点は読込時に未同定のノードとして保持する。型名、筋名、ラベルで同一性を決めない。

`edges.csv.gz` の列は `bodyId_pre,bodyId_post,weight,weightHP,weightHR,pre_is_neuron,post_is_neuron,source_ids`。有向化学 `ConnectsTo` 集計で、選択集合の少なくとも片端に接する一意な端点組を保持する。weightは非負整数、HP/HRの未取得は空欄。真偽値はtrue/false、未取得は空欄。自己辺は保持する。`source_ids` はJSON文字列配列で `sources.json` へ解決する。同じ内部辺の入出力照会に三重みの不一致があれば一つへ丸めない。

`sources.json` は `{id,path,sha256,size_bytes,role,availability,path_basis}` の配列。公開版の `availability` は `archival_not_shipped`、`path_basis` は `original_research_root`。`path` は原研究アーカイブからの相対参照で、checkout内のファイル参照ではない。元の5欄を保持し、辺の出所摘要文字列を変えない。原資料のhashを記録することと、原資料の実在や内容を今回検証することは別である。

公開用の `publication` 拡張は `schema_version: circuit-published-inputs/v1`、`archival_sources_verified: false`、`files` を持つ。`files` は同梱するnodes/edges/sourcesの各ローカルファイル名から `{sha256,size_bytes}` への完全な対応表。`verify-inputs` は3ファイルすべての大きさとSHA-256を検査し、出所ID重複と非同梱宣言を検査する。辺・ノードの構造的妥当性は `inspect` が検査する。全ファイルの公開目録とmanifest自体のhashは [PUBLICATION.json](PUBLICATION.json) に置き、`verify_publication.py` が検査する。

この拡張を持たない従来入力の `verify-inputs` は、操作エンジンの一つ上のディレクトリを原資料rootとし、各sourceの大きさと摘要を検査する。公開5集合はその動作に依存しない。原取得の再照会・元応答からの正規化は配布対象外である。
