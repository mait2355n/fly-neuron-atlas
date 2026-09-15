# 完了範囲と公開内容

2026年9月15日までの16研究束を対象にする。「完了」は下表の調査・取得・計算を終えた範囲を表す。生体機能の確定、学術的新規性の認定、全脳の分解完了という意味ではない。

|研究束の識別名|完了した範囲|この公開版での利用|
|---|---|---|
|`malecns_research_20260914`|航法と結果更新の候補比較、限定配線、公開式6,498条件の計算|[航法章](findings-navigation-and-learning.md)に結果と模型の条件|
|`malecns_mechanisms_20260914`|活動証拠の整理、PFL3 15細胞・396区画、限定型対応|後続の訂正を反映して航法・学習章へ統合|
|`malecns_mechanisms_followup_20260914`|Huang全96記録、反転資料、模型128訓練・160評価、物体操作比較|訂正版の数値と別個体・模型の留保|
|`malecns_discrepancy_resolution_20260914`|Huang公表96値、McCurdy452比較、物体操作の処理定義差の照合|[訂正JSON](../data/learning/huang_corrected_summary.json)、[未復元の原記録](limitations.md)|
|`malecns_activity_mechanisms_20260914`|430視覚跳躍、PFL3予測比較、反転113個体行、更新先・欠測の対比|航法2表、結果の条件と負の結果。全原H5は未同梱|
|`malecns_action_grounding_20260914`|作用・停止・試行の整理、PFL3介入比較、静的経路の集計|[介入個体平均](../data/action/pfl3_intervention_fly_means.csv)、動作解釈|
|`malecns_joint_grounding_20260914`|六脚381MN索引、右中脚の具体筋・5MNと入力3,292辺の対応|後続の全身表・[右中脚作用軸](../data/structure/right_t2_axis_map.csv)へ統合|
|`malecns_joint_control_20260914`|右T2全58MNの入力22,960辺、候補型照合、関節介入の再集計|[右T2六候補](../data/right_t2_six_candidates.csv)、相互接続・Agrawal介入表|
|`malecns_activity_update_20260914`|六候補の全入力4,592辺、別型Ca・同期関節、身体変化後の行動、観測条件の具体化|別型Ca要約と未測定項目。NC由来行データと許諾範囲未確定の同期データは未同梱|
|`malecns_research_summary_20260914`|初期9束の訂正込み索引、同版の六候補構造表|今回の統合へ継承。追加の生理測定とは数えない|
|`malecns_functional_partition_20260915`|選択・調整・協調の候補分け、六候補と58MN上流の重複、chief9A型対応|[機能分割集計](../data/functional_partition.csv)、器官相同との区別|
|`malecns_bodywide_control_20260915`|815 MN目録と全入力、脚・翅・頸部・摂食等の筋対応と欠測|815行、全入力辺、381脚作用、434非脚根拠、部位間共有|
|`malecns_mapping_video_20260915`|神経形状と身体模型の説明映像、21細胞・82.6秒|完成範囲と表示の限界を記載。媒体・身体模型は未同梱|
|`malecns_mapping_video_20260915_v2`|六脚へ拡張した166細胞・30場面・240.2秒の映像|[可視化の範囲](findings-body-and-activity.md)。筋計算は左前脚の限定比較|
|`malecns_shared_control_20260915`|166 MN/42群の共有条件、初回6細胞の入出力、筋注釈感度|群所属と閾値別候補を収録。初回6は右T2の13A六候補とは別|
|`malecns_shared_roles_20260915`|2,155候補分類、40細胞の入出力、型の実験証拠、23電位記録の全長再解析|全候補・40細胞全辺・生理台帳・活動表・原電位再解析脚本|

## 公開時に改めて検証したこと

選定データを新しい構成へ移し、各表の出所とハッシュを[provenance](../data/provenance.json)へ記録した。元の研究束に対する訂正は公開解説へ反映し、履歴を上書きしていない。

構造は全815 MN入力から候補集合と感度条件を再集計した。膜電位は23記録を公開脚本で全長再解析し、保存された基礎解析4表に一致した。[原電位の数値照合](../data/ephys_validation.json)

前半の航法・学習・関節作用は保存済み派生値を再集計・照合したが、全原H5・MAT・RDataから全解析をやり直したものではない。動画の再描画・全編復号、全一次論文の新規精読、筋の末梢追跡、対象細胞の新しい生理実験も今回の公開検証には含めない。
