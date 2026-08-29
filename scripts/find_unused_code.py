#!/usr/bin/env python
"""未使用のクラス、関数、変数、メソッドを検出するASTベースのスクリプト."""

import ast
import contextlib
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ImportBinding:
    """Mapping between the imported public name and the original symbol."""

    public_name: str
    qualified_name: str
    is_from_import: bool


@dataclass
class Symbol:
    """コード内のシンボル情報."""

    name: str
    type: str  # 'class', 'function', 'method', 'variable', 'import'
    file: str
    line: int
    column: int
    parent: str | None = None  # クラスメソッドの場合は親クラス名
    is_private: bool = False  # _で始まる
    is_dunder: bool = False  # __で始まり__で終わる
    is_exported: bool = False  # __all__ にリストされている


@dataclass
class CodeAnalyzer:
    """コードベースの静的解析を行うクラス."""

    # 定義されたシンボル: filepath:name -> Symbol
    defined_symbols: dict[str, Symbol] = field(default_factory=dict)
    # 解決済み参照: symbol_name -> {filepath, ...}
    referenced_names: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    # ファイルごとの参照済みシンボル名: filepath -> {symbol_name, ...}
    references_by_file: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    # ファイルごとのインポート: filepath -> [ImportBinding, ...]
    imports_by_file: dict[str, list[ImportBinding]] = field(
        default_factory=lambda: defaultdict(list)
    )
    # __all__ エクスポート: filepath -> [exported_names]
    exports_by_file: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    # クラスの継承関係
    class_hierarchy: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    @staticmethod
    def _is_test_reference(path: str) -> bool:
        """テスト由来の参照かどうかを判定."""
        path_obj = Path(path)
        if path_obj.name.lower().startswith("test_"):
            return True
        return any(part.lower() == "tests" for part in path_obj.parts)

    def analyze_file(self, filepath: Path) -> None:
        """単一ファイルを解析."""
        with contextlib.suppress(SyntaxError, UnicodeDecodeError):
            with filepath.open(encoding="utf-8") as handle:
                source = handle.read()

            tree = ast.parse(source, filename=str(filepath))
            visitor = SymbolVisitor(str(filepath), self)
            visitor.visit(tree)

    def analyze_directory(self, directory: Path, exclude_dirs: set[str] | None = None) -> None:
        """ディレクトリ内のPythonファイルを再帰的に解析."""
        exclude_dirs = exclude_dirs or {
            "__pycache__",
            ".git",
            "venv",
            ".venv",
            "build",
            "dist",
            ".tox",
            "node_modules",
        }

        for py_file in directory.rglob("*.py"):
            # 除外ディレクトリをスキップ
            if any(exclude in py_file.parts for exclude in exclude_dirs):
                continue
            self.analyze_file(py_file)

    def record_reference(self, name: str, filepath: str) -> None:
        """Record a symbol reference originating from ``filepath``."""
        if not name:
            return
        self.references_by_file[filepath].add(name)

    def cross_reference(self) -> None:
        """ファイル間の参照を解決."""
        resolved: dict[str, set[str]] = defaultdict(set)

        for filepath, names in self.references_by_file.items():
            normalized_names = set(names)
            for binding in self.imports_by_file.get(filepath, []):
                if binding.public_name == "*":
                    continue
                if binding.public_name in names:
                    # エイリアス経由で参照された場合でも元のシンボル名に解決する
                    normalized_names.add(binding.public_name)
                    if binding.is_from_import:
                        original_symbol = binding.qualified_name.rsplit(".", 1)[-1]
                        normalized_names.add(original_symbol)

            for name in normalized_names:
                resolved[name].add(filepath)

        self.referenced_names = resolved

    def find_unused_symbols(self) -> dict[str, list[Symbol]]:
        """未使用のシンボルを検出."""
        # ファイル間参照を解決
        self.cross_reference()

        unused = {"classes": [], "functions": [], "methods": [], "variables": []}

        for symbol in self.defined_symbols.values():
            # 特殊ケースは除外
            if self._should_skip_symbol(symbol):
                continue

            # シンボル名が参照されているかチェック
            is_referenced = False

            # 直接参照をチェック
            if symbol.name in self.referenced_names:
                referencing_files = self.referenced_names[symbol.name]

                # テストファイルからの参照を除外
                non_test_refs = {f for f in referencing_files if not self._is_test_reference(f)}

                if non_test_refs:
                    # クラスの場合、特別な処理
                    if symbol.type == "class":
                        # 自分自身のファイル内での参照があるかチェック
                        if symbol.file in non_test_refs:
                            is_referenced = True
                        else:
                            # 外部ファイルからの参照のみの場合、__init__.py以外からの参照があるかチェック
                            non_init_refs = {
                                f for f in non_test_refs if not f.endswith("__init__.py")
                            }
                            is_referenced = bool(non_init_refs)
                    else:
                        is_referenced = True
                else:
                    # テストファイルからの参照のみの場合は未使用
                    is_referenced = False

            # クラスメソッドの場合は特別な処理は不要
            # メソッドも直接参照されている場合のみ使用されているとみなす

            # エクスポートされているか確認
            if (
                symbol.file in self.exports_by_file
                and symbol.name in self.exports_by_file[symbol.file]
            ):
                is_referenced = True

            # 未参照の場合はリストに追加
            if not is_referenced:
                if symbol.type == "class":
                    unused["classes"].append(symbol)
                elif symbol.type == "function":
                    unused["functions"].append(symbol)
                elif symbol.type == "method":
                    unused["methods"].append(symbol)
                elif symbol.type == "variable":
                    unused["variables"].append(symbol)

        return unused

    def _should_skip_symbol(self, symbol: Symbol) -> bool:
        """スキップすべきシンボルかチェック."""
        # 特殊メソッド
        if symbol.is_dunder:
            return True

        # テストファイル/メソッド
        if "test" in symbol.file.lower() or symbol.name.startswith("test_"):
            return True

        # 特定の名前
        skip_names = {"main", "setUp", "tearDown", "__all__", "logger"}
        if symbol.name in skip_names:
            return True

        # __init__.py内の定義は基本的に公開API
        return "__init__.py" in symbol.file


