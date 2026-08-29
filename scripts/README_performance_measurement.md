# パフォーマンス測定ガイド

## 概要

吸収線データベース画面のパフォーマンス測定を行うためのツールと手順です。GUI 本体にはプロファイラが組み込まれていないため、必ず本ドキュメントで説明する専用スクリプトを経由してダイアログを起動してください。

## 測定方法

### 1. 測定スクリプトを起動

LineSelectionDialog のメソッドを外部からラップして計測する `scripts/measure_line_selection_performance.py` を実行します。スクリプト内で `CHAPPY_PROFILE_PERFORMANCE` を自動的に `true` に設定しますが、出力先を変更したい場合は `CHAPPY_PROFILE_OUTPUT_DIR` を指定してください。

```bash
export CHAPPY_PROFILE_OUTPUT_DIR=performance_logs  # 任意
uv run python scripts/measure_line_selection_performance.py
```

### 2. 操作を実行

画面で以下の操作を実行してください：

- チェックボックスのクリック（複数回）
- フィルタの変更
- ソート操作

### 3. 測定結果の確認

スクリプトがダイアログを閉じると、`performance_logs/` ディレクトリに測定結果が保存されます。GUI を通常起動しただけでは計測されません。

ファイル名は `line_selection_dialog_<timestamp>.json` の形式です。

## 測定結果の形式

JSONファイルには以下の情報が含まれます：

```json
{
  "total_records": 100,
  "records": [
    {
      "function_name": "_on_item_changed",
      "elapsed_time_ms": 123.45,
      "timestamp": 1234567890.123,
      "metadata": {
        "row_count": 2600
      }
    },
    ...
  ]
}
```

## ベースラインの記録

初回測定結果をベースラインとして保存してください：

```bash
cp performance_logs/line_selection_dialog_<timestamp>.json performance_logs/baseline.json
```

## 最適化後の比較

専用の比較スクリプトは存在しないため、下記のユーティリティ（Python 標準ライブラリのみ）で平均時間を確認してください：

```bash
python - <<'PY' performance_logs/baseline.json performance_logs/line_selection_dialog_<new_timestamp>.json
import json
import statistics
import sys

def summarize(path: str) -> dict[str, float]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    groups: dict[str, list[float]] = {}
    for record in data.get("records", []):
        groups.setdefault(record["function_name"], []).append(record["elapsed_time_ms"])
    return {name: statistics.mean(times) for name, times in groups.items()}

baseline, target = map(summarize, sys.argv[1:3])
all_names = sorted(set(baseline) | set(target))
for name in all_names:
    print(f"{name}: baseline={baseline.get(name, 0):.2f} ms, target={target.get(name, 0):.2f} ms")
PY
```

シンプルに差分を見たい場合は `python -m json.tool` や `diff -u` などで JSON を比較しても構いません。

## 測定対象の関数

以下の関数の実行時間が測定されます：

- `_on_item_changed`: チェックボックス変更時の全体処理
- `_apply_multiplet_highlight`: ハイライト処理
- `_update_checkbox_sort_keys`: ソートキー更新処理
- `_row_for_line`: 行検索処理
- `_populate_table`: テーブル生成処理

## 注意事項

- プロファイリングが有効な場合、わずかなオーバーヘッドが発生します
- 本番環境では無効化してください（環境変数を設定しない）
- 測定結果は開発・最適化の参考として使用してください
