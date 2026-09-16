# 再計算と取得

9月16日の追加物は、[回路操作と5集合の入力](../circuits/README.md)、[経験・方位の同梱集計](../research/2026-09-16/README.md)に実行手順を分けた。以下の従来表の再集計と原電位解析も引き続き利用できる。

## 収録データだけで再集計する

リポジトリのルートから実行する。Python 3.10以降、標準ライブラリのみ。

```sh
python scripts/verify.py
python scripts/reproduce.py
```

両方ともファイルを書き換えない。検査結果のJSONは標準出力へ出し、一致は終了符号0、不一致は1。読取失敗・不正値・重複した細胞番号などで計算を続けられない場合は、`status: error`と`message`を含むJSONを標準誤出力へ出して1を返す。`verify.py`はSHA-256、bytes、CSVの行数と列、出典ID、ローカル文書リンクを検査する。`MANIFEST.json`自体とそのチェックサム一覧は相互再帰を避けるためmanifest対象外とする。

`reproduce.py`は次を収録辺から計算する。

1. 全815運動ニューロンの入力辺数・weight、および各細胞の表との一致。
2. 166 MN・42群、辺閾値1/3/5/10で共有候補を再抽出し、閾値10の全bodyId集合を照合。
3. 44 annotation-only MNを除外した群別weightと共有資格を全候補で再計算。
4. 40細胞の入出力を各閾値で集計し、別の分母表と照合。
5. 活動記録・チャンネルの対応と時間の合計を集計。

集計の前提となる行集合も検査する。調査40細胞は全候補表の取得済み細胞と全列を照合し、分母表は各細胞につき入力・出力の両方向と閾値1/3/5/10の各行が一度ずつあることを要求する。注釈感度表は全候補を一度ずつ含める。細胞番号の重複や行の欠落を、辞書への上書きや空集合の比較で見逃さない。

この欠落・重複検出は、収録データの一時コピーを変更して公開コマンドを実行する回帰試験でも確認できる。元の収録表は変更しない。

[照合結果と旧脚本での欠落見逃し](validation-notes.md)

```sh
python -m unittest discover -s tests -v
```

このコマンドは保存相関値を読む。原電位から相関を計算し直す工程は次節に分ける。共有分類の意味や生理機能、元の再構成・同定の正しさを検査が認定するわけではない。

## 原電位から再解析する

Harvard Dataverseの`10.7910/DVN/0NCLP1` v1.2から、`directoryLabel`に`/ephys_data_`を含む全23 MATを選定した。総量5,508,020,284 bytes。画像群は対象外。ファイルID・サイズ・MD5・URLは[download_manifest.json](../data/activity/download_manifest.json)にある。データはCC0、アルゴリズムの一部はWilson LabのMIT表示を保持する。

依存なしで取得予定を確認できる。

```sh
python scripts/reanalyze_ephys.py --list
python scripts/reanalyze_ephys.py --list --fly a2_d_08
```

解析には数値計算ライブラリが必要。保存時と公開検証ではPython 3.12、NumPy 2.3.5、SciPy 1.18.1、Matplotlib 3.11.2を使った。

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-ephys.txt
.venv/bin/python scripts/reanalyze_ephys.py --fly a2_d_08 --download \
  --raw-dir .local/raw --output .local/ephys-a2-d-08
