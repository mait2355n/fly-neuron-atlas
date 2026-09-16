# 構造操作の局所仕様

標準Pythonの `circuit_ops.py` で操作する。これは静的有向グラフの操作で、ニューロン活動・筋・学習のシミュレータではない。配布する正規化入力と生成グラフを扱うCLIである。

Graphはsnapshot（dataset,uuid,tag,latestMutationId）と、nodes辞書、edges辞書、coverageを持つ。nodesのキーはmale-cns:v1.0:<bodyId>。人工複製はclone:<UUID>としてderived_fromへ原entity_idを記録する。nodesの値はJSON可能な原注釈とbodyId/is_neuron/ref/derived_from等。ラベル・型を結合キーにしない。edgesのキーは(pre_entity_id,post_entity_id)、値は{weight,weightHP,weightHR,source_refs}。source_refsは原ファイルpath+sha256に解決済みの文字列配列である。公開5集合では非同梱の原研究アーカイブへの来歴であり、checkout内のファイル参照ではない。

load_source(path) -> Graph。pathはset_manifest.json。版・選択ID・辺重複・3重み・source_ids参照・端点標識を検証し、selected_idsと切出し可能範囲を保持する。未知のHP/HRはnull。公開入力のverify-inputsは同梱nodes/edges/sourcesの摘要を照合し、原取得の検証は行わない。詳細は [INPUT_CONTRACT.md](INPUT_CONTRACT.md)。

cut(graph, selected_entity_ids) -> {inside:Graph, boundary:Graph, selected_ids:[...], original_selected_ids:[...], original_coverage:{...}, original_fingerprint:str, snapshot:{...}}。insideは両端が選択内、boundaryはそれ以外の辺を保持する（cut対象外同士が元にあればそれも失わない）。内部と境界は辺が排他的で、和集合が原構造になる。元の選択IDとcoverageはreconnectでの復元に用いる。境界Graphのnodesは元の全nodesを保持し、孤立選択細胞も失わない。境界には方向分類を別に出せる。

merge(graphs) -> Graph。同版の同一entity_idを一つにし、同じ辺は3重み・原注釈が一致する時だけsource_refsを和集合にする。版違い、同一IDの注釈競合、同一辺の重み競合はValueError。共通ラベルの別IDは別ノードのまま。

reconnect(cut_record) -> Graph。insideとboundaryをmergeし、元fingerprintとの一致を要求する。切断前の構造摘要は選択ID・coverage・全node属性・辺端点/3重み/source_refsを含む。取得不完全という事実も保持し、不完全な元構造の復元を完全生体網の復元と呼ばない。

clone_node(graph, entity_id, clone_tag) -> (Graph,changes)。元nodeと辺を残し、そのnodeの完全なincident近傍をもう一組作る。自己辺はclone→cloneとする。UUID5は原ID/snapshot/clone_tagから決定し、同じtagの二度適用は拒否。複製は元の同じ細胞というrefへせずderived_fromにする。これは人工改変である。

drop_edges(graph, predicate) -> (Graph,changes)、swap_targets(graph, edge_key1, edge_key2) -> (Graph,changes)。削除・追加した辺をchangesへ残す。理由は呼出側が付加し、demoでは閾値と終点交換の理由を保存する。変更前後の構造摘要はdemoのRESULT.jsonに残る。swapは4つの異なる端点で、既存辺との衝突を拒否する。辺のweightは元preに付随したまま移すため、post側の加重入力総量を保つとは主張しない。

fingerprint(graph) -> str。JSON可能な内容を安定順にしてSHA256（ラベルも含む完全な静的内容の同一性証拠）。内容hashそのものを生物学的identityにしない。

write_graph(graph,outdir)とread_graph(outdir)はJSONのgraph.json（版・node・coverage）とedges.csv.gzを保存/再読し、manifestの内容摘要を検証する。保存されたgraph.json/edges.csv.gzは同じディレクトリから読むため、保存先を別の場所へコピーして再読できる。注釈やcoverage中の原資料参照の解決可能性までは検証しない。graph/edge原本に上書きする操作はない。

保存版はgraph.jsonのschema_versionがcircuit-graph/v1、manifest.jsonがcircuit-export/v1、demoのRESULT.jsonがcircuit-demo/v1。graph.jsonのsnapshot/nodes/coverageはobject、selected_idsはstring配列。manifest.jsonのfingerprintはSHA-256文字列、filesはgraph.jsonとedges.csv.gzの名前からSHA-256へのobject。辺表のbodyId_pre/bodyId_postはentity_id文字列、weightは非負整数、weightHP/weightHRは非負整数または未取得を表す空欄、source_refsはJSON文字列配列である。読取時は保存版・二ファイル摘要・構造摘要を検査する。

CLI（circuits内から）: python3 circuit_ops.py inspect MANIFEST / verify-inputs MANIFEST / demo MANIFEST --out DIRECTORY / verify-graph DIRECTORY。成功stdoutはJSON {status:"ok",result:{...}}、入力不備はstderrへJSON {status:"error",error:{type,message}}でexit2。成功exit0、内部不具合exit1。demoは既存outを上書きせず、内部/境界/再接続、閾値10、共有nodeの人工複製、可能なら2辺の終点交換を実データで実行し、差分と比較表を保存する。

このCLIのエラーはPython例外のtypeとmessageを持つ。SDK向けの独立したerror_code/details/hintは定義しない。--helpは通常の説明文である。demoの開始/終了時刻はUTCのISO 8601文字列。snapshotは生物資料の版であり実験時刻ではない。人工改変はbiological_function_verified:false、未測定項目はRESULT.jsonのunmeasuredに残す。動態・符号・更新則の推測は今回の実辺データに書き込まない。

独立検査は、小さい有向・自己辺・孤立node・共有nodeを含むfixtureで正常な保存/切断/再接続/共有統合を確認する。辺欠落、重み改変、版混合、同名別IDの統合、人工複製の同一視、壊れた保存ファイル、同じtagの再複製を検出する。公開入力ではPUBLICATION.jsonに保持した元の構造摘要と、verify_publication.pyの独立CSV集計を照合する。原取得応答は同梱しないため再検証対象外である。
