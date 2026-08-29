# インストール手順

**日本語** | [English](INSTALL.en.md)

chappy を実行するために必要なセットアップ手順です。

## 1. uv のインストール

chappy は Python パッケージマネージャー [uv](https://docs.astral.sh/uv/) を使用しています。
以下の手順で uv をインストールしてください。

### Windows

PowerShell を開き、以下のコマンドを実行します：

```powershell
winget install --id=astral-sh.uv -e
```

### macOS / Linux

ターミナルを開き、以下のコマンドを実行します：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

インストール完了後、ターミナルを再起動してください。
または、インストーラーが表示する指示に従ってパスを通してください。

### その他のインストール方法

上記以外のインストール方法については、公式ドキュメントを参照してください：

- [uv Installation Guide](https://docs.astral.sh/uv/getting-started/installation/)

## 2. chappy の実行

**Windows:**

1. エクスプローラーで `scripts` フォルダを開く
2. `run.cmd` をダブルクリック

または、コマンドプロンプトから：

```cmd
scripts\run.cmd
```

**macOS:**

1. Finder で `scripts` フォルダを開く
2. `run.command` をダブルクリック

初回実行時は「開発元を確認できない」という警告が表示される場合があります。
その場合は、Control キーを押しながらクリックして「開く」を選択してください。

または、ターミナルから：

```bash
./scripts/run.sh
```

**Linux:**

ターミナルで以下を実行：

```bash
./scripts/run.sh
```

アプリケーションメニューに登録したい場合は、以下を一度実行してください：

```bash
./scripts/install-desktop.sh
```

---

初回実行時は、必要な Python バージョンと依存パッケージが自動的にダウンロード・インストールされます。

## 3. Windows での注意事項（パス長の制限）

Windows には従来 260 文字のパス長制限があります。
chappy を深いフォルダ階層に配置すると、依存パッケージのインストールに失敗する場合があります。

chappy は**短いパス**に配置してください：

- ✓ `C:\chappy`
- ✓ `D:\projects\chappy`
- ✗ `C:\Users\Username\Documents\Research\2024\Projects\Astronomy\chappy`

## 4. アンインストール

chappy はインストーラーを使わないため、以下を手動で削除します。
作業前に chappy を終了してください（起動中だと設定が書き戻されます）。

### 4.1 アプリケーション本体

配置したフォルダをそのまま削除します。
実行時に自動生成される `.venv` / `.uv` も一緒に消えます。

### 4.2 ユーザーデータ（`~/.chappy/`）

| ファイル・ディレクトリ | 内容 |
| --- | --- |
| `presets.json` | 吸収線プリセット |
| `config.toml` | 言語設定 |
| `spectral_lines.csv` | 差し替え用のスペクトル線カタログ（置いた場合のみ） |
| `log/` | アプリケーションログ |

```bash
rm -rf ~/.chappy          # macOS / Linux
```

```powershell
Remove-Item -Recurse -Force "$HOME\.chappy"   # Windows
```

環境変数 `CHAPPY_CONFIG_DIR` / `CHAPPY_LOG_DIR` / `CHAPPY_SPECTRAL_LINES_CSV` を設定していた場合は、
`~/.chappy` ではなくそちらで指定したディレクトリが対象になります。

### 4.3 ウィンドウ状態などの GUI 設定

ウィンドウサイズ・分割位置・最後に開いたフォルダなどは、OS 標準の設定領域に保存されます。
chappy は 2 つの設定ストアを使うため、いずれも削除してください。

**macOS:**

```bash
defaults delete com.chappy-astronomy.chappy
defaults delete com.chappy.Chappy
```

**Windows:** レジストリエディタで以下のキーを削除します。

- `HKEY_CURRENT_USER\Software\chappy\chappy`
- `HKEY_CURRENT_USER\Software\Chappy\Chappy`

**Linux:**

```bash
rm -f ~/.config/chappy/chappy.conf ~/.config/Chappy/Chappy.conf
```

### 4.4 デスクトップエントリ（Linux のみ）

`scripts/install-desktop.sh` を実行していた場合のみ削除します。

```bash
rm -f ~/.local/share/applications/chappy.desktop
```
