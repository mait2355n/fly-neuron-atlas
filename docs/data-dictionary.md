# データ辞書

CSVはUTF-8、ヘッダ付き。`.csv.gz`はgzip圧縮した同形式。各表の正確な列名と行数は[provenance.json](../data/provenance.json)の`columns`・`rows`にある。数値計算へ読み込む場合も、細胞番号は文字列として扱う。

## 共通の識別と量

|欄|意味|
|---|---|
|`dataset`|接続・注釈のデータセット版。省略された接続表はsnapshot.jsonのmale-cns:v1.0|
|`bodyId`, `bodyId_pre`, `bodyId_post`|再構成標本内の識別子。preは入力元、postは入力先|
|`entity_id`|`dataset:bodyId`という名前空間付き識別子|
|`ref`, `compact_ref`|表示名と識別子の略記。末尾の`・`より右を識別子として読む。型名だけで同一性を判断しない|
|`type`, `preType`, `postType`|型の注釈。空欄は不明・未付与で、型が存在しないという意味ではない|
|`weight`|配布元の化学シナプス接続weight。今回の閾値に使用|
|`weightHP`, `weightHR`|配布元の高精度/高再現率側weight。weightと混ぜて加算しない|
|`preIsNeuron`, `postIsNeuron`|Neuronラベルの有無。FalseのSegmentを同定済み細胞と数えない|
|`somaSide`, `somaNeuromere`|細胞体の側・胸節の注釈。筋作用の側を独立に確認した情報ではない|
|`predictedNt`, `prePredictedNt`, `preConsensusNt`|伝達物質の予測/合意注釈。受容体を含む実際の作用符号の証明ではない|

bodyIdの略記にデータセット名が含まれない既存列は、同じ行の`dataset`またはsnapshotと合わせて読む。`candidate_ref`に相当する型・標本間の対応を、確認済みの同一細胞参照へ昇格させない。provenanceの`derived_from`は派生元を表し、同一内容・同一実体を表さない。

## 表ごとの使い道

|表|主キー・粒度|用途と境界|
|---|---|---|
|[motor_atlas](../data/motor_atlas.csv)|bodyId、815行|筋作用の根拠・欠測・各細胞の入力分母。`evidence_table`はrepo root相対パス|
|[motor_inputs](../data/connectivity/motor_inputs.csv.gz)|pre/post対、330,888行|815 MNへの直接入力全件。重複のない取得辺|
|[motor_groups](../data/motor_groups.csv)|bodyId、166行|42群所属、筋対応の根拠。群名は機能証明ではない|
|[shared_candidates](../data/shared_candidates.csv)|bodyId、2,155行|閾値10の候補。`target_group_ids`は`\|`区切り。群対や理由の配列欄はJSON文字列|
|[studied_cells](../data/studied_cells.csv)|bodyId、40行|全入出力取得済み集合。初回6と追加34を含む|
|[studied_totals](../data/studied_totals.csv)|direction/target/threshold、320行|40細胞×入出力×4閾値の分母。同じ辺を閾値間で繰返し含む|
|[studied_incoming](../data/connectivity/studied_incoming.csv.gz)、[studied_outgoing](../data/connectivity/studied_outgoing.csv.gz)|pre/post対|前者は40細胞が入力先、後者は40細胞が入力元。未観測端点間の辺は未知|
|[annotation_sensitivity](../data/annotation_sensitivity.csv)|bodyId、2,155行|44 MN除外前後の群別weight、共有資格の残存。群別辞書はJSON文字列|
|[physiology_evidence](../data/physiology_evidence.csv)|bodyId、23行|16型の精読台帳。型の相関・十分性・必要性・性別・系統・未同定を別欄に保持|
|[right_t2_six_candidates](../data/right_t2_six_candidates.csv)|bodyId、6行|右中脚13A候補。共有探索の初回6とは別集合|
|[functional_partition](../data/functional_partition.csv)|集計群|外部上流・MN・相互入力の分母。百分率は生理寄与率ではない|

共有分類は`leg_and_nonleg`、`multiple_legs`、`same_leg_knee_root`、`same_leg_same_joint`、`nonleg_only`を、元解析の分類優先順で一つずつ付けたもの。別の関係欄では一つの候補が複数の関係を持ち得る。分類件数と全群対の件数を同じ分母にしない。

## 活動表

|表・欄|意味|
|---|---|
|`inventory.csv`の`fly`|著者の記録ラベル。独立した物理的個体の一意性を保証しない|
|`available_ephys_s` / `analyzed_s` / `valid_no_stim_s`|配布電位時間 / 共通100Hz時間軸 / 刺激・境界等を除いた技術採用時間|
|`channels.csv`|記録×電位チャンネル。33行。型、側、検出数、推定Hz、相関、品質注記|
|`pairs.csv`|同時計測10記録×3比較系列=30行。30独立個体ではない|
|`A_minus_B` / `A_plus_B`|同型双側なら左−右 / 左＋右。同側異型ならDNa02左とDNa01左の差/和|
|`r150`|神経系列(t)と対象系列(t+150ms)のPearson相関|
|`shift1_r150` / `shift2_r150`|記録長のおよそ1/3、2/3だけずらした対照。無作為化試験やp値ではない|
|`main_summary_eligible`|主集計への採用フラグ。低SNR記録はFalseでも表から除かない|
|`voltage_sensitivity.csv`|Vm近似≤−33mVの探索的感度。著者の品質除外手順の再現ではない|

空欄・`nan`・不明の文字列を0へ置換しない。生物学的標本数を時間点数から作らない。全列の算出法は[再計算方法](reproducing.md)と[活動の留保](limitations.md)を参照する。
