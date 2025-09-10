# -*- coding: utf-8 -*-
"""
方法论导入导出命令行工具

功能：
- 导入方法论文件（合并策略）
- 导出当前方法论
- 列出所有方法论
"""

import hashlib
import json
import os

import typer
import yaml  # type: ignore

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.methodology import (
    _get_methodology_directory,
    _load_all_methodologies,
)
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

app = typer.Typer(help="方法论管理工具")


@app.command("import")
def import_methodology(
    input_file: str = typer.Argument(..., help="要导入的方法论文件路径")
):
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
        raise typer.Exit(code=1)


@app.command("export")
def export_methodology(output_file: str = typer.Argument(..., help="导出文件路径")):
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
        raise typer.Exit(code=1)


@app.command("list")
def list_methodologies():
    """列出所有方法论"""
    try:
        methodologies = _load_all_methodologies()

        if not methodologies:
            PrettyOutput.print("没有找到方法论", OutputType.INFO)
            return

        # 先拼接再统一打印，避免在循环中逐条输出造成信息稀疏
        lines = ["可用方法论:"]
        for i, (problem_type, _) in enumerate(methodologies.items(), 1):
            lines.append(f"{i}. {problem_type}")
        PrettyOutput.print("\n".join(lines), OutputType.INFO)
    except (OSError, json.JSONDecodeError) as e:
        PrettyOutput.print(f"列出方法论失败: {str(e)}", OutputType.ERROR)
        raise typer.Exit(code=1)


@app.command("extract")
def extract_methodology(
    input_file: str = typer.Argument(..., help="要提取方法论的文本文件路径")
):
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
        PrettyOutput.print("正在提取方法论...", OutputType.INFO)
        try:
            response = platform.chat_until_success(prompt)
        except Exception as e:
            PrettyOutput.print("提取失败", OutputType.ERROR)
            PrettyOutput.print(f"提取方法论失败: {str(e)}", OutputType.ERROR)
            raise typer.Exit(code=1)

        # 提取YAML部分
        methodologies_start = response.find("<methodologies>") + len("<methodologies>")
        methodologies_end = response.find("</methodologies>")
        if methodologies_start == -1 or methodologies_end == -1:
            PrettyOutput.print("响应格式无效", OutputType.ERROR)
            PrettyOutput.print(
                "大模型未返回有效的<methodologies>格式", OutputType.ERROR
            )
            raise typer.Exit(code=1)

        yaml_content = response[methodologies_start:methodologies_end].strip()

        try:
            data = yaml.safe_load(yaml_content)
            extracted_methodologies = {
                item["problem_type"]: item["content"] for item in data
            }
        except (yaml.YAMLError, KeyError, TypeError) as e:
            PrettyOutput.print("YAML解析失败", OutputType.ERROR)
            PrettyOutput.print(f"YAML解析错误: {str(e)}", OutputType.ERROR)
            raise typer.Exit(code=1)

        if not extracted_methodologies:
            PrettyOutput.print("未提取到有效方法论", OutputType.WARNING)
            return
        PrettyOutput.print("提取到有效方法论", OutputType.SUCCESS)

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
        raise typer.Exit(code=1)


@app.command("extract-url")
def extract_methodology_from_url(
    url: str = typer.Argument(..., help="要提取方法论的URL")
):
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
        PrettyOutput.print("正在从URL提取方法论...", OutputType.INFO)
        try:
            response = platform.chat_until_success(prompt)
        except Exception as e:
            PrettyOutput.print("提取失败", OutputType.ERROR)
            PrettyOutput.print(f"提取方法论失败: {str(e)}", OutputType.ERROR)
            raise typer.Exit(code=1)

        # 提取YAML部分
        methodologies_start = response.find("<methodologies>") + len("<methodologies>")
        methodologies_end = response.find("</methodologies>")
        if methodologies_start == -1 or methodologies_end == -1:
            PrettyOutput.print("响应格式无效", OutputType.ERROR)
            PrettyOutput.print(
                "大模型未返回有效的<methodologies>格式", OutputType.ERROR
            )
            raise typer.Exit(code=1)

        yaml_content = response[methodologies_start:methodologies_end].strip()

        try:
            data = yaml.safe_load(yaml_content)
            extracted_methodologies = {
                item["problem_type"]: item["content"] for item in data
            }
        except (yaml.YAMLError, KeyError, TypeError) as e:
            PrettyOutput.print("YAML解析失败", OutputType.ERROR)
            PrettyOutput.print(f"YAML解析错误: {str(e)}", OutputType.ERROR)
            raise typer.Exit(code=1)

        if not extracted_methodologies:
            PrettyOutput.print("未提取到有效方法论", OutputType.WARNING)
            return
        PrettyOutput.print("提取到有效方法论", OutputType.SUCCESS)

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
        raise typer.Exit(code=1)


def main() -> None:
    """Application entry point"""
    app()


if __name__ == "__main__":
    main()
