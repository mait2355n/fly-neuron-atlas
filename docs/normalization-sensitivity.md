# 正規化方式の限定感度比較

対象を DNa02 双側記録 `a2_d_08`、`a2_d_12`、`a2_d_13` に固定し、雑音幅を見積もる方式への感度を調べる。原方式を保存し、相関が高い方式を採用する選択は行わない。3記録での感度であり、母集団・未試験の方式・生物学的な峰検出精度には一般化しない。

## 方式と固定条件

両方式とも、元の時刻が巻き戻る区間ごとに、120秒・30秒の区分 detrend を各0.5の重みで平均し、原式の `buttord(wp=100, ws=.05, gpass=3, gstop=30, fs=fs)`、`butter(..., btype='high')`、`filtfilt` を使う。これらの濾波入力・係数・出力の一致を小試験で確認する。

| 方式 | 中央値と雑音幅の推定 | 標本列への補間 |
| --- | --- | --- |
| `source_reshape_mad` | 原式の C 順序 `reshape(fs, -1)`、3つの循環移動、中央値と MAD を保持 | 原式の `signal.resample` |
| `contiguous_half_second_mad` | 重ならない連続0.5秒窓ごとに中央値と `MAD × 1.4826` | 標本座標で各窓中心を線形補間。両端は直近中心の値を延長 |

MAD は窓内中央値からの絶対偏差の中央値。代替方式は正の有限 MAD を必要とし、零・非有限 MAD を別の定数で埋めない。MAD 以外の濾波まで異なっていた過去の `local_mad_diagnostic` は、この比較には使わない。

峰検出の高さ2.5、prominence 7.5、参照幅10秒、100 Hz の計数、標準偏差2.5 bin の rate 平滑化、刺激除外、有効標本、左右の向き、yaw 符号、150 ms の遅れは両方式で同じ。正規化、峰検出、平滑化、Vm、ISI、遅れ相関を元の時刻区間内で処理する。`A_minus_B` は左の rate − 右の rate で、yaw は元資料の符号を保つ。

## 追試

リポジトリの根で、Python 3.12 の新しい環境に固定依存を入れる。

```sh
python3.12 -m venv .venv-ephys
.venv-ephys/bin/python -m pip install -r requirements-ephys.txt
.venv-ephys/bin/python -m unittest discover -s tests -p 'test_normalization.py' -v
```

raw MAT は `data/activity/download_manifest.json` の指定ファイルを用意する。まだ無ければ、記録ごとに基礎再解析を実行すると、指定サイズと MD5 を照合した raw と receipt が保存される。各出力先は新しいディレクトリにする。

```sh
.venv-ephys/bin/python scripts/reanalyze_ephys.py --fly a2_d_08 --download --raw-dir .local/raw --output .local/download-check-a2_d_08
.venv-ephys/bin/python scripts/reanalyze_ephys.py --fly a2_d_12 --download --raw-dir .local/raw --output .local/download-check-a2_d_12
.venv-ephys/bin/python scripts/reanalyze_ephys.py --fly a2_d_13 --download --raw-dir .local/raw --output .local/download-check-a2_d_13
.venv-ephys/bin/python scripts/normalization_sensitivity.py --raw-dir .local/raw --output .local/normalization-v2 --reference .local/ephys-v2
```

`--reference` は補正済み原方式による完了済み基礎実行を指し、既定値を使う場合も照合必須。`RUN.json`、`channels.csv`、`pairs.csv` が無い、または処理未完なら参照照合を `not_verified` と記録し、総合結果は `fail`・終了符号1とする。先に `reanalyze_ephys.py` で参照先を作る。基礎実行は既存 raw の全23記録を対象とし、ここで方式比較をするのは指定3記録だけ。

方式比較のスクリプトは raw と receipt を変更しない。各方式の直前に raw のサイズ、MD5、SHA-256 を読む。MD5 とサイズを配布 manifest に照合し、両方式が同じ3ファイルを使ったことを `RUN.json` に記録する。進捗は標準誤出力、短い結果 JSON は標準出力。全6組の処理と入力一致が完了し、利用不能結果・参照不一致・実行失敗が無ければ終了符号0、その他は1、引数の誤りは2。

## 出力と解釈

- [channels.csv](../data/reanalysis/normalization-v2/channels.csv): 各方式の発火数、全解析時間・刺激除外後の平均 rate、yaw 相関、有効遅れ標本数と原方式からの差。
- [pairs.csv](../data/reanalysis/normalization-v2/pairs.csv): 左右 rate 間、左右差と yaw、左右和と yaw の相関と原方式からの差。
- 各方式の下位ディレクトリ: inventory、channel、pair、遅れ曲線、閾値感度の CSV、整列 NPZ、検出時刻 NPZ、固定波形図。
- [固定波形図](../data/reanalysis/normalization-v2/figures/a2_d_12_0.8-1.3s.png): 先に指定した0.8–1.3秒の左右原波形に、両方式の検出点を重ねた図。
- [RUN.json](../data/reanalysis/normalization-v2/RUN.json): 入力ハッシュ、設定、実行コードのハッシュ、依存版、原方式基礎結果との照合、エラー、計算時間。
- `local_context.json`: 実行機固有の絶対パスと呼出し。公開用成果物から分離した実行控え。

原方式の再計算値は、別に保存された補正済み基礎実行の CSV を読み直し、各対象記録の2 channel・3 pair系列のキーが過不足・重複なく揃うことと、数値が絶対許容差 `1e-12` で一致することを照合する。この一致は追試の整合性であり、正解ラベルによる精度評価ではない。

固定波形図は、どの峰を拾うかを人が点検するための代理評価。波形上の妥当性も人による正解ラベルでは未検証で、感度・特異度を示さない。相関の増減から方式の優劣や因果関係を決めず、模型較正も認定しない。

## 指定3記録の観測値

同じ入力と閾値で得た `A_minus_B` と yaw の150 ms相関は次の通り。差は代替方式 − 原方式。

| 記録 | 原方式 | 連続0.5秒 MAD | 差 |
| --- | ---: | ---: | ---: |
| `a2_d_08` | −0.379666 | −0.189329 | +0.190337 |
| `a2_d_12` | −0.711984 | −0.210217 | +0.501766 |
| `a2_d_13` | −0.295796 | −0.201618 | +0.094177 |

対象の3記録に含まれる6 channelでは、原方式から代替方式へ替えると検出数が減った。左右の検出数は、`a2_d_08` が 32,006 / 22,158 → 18,119 / 13,009、`a2_d_12` が 26,955 / 23,349 → 14,257 / 14,383、`a2_d_13` が 1,723 / 3,902 → 1,093 / 2,694。数値の全桁、rate と個別 channel 相関は比較 CSV を参照する。

この3記録では左右差相関の負符号は残り、その大きさは正規化方式で変わった。補正済み原方式の別実行との照合は、計6 channel と9 pair系列で一致した。固定波形例では左の検出数が両方式19、右が原方式6・代替方式7。全記録の検出数と、この短い例の検出数が逆方向に動くこともあるため、この例だけで全体の検出精度を推定しない。
