# マニュアル生成器の Qt 翻訳カタログ

`manual_ja.ts` / `manual_ja.qm` はマニュアル生成器
(`chappy_user_manual_generator`)専用の Qt 翻訳カタログ。chappy 本体の
`src/chappy/i18n/qt/chappy_ja.ts` と同じ Qt 方式(`tr` /
`QT_TRANSLATE_NOOP` + `lupdate` / `lrelease`)だが、カタログは分離されて
おり、ロードは `translations.py` の `install_language()` が行う
(`__main__.py` で `--language` 指定時に呼び出される)。

カタログのコンテキストは由来で分かれる: `ManualAnnotations`
(annotations_map.yaml の `text:` 文字列)、`ManualExporter`(exporter/
pipeline/manifest/panel_windows/data 配下のコード直書き)、`ManualMenu`
(menu_exporter.py)、`ManualTemplates`(templates.py)。加えて
`install_language()` は chappy 本体カタログ(`chappy_ja.qm`)も併せて
ロードし、メニュー項目のラベルやステータスチップ
(`MenuActionFactory` コンテキスト)を解決する。経緯は
`docs/adr/doc-translation-qt-unification.md` を参照。

すべてリポジトリルートから実行する。

## 抽出ブリッジ(annotations_map.yaml → lupdate 供給用生成ファイル)

`pyside6-lupdate` は `.py` などのソースファイルしか解析しないため、
`annotations_map.yaml` に `text:` として宣言された英語文字列は素通りする。
lupdate の前工程として、YAML 内の全 `text:` 文字列を
`QT_TRANSLATE_NOOP("ManualAnnotations", ...)` として列挙した生成ファイル
`i18n/_annotations_extraction_bridge.py` を再生成すること
(ランタイムからは import されず、lupdate 専用)。

```bash
uv run python scripts/i18n_manual_annotations_bridge.py
```

`annotations_map.yaml` を変更したら、lupdate を実行する前に必ずこの
スクリプトを再実行して生成ファイルを最新化すること。生成ファイルは
`ruff format` の対象なので、再生成後にフォーマットしてからコミットする。

同期確認(lefthook pre-push / CI でも実行される):

```bash
uv run python scripts/i18n_manual_annotations_bridge.py --check
```

## lupdate(ソースからメッセージを抽出し `.ts` を更新)

```bash
uv run python scripts/i18n_lupdate.py docs/user_manual/src/chappy_user_manual_generator \
  --ts-output docs/user_manual/src/chappy_user_manual_generator/i18n/manual_ja.ts
```

## lrelease(`.ts` から `.qm` を生成)

```bash
uv run python scripts/i18n_lrelease.py \
  docs/user_manual/src/chappy_user_manual_generator/i18n/manual_ja.ts \
  --qm-output docs/user_manual/src/chappy_user_manual_generator/i18n/manual_ja.qm
```

## check(未訳・obsolete・ソース差分・コミット済み `.qm` の陳腐化を検査)

```bash
uv run python scripts/i18n_qt_check.py docs/user_manual/src/chappy_user_manual_generator \
  --ts-input docs/user_manual/src/chappy_user_manual_generator/i18n/manual_ja.ts \
  --expected-qm docs/user_manual/src/chappy_user_manual_generator/i18n/manual_ja.qm
```

`.ts` / `.qm` はコミット対象の生成物(chappy 本体の `chappy_ja.qm` と同じ
扱い)。ソースを変更したら(YAML 変更時はブリッジ再生成 →)lupdate →
訳 → lrelease → check の順で更新すること。未訳(unfinished)・空訳・
obsolete はゼロを維持する。

ブリッジ同期チェックとこの check は lefthook pre-push
(`i18n-manual-bridge-sync` / `i18n-manual-catalog`)と CI(i18n Checks
ジョブ)で自動実行される。
