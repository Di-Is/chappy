# コントリビューションガイド

**日本語** | [English](CONTRIBUTING.en.md)

バグ報告・機能提案・プルリクエストを歓迎します。

## バグ報告・機能提案

[Issues](https://github.com/Di-Is/qso-chappy/issues) からお知らせください。
バグ報告には、次の情報があると調査が進めやすくなります。

- 何をしようとして、何が起きたか
- OS とバージョン（Windows / macOS / Linux）
- ログ（`~/.chappy/log/`）に関連する記録があれば、その抜粋

## 開発環境のセットアップ

### 前提条件

- Python 3.12 以降
- [mise](https://mise.jdx.dev/) — ツールのバージョン管理
- [uv](https://github.com/astral-sh/uv) — Python パッケージ管理

### 手順

1. mise をインストールし、ツールを導入する:

   ```bash
   curl https://mise.jdx.dev/install.sh | sh   # 未導入の場合
   mise install
   ```

2. 依存パッケージを導入する:

   ```bash
   uv sync --all-extras
   ```

   `uv sync` が `.venv` の作成まで行うため、事前の `uv venv` は不要です。
   以降のコマンドは `uv run` 経由で実行するので、仮想環境を activate する必要もありません。

3. git hooks を導入する:

   ```bash
   lefthook install
   ```

   以降、commit と push のたびに lint・型チェック・テストが自動で実行されます。
   実行内容は [`lefthook.yml`](lefthook.yml) を参照してください。

## 開発時の操作

### アプリケーションの起動

```bash
uv run chappy
```

### 品質チェック

```bash
uv run ruff check .           # リンタ
uv run ruff format .          # フォーマッタ
uv run mypy src/              # 型チェック
uv run pytest                 # テスト
uv run lint-imports           # アーキテクチャ境界の検査
```

個別のテストを実行する場合:

```bash
uv run pytest tests/test_voigt.py::TestVoigtProfile::test_gaussian_limit
```

### ユーザーマニュアルの生成

```bash
uv run --project docs/user_manual -m chappy_user_manual_generator
```

生成物は `docs/user_manual/dist/` に出力されます（リポジトリには含めません）。
リリース時は GitHub Actions が生成し、配布パッケージへ同梱します。

## コーディング方針

- 型安全性と保守性を優先します
- 内部の構成は自由に変更できます。保守性とアーキテクチャの整合が改善するなら、大きな作り替えも歓迎します
- 実行されないコードは残しません

アーキテクチャの層構造は `lint-imports`（`pyproject.toml` の import-linter 契約）で機械的に検査されます。
層をまたぐ import を追加する場合は、契約の見直しが必要かどうかを検討してください。

## バージョニング

バージョンは [セマンティックバージョニング](https://semver.org/lang/ja/) に従います。
GUI アプリケーションのためライブラリとしての公開 API は持ちませんが、代わりに次をユーザーとの約束として扱います。

- 保存ファイルの形式 — プロジェクト（`.h5` / `.hdf5`）とプリセット（`~/.chappy/presets.json`）
- コマンドライン引数と、`CHAPPY_CONFIG_DIR` などの環境変数

| 変更の内容 | 上げる番号 |
|--|--|
| 以前のバージョンで保存したファイルが開けなくなる、既存の引数が使えなくなる | MAJOR |
| 機能を追加する（以前のファイルは引き続き開ける） | MINOR |
| 不具合の修正のみ | PATCH |

`PROJECT_SCHEMA_VERSION`（`src/chappy/application/project_schema.py`）と
`PRESET_FILE_SCHEMA_VERSION`（`src/chappy/infrastructure/preset_store.py`）を変更するときは、
古い形式を読み込む移行処理を必ず用意してください。
現在の読み込み処理はスキーマ番号の完全一致を要求するため、移行処理のないまま番号を上げると、
ユーザーが保存済みのファイルはすべて読み込み時に拒否されます。

### リリース手順

1. `pyproject.toml` の `version` を新しいバージョンに更新する
2. `v<バージョン>` のタグを push する（例: `v1.2.0`）

タグの push で GitHub Actions がユーザーマニュアルを生成し、配布パッケージを作成して Release を公開します。
配布物のバージョンは `pyproject.toml` から取り込まれるため、タグと食い違わないよう手順1を先に行ってください。

## プルリクエストの手順

1. 作業ブランチを作成する
2. 変更を加える
3. 上記の品質チェックがすべて通ることを確認する
4. プルリクエストを作成する

ユーザーに見える文言を追加・変更した場合は、日本語と英語の両方を更新してください。
