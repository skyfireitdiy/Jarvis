# -*- coding: utf-8 -*-
"""
方法论导入导出命令行工具

功能：
- 导入方法论文件（合并策略）
- 导出当前方法论
- 列出所有方法论
"""

import argparse
import hashlib
import json
import os

import yaml  # type: ignore

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.methodology import (
    _get_methodology_directory,
    _load_all_methodologies,
)
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


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
            safe_filename = hashlib.md5(problem_type.encode("utf-8")).hexdigest()
            file_path = os.path.join(methodology_dir, f"{safe_filename}.json")

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"problem_type": problem_type, "content": content},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

        PrettyOutput.print(
            f"成功导入 {len(import_data)} 个方法论（总计 {len(merged_data)} 个）",
            OutputType.SUCCESS,
        )
    except (json.JSONDecodeError, OSError) as e:
        PrettyOutput.print(f"导入失败: {str(e)}", OutputType.ERROR)


def export_methodology(output_file):
    """导出当前方法论到单个文件"""
    try:
        methodologies = _load_all_methodologies()

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(methodologies, f, ensure_ascii=False, indent=2)

        PrettyOutput.print(
            f"成功导出 {len(methodologies)} 个方法论到 {output_file}",
            OutputType.SUCCESS,
        )
    except (OSError, TypeError) as e:
        PrettyOutput.print(f"导出失败: {str(e)}", OutputType.ERROR)


def list_methodologies():
    """列出所有方法论"""
    try:
        methodologies = _load_all_methodologies()

        if not methodologies:
            PrettyOutput.print("没有找到方法论", OutputType.INFO)
            return

        PrettyOutput.print("可用方法论:", OutputType.INFO)
        for i, (problem_type, _) in enumerate(methodologies.items(), 1):
            PrettyOutput.print(f"{i}. {problem_type}", OutputType.INFO)
    except (OSError, json.JSONDecodeError) as e:
        PrettyOutput.print(f"列出方法论失败: {str(e)}", OutputType.ERROR)


def extract_methodology(input_file):
    """从文本文件中提取方法论"""
    try:
        # 读取文本文件内容
        with open(input_file, "r", encoding="utf-8") as f:
            text_content = f.read()

        # 获取平台实例
        platform = PlatformRegistry().get_normal_platform()

        # 构建提取提示
        prompt = f"""请从以下文本中提取方法论：
        
{text_content}

请按以下格式返回结果：
<methodologies>
- problem_type: [问题类型1]
  content: |2
    [多行方法论内容1]
- problem_type: [问题类型2]
  content: |2
    [多行方法论内容2]
</methodologies>

要求：
1. 方法论应聚焦于通用且可重复的解决方案流程
2. 方法论应该具备足够的通用性，可应用于同类问题
3. 方法论内容应包含：
   - 问题重述: 简明扼要的问题归纳
   - 最优解决方案: 经过验证的解决方案
   - 注意事项: 执行中可能遇到的问题
   - 可选步骤: 多种解决路径和适用场景
4. 在<methodologies>标签中直接使用YAML列表
5. 确保YAML缩进正确
6. 内容字段使用|保留多行格式
"""

        # 调用大模型平台提取方法论
        print("📥 正在提取方法论...")
        try:
            response = platform.chat_until_success(prompt)
        except Exception as e:
            print("❌ 提取失败")
            PrettyOutput.print(f"提取方法论失败: {str(e)}", OutputType.ERROR)
            return

        # 提取YAML部分
        methodologies_start = response.find("<methodologies>") + len("<methodologies>")
        methodologies_end = response.find("</methodologies>")
        if methodologies_start == -1 or methodologies_end == -1:
            print("❌ 响应格式无效")
            PrettyOutput.print(
                "大模型未返回有效的<methodologies>格式", OutputType.ERROR
            )
            return

        yaml_content = response[methodologies_start:methodologies_end].strip()

        try:
            data = yaml.safe_load(yaml_content)
            extracted_methodologies = {
                item["problem_type"]: item["content"] for item in data
            }
        except (yaml.YAMLError, KeyError, TypeError) as e:
            print("❌ YAML解析失败")
            PrettyOutput.print(f"YAML解析错误: {str(e)}", OutputType.ERROR)
            return

        if not extracted_methodologies:
            print("❌ 未提取到有效方法论")
            return
        print("✅ 提取到有效方法论")

        # 加载现有方法论
        existing_methodologies = _load_all_methodologies()

        # 合并方法论（新数据会覆盖旧数据）
        merged_data = {**existing_methodologies, **extracted_methodologies}

        # 保存合并后的方法论
        methodology_dir = _get_methodology_directory()
        for problem_type, content in merged_data.items():
            safe_filename = hashlib.md5(problem_type.encode("utf-8")).hexdigest()
            file_path = os.path.join(methodology_dir, f"{safe_filename}.json")

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"problem_type": problem_type, "content": content},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

        PrettyOutput.print(
            f"成功从文件提取 {len(extracted_methodologies)} 个方法论（总计 {len(merged_data)} 个）",
            OutputType.SUCCESS,
        )
    except Exception as e:
        PrettyOutput.print(f"提取失败: {str(e)}", OutputType.ERROR)


