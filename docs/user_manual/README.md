# chappy User Manual Toolkit

このディレクトリは chappy のユーザーマニュアル生成用プロジェクトです。`pyproject.toml` をベースに `uv` で依存関係を管理し、`chappy_user_manual_generator` パッケージから CLI を提供します。

メインアプリケーションのソースコードは `../..` に配置されているため、`pyproject.toml` では `chappy` をパス依存として参照します。マニュアル生成後の Markdown は `dist/markdown/` に配置されます。