class SymbolVisitor(ast.NodeVisitor):
    """ASTを走査してシンボルを収集."""

    def __init__(self, filepath: str, analyzer: CodeAnalyzer) -> None:
        self.filepath = filepath
        self.analyzer = analyzer
        self.current_class = None
        self.in_function = 0  # 関数のネストレベル

    def _make_symbol_id(self, name: str, parent: str | None = None) -> str:
        """一意のシンボルIDを生成."""
        if parent:
            return f"{self.filepath}:{parent}.{name}"
        return f"{self.filepath}:{name}"

    def _is_private(self, name: str) -> bool:
        """プライベートシンボルかチェック."""
        return name.startswith("_") and not name.startswith("__")

    def _is_dunder(self, name: str) -> bool:
        """特殊メソッド（ダンダー）かチェック."""
        return name.startswith("__") and name.endswith("__")

    def visit_Module(self, node: ast.Module) -> None:
        """モジュールを処理."""
        # __all__ を探す
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id == "__all__"
                        and isinstance(stmt.value, ast.List | ast.Tuple)
                    ):
                        for elt in stmt.value.elts:
                            if isinstance(elt, ast.Constant):
                                self.analyzer.exports_by_file[self.filepath].add(elt.value)

        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """クラス定義を処理."""
        symbol_id = self._make_symbol_id(node.name)
        symbol = Symbol(
            name=node.name,
            type="class",
            file=self.filepath,
            line=node.lineno,
            column=node.col_offset,
            is_private=self._is_private(node.name),
            is_dunder=self._is_dunder(node.name),
        )
        self.analyzer.defined_symbols[symbol_id] = symbol

        # 基底クラスを参照として記録
        for base in node.bases:
            if isinstance(base, ast.Name):
                self.analyzer.class_hierarchy[node.name].add(base.id)
                self.analyzer.record_reference(base.id, self.filepath)
            elif isinstance(base, ast.Attribute):
                # module.BaseClass のようなケース
                self.analyzer.record_reference(base.attr, self.filepath)

        # デコレータを参照として記録
        for decorator in node.decorator_list:
            self._extract_references(decorator)

        # クラス内を走査
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """関数/メソッド定義を処理."""
        self._visit_function_def(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """非同期関数/メソッド定義を処理."""
        self._visit_function_def(node)

    def _visit_function_def(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """関数定義の共通処理."""
        # 関数/メソッド自体を定義として記録
        if self.in_function == 0:  # トップレベルの関数/メソッドのみ
            if self.current_class:
                # メソッド
                symbol_id = self._make_symbol_id(node.name, self.current_class)
                symbol_type = "method"
                parent = self.current_class
            else:
                # 関数
                symbol_id = self._make_symbol_id(node.name)
                symbol_type = "function"
                parent = None

            symbol = Symbol(
                name=node.name,
                type=symbol_type,
                file=self.filepath,
                line=node.lineno,
                column=node.col_offset,
                parent=parent,
                is_private=self._is_private(node.name),
                is_dunder=self._is_dunder(node.name),
            )
            self.analyzer.defined_symbols[symbol_id] = symbol

        # デコレータの参照を記録
        for decorator in node.decorator_list:
            self._extract_references(decorator)

        # 関数内を走査
        self.in_function += 1
        self.generic_visit(node)
        self.in_function -= 1

    def visit_Assign(self, node: ast.Assign) -> None:
        """変数代入を処理."""
        # モジュールレベルの変数定義
        if self.in_function == 0 and not self.current_class:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    # __all__ は特別扱い
                    if target.id == "__all__":
                        continue

                    symbol_id = self._make_symbol_id(target.id)
                    symbol = Symbol(
                        name=target.id,
                        type="variable",
                        file=self.filepath,
                        line=node.lineno,
                        column=node.col_offset,
                        is_private=self._is_private(target.id),
                    )
                    self.analyzer.defined_symbols[symbol_id] = symbol

        # 右辺の参照を抽出
        self._extract_references(node.value)

        # 代入ターゲットも訪問（属性アクセスなどがある場合）
        for target in node.targets:
            if not isinstance(target, ast.Name):
                self._extract_references(target)

    def _extract_references(self, node: ast.AST | None) -> None:
        """ノードから参照を抽出."""
        if node is None:
            return

        if isinstance(node, ast.Name):
            # 単純な名前参照
            self.analyzer.record_reference(node.id, self.filepath)
        elif isinstance(node, ast.Attribute):
            # obj.attr のような参照
            # attrを参照として記録
            self.analyzer.record_reference(node.attr, self.filepath)
            # objも再帰的に処理
            self._extract_references(node.value)
        elif isinstance(node, ast.Call):
            # 関数呼び出し
            self._extract_references(node.func)
            for arg in node.args:
                self._extract_references(arg)
            for keyword in node.keywords:
                self._extract_references(keyword.value)
        elif isinstance(node, ast.Subscript):
            # obj[key] のような参照
            self._extract_references(node.value)
            self._extract_references(node.slice)
        elif isinstance(node, ast.List | ast.Tuple | ast.Set):
            # コレクション
            for elt in node.elts:
                self._extract_references(elt)
        elif isinstance(node, ast.Dict):
            # 辞書
            for key in node.keys:
                self._extract_references(key)
            for value in node.values:
                self._extract_references(value)
        elif isinstance(node, ast.BinOp):
            # 二項演算
            self._extract_references(node.left)
            self._extract_references(node.right)
        elif isinstance(node, ast.UnaryOp):
            # 単項演算
            self._extract_references(node.operand)
        elif isinstance(node, ast.Compare):
            # 比較
            self._extract_references(node.left)
            for comp in node.comparators:
                self._extract_references(comp)
        elif isinstance(node, ast.BoolOp):
            # and/or
            for value in node.values:
                self._extract_references(value)
        elif isinstance(node, ast.IfExp):
            # 三項演算子
            self._extract_references(node.test)
            self._extract_references(node.body)
            self._extract_references(node.orelse)
        elif isinstance(node, ast.Lambda):
            # ラムダ式の本体
            self._extract_references(node.body)
        elif isinstance(node, ast.ListComp):
            # リスト内包表記
            self._extract_references(node.elt)
            for gen in node.generators:
                self._extract_references(gen.iter)
                for if_ in gen.ifs:
                    self._extract_references(if_)
        elif isinstance(node, ast.JoinedStr):
            # f-string
            for value in node.values:
                self._extract_references(value)
        elif isinstance(node, ast.FormattedValue):
            # f-string内のフォーマット値
            self._extract_references(node.value)
        # 他のノードタイプも必要に応じて追加

    def visit(self, node: ast.AST) -> None:  # type: ignore[override]
        """ノードを訪問（参照を抽出）."""
        # 定義ノード（ClassDef, FunctionDef等）の場合は、
        # それぞれのvisit_*メソッドで処理されるので、ここでは参照抽出をスキップ
        # ただし、それ以外のノードは参照を抽出
        if not isinstance(
            node,
            ast.ClassDef
            | ast.FunctionDef
            | ast.AsyncFunctionDef
            | ast.Assign
            | ast.Import
            | ast.ImportFrom,
        ):
            self._extract_references(node)

        # 通常の訪問処理
        super().visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """import文を処理."""
        for alias in node.names:
            module_name = alias.name
            public_name = alias.asname or alias.name.split(".")[0]
            binding = ImportBinding(
                public_name=public_name, qualified_name=module_name, is_from_import=False
            )
            self.analyzer.imports_by_file[self.filepath].append(binding)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """From ... import文を処理."""
        module = node.module or ""
        for alias in node.names:
            if alias.name == "*":
                qualified = f"{module}.*" if module else "*"
                binding = ImportBinding(
                    public_name="*", qualified_name=qualified, is_from_import=True
                )
                self.analyzer.imports_by_file[self.filepath].append(binding)
                continue

            public_name = alias.asname or alias.name
            qualified_name = f"{module}.{alias.name}" if module else alias.name
            binding = ImportBinding(
                public_name=public_name, qualified_name=qualified_name, is_from_import=True
            )
            self.analyzer.imports_by_file[self.filepath].append(binding)


def format_results(unused: dict[str, list[Symbol]], base_path: Path) -> str:
    """結果を整形してMarkdown形式で返す."""
    total = sum(len(symbols) for symbols in unused.values())

    if total == 0:
        return "# 未使用コード分析結果\n\n✅ 未使用のコードは見つかりませんでした。\n"

    lines = ["# 未使用コード分析結果\n"]
    lines.append("## 概要\n")
    lines.append(f"- **合計未使用シンボル数**: {total}\n")

    for category in ["classes", "functions", "methods", "variables"]:
        count = len(unused.get(category, []))
        if count > 0:
            lines.append(f"- **{category.capitalize()}**: {count}\n")

    lines.append("\n---\n")

    for category, symbols in unused.items():
        if not symbols:
            continue

        lines.append(f"\n## 未使用の{category.capitalize()}\n")

        # ファイルごとにグループ化
        by_file = defaultdict(list)
        for symbol in symbols:
            try:
                rel_path = Path(symbol.file).relative_to(base_path)
                by_file[str(rel_path)].append(symbol)
            except ValueError:
                by_file[symbol.file].append(symbol)

        # 全てのファイルと全てのシンボルを表示
        for filepath in sorted(by_file.keys()):
            lines.append(f"\n### `{filepath}`\n")
            for symbol in sorted(by_file[filepath], key=lambda s: s.line):
                if symbol.parent:
                    lines.append(f"- **{symbol.parent}.{symbol.name}** (L{symbol.line})")
                else:
                    lines.append(f"- **{symbol.name}** (L{symbol.line})")

                if symbol.is_private:
                    lines.append(" [private]")
                lines.append("\n")

    return "".join(lines)


def save_json_report(unused: dict[str, list[Symbol]], output_file: Path) -> None:
    """JSON形式でレポートを保存."""
    report = {}
    for category, symbols in unused.items():
        report[category] = [
            {
                "name": s.name,
                "file": s.file,
                "line": s.line,
                "parent": s.parent,
                "is_private": s.is_private,
            }
            for s in symbols
        ]

    with output_file.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)


def main() -> None:
    """メイン処理."""
    # プロジェクトルートを検出
    project_root = Path(__file__).parent.parent
    src_dir = project_root / "src" / "chappy"
    tests_dir = project_root / "tests"

    if not src_dir.exists():
        sys.exit(1)

    # 解析実行
    analyzer = CodeAnalyzer()
    analyzer.analyze_directory(src_dir)

    # testsディレクトリも解析（参照情報のみ取得）
    if tests_dir.exists():
        analyzer.analyze_directory(tests_dir)

    # 未使用シンボルを検出
    unused = analyzer.find_unused_symbols()

    # 結果を標準出力に書き込み
    markdown_report = format_results(unused, project_root)
    sys.stdout.write(markdown_report)
    sys.stdout.flush()

    # JSONレポートを保存
    report_file = project_root / "unused_code_report.json"
    save_json_report(unused, report_file)
    sys.stdout.write(f"\n📄 JSONレポートを保存しました: {report_file}\n")

    # 終了コード
    total_unused = sum(len(symbols) for symbols in unused.values())
    if total_unused > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