def extract_methodology_from_url(url):
    """从URL提取方法论"""
    try:
        # 获取平台实例
        platform = PlatformRegistry().get_normal_platform()

        platform.web = True

        # 构建提取提示
        prompt = f"""请从以下URL内容中提取方法论：
        
{url}

请按以下格式返回结果：
<methodologies>
- problem_type: [问题类型1]
  content: |2
    [多行方法论内容1]
- problem_type: [问题类型2]
  content: |2
    [多行方法论内容2]
</methodologies>

要求：
1. 方法论应聚焦于通用且可重复的解决方案流程
2. 方法论应该具备足够的通用性，可应用于同类问题
3. 方法论内容应包含：
   - 问题重述: 简明扼要的问题归纳
   - 最优解决方案: 经过验证的解决方案
   - 注意事项: 执行中可能遇到的问题
   - 可选步骤: 多种解决路径和适用场景
4. 在<methodologies>标签中直接使用YAML列表
5. 确保YAML缩进正确
6. 内容字段使用|保留多行格式
"""
        # 调用大模型平台提取方法论
        print("📥 正在从URL提取方法论...")
        try:
            response = platform.chat_until_success(prompt)
        except Exception as e:
            print("❌ 提取失败")
            PrettyOutput.print(f"提取方法论失败: {str(e)}", OutputType.ERROR)
            return

        # 提取YAML部分
        methodologies_start = response.find("<methodologies>") + len("<methodologies>")
        methodologies_end = response.find("</methodologies>")
        if methodologies_start == -1 or methodologies_end == -1:
            print("❌ 响应格式无效")
            PrettyOutput.print(
                "大模型未返回有效的<methodologies>格式", OutputType.ERROR
            )
            return

        yaml_content = response[methodologies_start:methodologies_end].strip()

        try:
            data = yaml.safe_load(yaml_content)
            extracted_methodologies = {
                item["problem_type"]: item["content"] for item in data
            }
        except (yaml.YAMLError, KeyError, TypeError) as e:
            print("❌ YAML解析失败")
            PrettyOutput.print(f"YAML解析错误: {str(e)}", OutputType.ERROR)
            return

        if not extracted_methodologies:
            print("❌ 未提取到有效方法论")
            return
        print("✅ 提取到有效方法论")

        # 加载现有方法论
        existing_methodologies = _load_all_methodologies()

        # 合并方法论（新数据会覆盖旧数据）
        merged_data = {**existing_methodologies, **extracted_methodologies}

        # 保存合并后的方法论
        methodology_dir = _get_methodology_directory()
        for problem_type, content in merged_data.items():
            safe_filename = hashlib.md5(problem_type.encode("utf-8")).hexdigest()
            file_path = os.path.join(methodology_dir, f"{safe_filename}.json")

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"problem_type": problem_type, "content": content},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

        PrettyOutput.print(
            f"成功从URL提取 {len(extracted_methodologies)} 个方法论（总计 {len(merged_data)} 个）",
            OutputType.SUCCESS,
        )
    except Exception as e:
        PrettyOutput.print(f"从URL提取失败: {str(e)}", OutputType.ERROR)


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

    # extract命令
    extract_parser = subparsers.add_parser("extract", help="从文本文件中提取方法论")
    extract_parser.add_argument(
        "input_file", type=str, help="要提取方法论的文本文件路径"
    )

    # extract-url命令
    extract_url_parser = subparsers.add_parser("extract-url", help="从URL提取方法论")
    extract_url_parser.add_argument("url", type=str, help="要提取方法论的URL")

    args = parser.parse_args()

    if args.command == "import":
        import_methodology(args.input_file)
    elif args.command == "export":
        export_methodology(args.output_file)
    elif args.command == "list":
        list_methodologies()
    elif args.command == "extract":
        extract_methodology(args.input_file)
    elif args.command == "extract-url":
        extract_methodology_from_url(args.url)


if __name__ == "__main__":
    main()