```

`--fly`を省くと23記録を処理する。既に原MATがある場合は`--raw-dir`へその保存先を指定し、`--download`を省ける。ダウンロードは指定時だけ行い、既存ファイルもサイズとMD5を確認する。解析時に原データ横へ検証receiptを書き、指定出力先へCSV、整列NPZ、推定発火時刻NPZ、波形図、`RUN.json`を書く。出力先は新規または空のディレクトリを要求し、以前の結果を上書きしない。原ファイルやreceiptのシンボリックリンクは受け付けない。研究元の読取専用ディレクトリを直接指定せず、専用の作業ディレクトリを使う。

取得・ハッシュ・解析時の例外は`RUN.json.errors`へ残す。`processing_status`は処理の完了、`analysis_status`は期待チャンネル・比較系列の数値利用可能性を表す。後者は`usable`・`partial`・`excluded`のいずれかで、両方が完備した時だけ`status=pass`・終了符号0となる。必要系列が欠ける場合、+150msで有効標本100未満の場合、必要相関を有限値として計算できない場合は主集計へ入れず、理由を記録して終了符号1を返す。著者の低SNR除外は、数値利用可能性とは別に保持する。

ダウンロードは試行ごとに固有の一時ファイルを使う。失敗した試行の一時ファイルは削除し、以前の`.part`は保存して無視する。検証済みの取得物を排他的に配置し、既存ファイルを上書きしない。ネットワーク取得先の変更や配布停止は自動修復しない。メモリ使用量は最大記録と数値配列の展開に依存し、原ファイルサイズだけでは見積もれない。

公開当初の23記録再実行は[旧方式の照合結果](../data/ephys_validation.json)に保存した。現行脚本は時計区間を独立処理するv2で、[修正版の基礎表](../data/reanalysis/epoch-v2/RUN.json)と比較する。

```sh
.venv/bin/python scripts/reanalyze_ephys.py --raw-dir .local/raw --output .local/ephys-v2
python scripts/compare_ephys.py --generated .local/ephys-v2 --reference data/reanalysis/epoch-v2
.venv/bin/python scripts/reproduce_sensitivity.py --raw-dir .local/raw \
  --run-dir .local/ephys-v2 --output .local/sensitivity-v2
```

[独立した結果比較](ephys-comparison.md)は主キー・行集合・列・許容誤差・NaNの扱いを明示する。毎回変わる処理時間は比較から外す。原記録を一件だけ選んだ場合も、`RUN.json.selected_flies`を使って同じ対象を比較できる。[追補解析の生成](sensitivity.md)では、閾値、双側差、電位品質、時計境界の表を再計算する。従来の全追補注釈や全16研究束を一括で再生成するコマンドではない。

CIは標準ライブラリでの表検査に加え、Python 3.12と固定版の数値依存で小型MATの解析本体・公開CLIを実行する。原記録5.51GBはCIでは取得しない。

## 電位処理の固定条件

電位標準化は30/120秒の線形傾向除去平均、零位相100Hz高域通過、固定版の`reshape(fs,-1)`とaxis 0のMAD×1.4826、循環移動列の平均とFourier再標本化を使う。これは連続する局所0.5秒窓のMADと同じ処理ではない。

ピーク検出はheight=2.5、prominence評価窓10秒、DNa01=5.75、DNa02=7.5。非重複10ms区間へ計数し、標準偏差25msの対称Gaussianで発火率を平滑化する。標準化、ピーク検出、発火率平滑化、Vm平滑化は時計リセットごとの区間で完結する。時間移動対照も各区間内で移動し、相関の標本対は時計境界を跨がない。

刺激値>2.5の区間と、刺激配列に非有限値を含む不明区間を、前100/後250msまで除外する。不明を刺激なしへ置き換えない。整列NPZでは既知の高値と不明の指示配列を別々に保持するため、同一区間内で両者が併存する場合もある。両端500ms、時計境界前後500ms、非有限な行動値も除外する。基準解析はVm≤−33mVという品質条件を課さない。標準化方式を変えた比較は[別手順](normalization-sensitivity.md)を使う。

相関は`corr(neural(t), yaw(t+lag))`、主比較はlag=+150ms。時間差の正符号は神経系列が先であることを表す。相関頂点は因果遅延ではない。低SNRの`a2_d_14`は参考値を残して主比較から外す。[追加の注意](limitations.md)

## MaleCNSを新規取得する場合

収録するのはv1.0の特定snapshotである。元の公式注釈・全接続データの入口は[MaleCNS download](https://male-cns.janelia.org/download/)、API探索は[neuPrint](https://neuprint.janelia.org/)。登録や認証が必要な場合は配布元の方法に従う。認証情報はこの配布物へ含めない。

必要な集合を定義する際は、motor注釈の815 bodyIdを入力先として、全直接化学辺を取得し、`preIsNeuron`や型欠損も保持する。共有候補の条件は個々の辺のweightに適用する。二本のweight5を群で足して10とし、辺閾値10を満たしたことにはしない。群別の和は辺を選んだ後に計算する。

取得前後のMeta、版、取得時刻、応答のハッシュを保存し、この公開snapshotと異なる場合は別の解析版として扱う。公開版の[provenance](../data/provenance.json)にある元研究ファイルのハッシュは出所の照合用であり、未同梱ファイルのダウンロードURLではない。
