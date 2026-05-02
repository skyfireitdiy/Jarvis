#!/usr/bin/env python3
"""
PlantUML提取与写回脚本

功能：
1. 从Markdown文件中提取PlantUML代码块为单独的.puml文件
2. 将修复后的.puml文件内容写回Markdown文件

用法：
    # 提取PlantUML代码块
    python3 plantuml_fix.py extract <markdown_file> [-o output_dir]

    # 校验.puml文件（调用plantuml程序）
    python3 plantuml_fix.py validate <puml_file_or_dir>

    # 将.puml文件内容写回Markdown文件
    python3 plantuml_fix.py writeback <markdown_file> <puml_dir>

工作流程：
    1. extract: 从MD提取PlantUML到.puml文件
    2. 使用plantuml程序校验/编辑.puml文件
    3. writeback: 将修复后的.puml写回MD
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple


class PlantUMLBlock:
    """表示一个PlantUML代码块"""

    def __init__(self, content: str, start_line: int, end_line: int, index: int):
        self.content = content
        self.start_line = start_line
        self.end_line = end_line
        self.index = index

    def __repr__(self):
        return f"PlantUMLBlock(index={self.index}, lines {self.start_line}-{self.end_line})"


class PlantUMLExtractor:
    """PlantUML代码块提取器"""

    PLANTUML_PATTERN = re.compile(r"```plantuml\s*\n((?:.*\n)*?)\s*```", re.MULTILINE)

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def _log(self, message: str):
        if self.verbose:
            print(f"[INFO] {message}")

    def _error(self, message: str):
        print(f"[ERROR] {message}", file=sys.stderr)

    def extract_blocks(self, content: str) -> List[PlantUMLBlock]:
        """从Markdown内容中提取PlantUML代码块"""
        blocks = []
        for i, match in enumerate(self.PLANTUML_PATTERN.finditer(content)):
            code = match.group(1)
            start_line = content[: match.start()].count("\n") + 1
            end_line = content[: match.end()].count("\n") + 1
            blocks.append(PlantUMLBlock(code, start_line, end_line, i))
        return blocks

    def extract_to_files(
        self, md_file: str, output_dir: Optional[str] = None
    ) -> List[str]:
        """从Markdown文件提取PlantUML代码块到.puml文件"""
        md_path = Path(md_file)
        if not md_path.exists():
            self._error(f"文件不存在: {md_file}")
            return []

        try:
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            self._error(f"无法读取文件: {e}")
            return []

        blocks = self.extract_blocks(content)
        if not blocks:
            print(f"文件 {md_file} 中未找到PlantUML代码块")
            return []

        if output_dir:
            out_dir = Path(output_dir)
        else:
            # 默认使用临时目录，避免被git管理
            import tempfile

            out_dir = Path(tempfile.gettempdir()) / f"plantuml_{md_path.stem}"

        out_dir.mkdir(parents=True, exist_ok=True)

        created_files = []
        for block in blocks:
            puml_file = out_dir / f"{md_path.stem}_{block.index}.puml"
            content_to_write = block.content
            if "@startuml" not in content_to_write:
                content_to_write = "@startuml\n" + content_to_write
            if "@enduml" not in content_to_write:
                content_to_write = content_to_write.rstrip() + "\n@enduml"

            try:
                with open(puml_file, "w", encoding="utf-8") as f:
                    f.write(content_to_write)
                created_files.append(str(puml_file))
                self._log(f"创建: {puml_file}")
            except Exception as e:
                self._error(f"无法写入 {puml_file}: {e}")

        print(f"\n提取完成: 从 {md_file} 提取了 {len(created_files)} 个PlantUML代码块")
        print(f"输出目录: {out_dir}")
        print("\n下一步: 使用 plantuml 程序校验这些文件:")
        print(f"  plantuml -checkonly {out_dir}/*.puml")

        return created_files


class PlantUMLValidator:
    """PlantUML校验器"""

    def __init__(self, plantuml_cmd: str = "plantuml", verbose: bool = False):
        self.plantuml_cmd = plantuml_cmd
        self.verbose = verbose

    def validate_file(self, puml_path: str) -> Tuple[bool, Optional[str]]:
        """校验单个.puml文件"""
        try:
            cmd = f'{self.plantuml_cmd} -checkonly "{puml_path}"'
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return True, None
            else:
                return False, result.stderr or result.stdout
        except subprocess.TimeoutExpired:
            return False, "校验超时"
        except Exception as e:
            return False, str(e)

    def validate_directory(self, dir_path: str) -> dict:
        """校验目录中的所有.puml文件"""
        dir_obj = Path(dir_path)
        if not dir_obj.is_dir():
            print(f"[ERROR] 目录不存在: {dir_path}", file=sys.stderr)
            return {}

        puml_files = sorted(dir_obj.glob("*.puml"))
        if not puml_files:
            print(f"目录 {dir_path} 中未找到.puml文件")
            return {}

        print(f"\n校验 {len(puml_files)} 个.puml文件...\n")
        results = {}
        for puml_file in puml_files:
            is_valid, error = self.validate_file(str(puml_file))
            results[str(puml_file)] = {"valid": is_valid, "error": error}
            status = "✓ 通过" if is_valid else "✗ 失败"
            print(f"{status}: {puml_file.name}")
            if error:
                print(
                    f"  错误: {error[:200]}"
                    if len(error) <= 200
                    else f"  错误: {error[:200]}..."
                )

        valid_count = sum(1 for r in results.values() if r["valid"])
        print(f"\n校验完成: {valid_count}/{len(results)} 通过")
        return results


class PlantUMLWriter:
    """将.puml文件内容写回Markdown"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def _log(self, message: str):
        if self.verbose:
            print(f"[INFO] {message}")

    def _error(self, message: str):
        print(f"[ERROR] {message}", file=sys.stderr)

    def writeback(self, md_file: str, puml_dir: str, backup: bool = True) -> bool:
        """将.puml文件内容写回Markdown文件"""
        md_path = Path(md_file)
        puml_path = Path(puml_dir)

        if not md_path.exists():
            self._error(f"Markdown文件不存在: {md_file}")
            return False
        if not puml_path.is_dir():
            self._error(f".puml目录不存在: {puml_dir}")
            return False

        try:
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            self._error(f"无法读取MD文件: {e}")
            return False

        puml_files = sorted(puml_path.glob(f"{md_path.stem}_*.puml"))
        if not puml_files:
            self._log(f"未找到匹配的.puml文件: {md_path.stem}_*.puml")
            return False

        puml_contents = {}
        for puml_file in puml_files:
            match = re.search(r"_(\d+)\.puml$", puml_file.name)
            if match:
                index = int(match.group(1))
                try:
                    with open(puml_file, "r", encoding="utf-8") as f:
                        puml_content = f.read()
                    puml_content = re.sub(r"^@startuml\s*\n?", "", puml_content)
                    puml_content = re.sub(r"\n?@enduml\s*$", "", puml_content)
                    puml_contents[index] = puml_content
                    self._log(f"读取: {puml_file.name}")
                except Exception as e:
                    self._error(f"无法读取 {puml_file}: {e}")

        pattern = re.compile(r"(```plantuml\s*\n)((?:.*\n)*?)(\s*```)", re.MULTILINE)
        new_content = content
        offset = 0

        for i, match in enumerate(pattern.finditer(content)):
            if i in puml_contents:
                start = match.start(2) + offset
                end = match.end(2) + offset
                new_content = new_content[:start] + puml_contents[i] + new_content[end:]
                offset += len(puml_contents[i]) - len(match.group(2))
                self._log(f"更新代码块 {i}")

        if backup:
            backup_path = str(md_path) + ".bak"
            shutil.copy2(md_path, backup_path)
            self._log(f"备份: {backup_path}")

        try:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"\n写回完成: {md_file}")
            print(f"更新了 {len(puml_contents)} 个PlantUML代码块")
            return True
        except Exception as e:
            self._error(f"无法写入MD文件: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(
        description="PlantUML提取、校验与写回工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
工作流程:
  1. 提取: python3 plantuml_fix.py extract document.md
  2. 校验: plantuml -checkonly document_plantuml/*.puml
  3. 修复: 手动编辑.puml文件修复错误
  4. 写回: python3 plantuml_fix.py writeback document.md document_plantuml/

示例:
  %(prog)s extract README.md                    # 提取到 README_plantuml/ 目录
  %(prog)s extract README.md -o uml/            # 提取到指定目录
  %(prog)s validate README_plantuml/            # 校验所有.puml文件
  %(prog)s writeback README.md README_plantuml/ # 写回修复后的内容
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    extract_parser = subparsers.add_parser(
        "extract", help="从Markdown提取PlantUML代码块"
    )
    extract_parser.add_argument("markdown_file", help="Markdown文件路径")
    extract_parser.add_argument("-o", "--output", help="输出目录")
    extract_parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    validate_parser = subparsers.add_parser("validate", help="校验.puml文件")
    validate_parser.add_argument("path", help=".puml文件或目录路径")
    validate_parser.add_argument(
        "--plantuml", default="plantuml", help="plantuml程序路径"
    )

    writeback_parser = subparsers.add_parser(
        "writeback", help="将.puml内容写回Markdown"
    )
    writeback_parser.add_argument("markdown_file", help="Markdown文件路径")
    writeback_parser.add_argument("puml_dir", help=".puml文件目录")
    writeback_parser.add_argument("--no-backup", action="store_true", help="不创建备份")
    writeback_parser.add_argument(
        "-v", "--verbose", action="store_true", help="详细输出"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "extract":
        extractor = PlantUMLExtractor(verbose=args.verbose)
        extractor.extract_to_files(args.markdown_file, args.output)

    elif args.command == "validate":
        validator = PlantUMLValidator(plantuml_cmd=args.plantuml)
        path = Path(args.path)
        if path.is_file():
            is_valid, error = validator.validate_file(str(path))
            if is_valid:
                print(f"✓ 通过: {path}")
            else:
                print(f"✗ 失败: {path}")
                print(f"  错误: {error}")
                sys.exit(1)
        elif path.is_dir():
            results = validator.validate_directory(str(path))
            if any(not r["valid"] for r in results.values()):
                sys.exit(1)
        else:
            print(f"[ERROR] 路径不存在: {args.path}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "writeback":
        writer = PlantUMLWriter(verbose=args.verbose)
        success = writer.writeback(
            args.markdown_file, args.puml_dir, backup=not args.no_backup
        )
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
