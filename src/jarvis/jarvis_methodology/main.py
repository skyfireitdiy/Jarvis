"""
方法论导入导出命令行工具

功能：
- 导入方法论文件（合并策略）
- 导出当前方法论
- 列出所有方法论
"""

import hashlib
import os
import json
import argparse
from jarvis.jarvis_utils.methodology import (
    _get_methodology_directory,
    _load_all_methodologies
)

def import_methodology(input_file):
    """导入方法论文件（合并策略）"""
    try:
        # 加载现有方法论
        existing_methodologies = _load_all_methodologies()

        # 加载要导入的方法论
        with open(input_file, "r", encoding="utf-8") as f:
            import_data = json.load(f)

        # 合并方法论（新数据会覆盖旧数据）
        merged_data = {**existing_methodologies, **import_data}

        # 保存合并后的方法论
        methodology_dir = _get_methodology_directory()
        for problem_type, content in merged_data.items():
            safe_filename = hashlib.md5(problem_type.encode('utf-8')).hexdigest()
            file_path = os.path.join(methodology_dir, f"{safe_filename}.json")

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump({
                    "problem_type": problem_type,
                    "content": content
                }, f, ensure_ascii=False, indent=2)

        print(f"成功导入 {len(import_data)} 个方法论（总计 {len(merged_data)} 个）")
    except (json.JSONDecodeError, OSError) as e:
        print(f"导入失败: {str(e)}")

def export_methodology(output_file):
    """导出当前方法论到单个文件"""
    try:
        methodologies = _load_all_methodologies()

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(methodologies, f, ensure_ascii=False, indent=2)

        print(f"成功导出 {len(methodologies)} 个方法论到 {output_file}")
    except (OSError, TypeError) as e:
        print(f"导出失败: {str(e)}")

def list_methodologies():
    """列出所有方法论"""
    try:
        methodologies = _load_all_methodologies()

        if not methodologies:
            print("没有找到方法论")
            return

        print("可用方法论:")
        for i, (problem_type, _) in enumerate(methodologies.items(), 1):
            print(f"{i}. {problem_type}")
    except (OSError, json.JSONDecodeError) as e:
        print(f"列出方法论失败: {str(e)}")

def main():
    """方法论管理工具主函数"""
    parser = argparse.ArgumentParser(description="方法论管理工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # import命令
    import_parser = subparsers.add_parser("import", help="导入方法论文件（合并策略）")
    import_parser.add_argument("input_file", type=str, help="要导入的方法论文件路径")

    # export命令
    export_parser = subparsers.add_parser("export", help="导出当前方法论到单个文件")
    export_parser.add_argument("output_file", type=str, help="导出文件路径")

    # list命令
    subparsers.add_parser("list", help="列出所有方法论")

    args = parser.parse_args()

    if args.command == "import":
        import_methodology(args.input_file)
    elif args.command == "export":
        export_methodology(args.output_file)
    elif args.command == "list":
        list_methodologies()

if __name__ == "__main__":
    main()
