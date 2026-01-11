"""
方法论导入导出命令行工具

功能：
- 导入方法论文件（合并策略）
- 导出当前方法论
- 列出所有方法论
"""

import hashlib
import json

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
import os
from typing import Any


import typer
import yaml

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.methodology import _get_methodology_directory
from jarvis.jarvis_utils.methodology import _get_project_methodology_directory
from jarvis.jarvis_utils.methodology import _load_all_methodologies
from jarvis.jarvis_utils.methodology import _load_methodologies_from_dir

app = typer.Typer(help="方法论管理工具")


@app.command("import")
def import_methodology(
    input_file: str = typer.Argument(..., help="要导入的方法论文件路径"),
    scope: str = typer.Option(
        "global",
        "--scope",
        "-s",
        help="方法论作用域：global（全局）或project（项目级），默认为global",
    ),
):
    """导入方法论文件（合并策略）"""
    try:
        # 验证 scope 参数
        if scope not in ["global", "project"]:
            PrettyOutput.auto_print(
                f"❌ 无效的scope参数: {scope}，必须是 'global' 或 'project'"
            )
            raise typer.Exit(code=1)

        # 根据scope选择存储目录
        if scope == "project":
            methodology_dir = _get_project_methodology_directory()
            if not methodology_dir:
                PrettyOutput.auto_print(
                    "❌ 无法获取项目级方法论目录，请确保在Git仓库中"
                )
                raise typer.Exit(code=1)
        else:
            methodology_dir = _get_methodology_directory()

        # 加载要导入的方法论
        with open(input_file, "r", encoding="utf-8") as f:
            import_data = json.load(f)

        # 加载现有方法论并合并（新数据覆盖旧数据）
        existing_methodologies = _load_methodologies_from_dir(methodology_dir)
        merged_data = {**existing_methodologies, **import_data}

        # 保存合并后的方法论
        for problem_type, content in merged_data.items():
            safe_filename = hashlib.md5(problem_type.encode("utf-8")).hexdigest()
            file_path = os.path.join(methodology_dir, f"{safe_filename}.json")

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"problem_type": problem_type, "content": content, "scope": scope},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

        PrettyOutput.auto_print(
            f"✅ 成功导入 {len(import_data)} 个{scope}方法论到 {methodology_dir}"
        )
    except (ValueError, OSError) as e:
        PrettyOutput.auto_print(f"❌ 导入失败: {str(e)}")
        raise typer.Exit(code=1)


@app.command("export")
def export_methodology(
    output_file: str = typer.Argument(..., help="导出文件路径"),
    scope: str = typer.Option(
        "all",
        "--scope",
        "-s",
        help="方法论作用域：global（全局）、project（项目级）或all（全部），默认为all",
    ),
):
    """导出当前方法论到单个文件"""
    try:
        # 验证 scope 参数
        if scope not in ["global", "project", "all"]:
            PrettyOutput.auto_print(
                f"❌ 无效的scope参数: {scope}，必须是 'global'、'project' 或 'all'"
            )
            raise typer.Exit(code=1)

        # 根据scope加载
        if scope == "all":
            methodologies: Any = _load_all_methodologies()
        elif scope == "project":
            project_dir = _get_project_methodology_directory()
            if not project_dir:
                PrettyOutput.auto_print(
                    "❌ 无法获取项目级方法论目录，请确保在Git仓库中"
                )
                raise typer.Exit(code=1)
            methodologies = _load_methodologies_from_dir(project_dir)
        else:  # global
            global_dir = _get_methodology_directory()
            methodologies = _load_methodologies_from_dir(global_dir)

        # 将结果转换为字典格式导出（支持 List[Tuple] 和 Dict 两种类型）
        export_data = (
            dict(methodologies)
            if not isinstance(methodologies, dict)
            else methodologies
        )
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        PrettyOutput.auto_print(
            f"✅ 成功导出 {len(methodologies)} 个{scope}方法论到 {output_file}"
        )
    except (OSError, TypeError) as e:
        PrettyOutput.auto_print(f"❌ 导出失败: {str(e)}")
        raise typer.Exit(code=1)


@app.command("list")
def list_methodologies(
    scope: str = typer.Option(
        "all",
        "--scope",
        "-s",
        help="方法论作用域：global（全局）、project（项目级）或all（全部），默认为all",
    ),
):
    """列出所有方法论"""
    try:
        # 验证 scope 参数
        if scope not in ["global", "project", "all"]:
            PrettyOutput.auto_print(
                f"❌ 无效的scope参数: {scope}，必须是 'global'、'project' 或 'all'"
            )
            raise typer.Exit(code=1)

        # 根据scope加载
        if scope == "all":
            methodologies: Any = _load_all_methodologies()
        elif scope == "project":
            project_dir = _get_project_methodology_directory()
            if not project_dir:
                PrettyOutput.auto_print("ℹ️ 无法获取项目级方法论目录，请确保在Git仓库中")
                return
            methodologies = _load_methodologies_from_dir(project_dir)
        else:  # global
            global_dir = _get_methodology_directory()
            methodologies = _load_methodologies_from_dir(global_dir)

        if not methodologies:
            PrettyOutput.auto_print(f"ℹ️ 没有找到{scope}方法论")
            return

        # 先拼接再统一打印，避免在循环中逐条输出造成信息稀疏
        lines = [f"可用{scope}方法论:"]
        # 兼容 List[Tuple] 和 Dict 两种类型
        if isinstance(methodologies, dict):
            for i, problem_type in enumerate(methodologies.keys(), 1):
                lines.append(f"{i}. {problem_type}")
        else:
            for i, (problem_type, _) in enumerate(methodologies, 1):
                lines.append(f"{i}. {problem_type}")
        joined_lines = "\n".join(lines)
        PrettyOutput.auto_print(f"ℹ️ {joined_lines}")
    except (OSError, ValueError) as e:
        PrettyOutput.auto_print(f"❌ 列出方法论失败: {str(e)}")
        raise typer.Exit(code=1)


@app.command("extract")
def extract_methodology(
    input_file: str = typer.Argument(..., help="要提取方法论的文本文件路径"),
    scope: str = typer.Option(
        "global",
        "--scope",
        "-s",
        help="方法论作用域：global（全局）或project（项目级），默认为global",
    ),
):
    """从文本文件中提取方法论"""
    try:
        # 验证 scope 参数
        if scope not in ["global", "project"]:
            PrettyOutput.auto_print(
                f"❌ 无效的scope参数: {scope}，必须是 'global' 或 'project'"
            )
            raise typer.Exit(code=1)

        # 根据scope选择存储目录
        if scope == "project":
            methodology_dir = _get_project_methodology_directory()
            if not methodology_dir:
                PrettyOutput.auto_print(
                    "❌ 无法获取项目级方法论目录，请确保在Git仓库中"
                )
                raise typer.Exit(code=1)
        else:
            methodology_dir = _get_methodology_directory()

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
        PrettyOutput.auto_print("ℹ️ 正在提取方法论...")
        try:
            response = platform.chat_until_success(prompt)
        except Exception as e:
            PrettyOutput.auto_print("❌ 提取失败")
            PrettyOutput.auto_print(f"❌ 提取方法论失败: {str(e)}")
            raise typer.Exit(code=1)

        # 提取YAML部分
        methodologies_start = response.find("<methodologies>") + len("<methodologies>")
        methodologies_end = response.find("</methodologies>")
        if methodologies_start == -1 or methodologies_end == -1:
            PrettyOutput.auto_print("❌ 响应格式无效")
            PrettyOutput.auto_print("❌ 大模型未返回有效的<methodologies>格式")
            raise typer.Exit(code=1)

        yaml_content = response[methodologies_start:methodologies_end].strip()

        try:
            data = yaml.safe_load(yaml_content)
            extracted_methodologies = {
                item["problem_type"]: item["content"] for item in data
            }
        except (yaml.YAMLError, KeyError, TypeError) as e:
            PrettyOutput.auto_print("❌ YAML解析失败")
            PrettyOutput.auto_print(f"❌ YAML解析错误: {str(e)}")
            raise typer.Exit(code=1)

        if not extracted_methodologies:
            PrettyOutput.auto_print("⚠️ 未提取到有效方法论")
            return
        PrettyOutput.auto_print("✅ 提取到有效方法论")

        # 加载现有方法论并合并（新数据覆盖旧数据）
        existing_methodologies = _load_methodologies_from_dir(methodology_dir)
        merged_data = {**existing_methodologies, **extracted_methodologies}

        # 保存合并后的方法论
        for problem_type, content in merged_data.items():
            safe_filename = hashlib.md5(problem_type.encode("utf-8")).hexdigest()
            file_path = os.path.join(methodology_dir, f"{safe_filename}.json")

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"problem_type": problem_type, "content": content, "scope": scope},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

        PrettyOutput.auto_print(
            f"✅ 成功从文件提取 {len(extracted_methodologies)} 个{scope}方法论到 {methodology_dir}"
        )
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 提取失败: {str(e)}")
        raise typer.Exit(code=1)


@app.command("extract-url")
def extract_methodology_from_url(
    url: str = typer.Argument(..., help="要提取方法论的URL"),
    scope: str = typer.Option(
        "global",
        "--scope",
        "-s",
        help="方法论作用域：global（全局）或project（项目级），默认为global",
    ),
):
    """从URL提取方法论"""
    try:
        # 验证 scope 参数
        if scope not in ["global", "project"]:
            PrettyOutput.auto_print(
                f"❌ 无效的scope参数: {scope}，必须是 'global' 或 'project'"
            )
            raise typer.Exit(code=1)

        # 根据scope选择存储目录
        if scope == "project":
            methodology_dir = _get_project_methodology_directory()
            if not methodology_dir:
                PrettyOutput.auto_print(
                    "❌ 无法获取项目级方法论目录，请确保在Git仓库中"
                )
                raise typer.Exit(code=1)
        else:
            methodology_dir = _get_methodology_directory()

        # 获取平台实例
        platform = PlatformRegistry().get_normal_platform()

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
        PrettyOutput.auto_print("ℹ️ 正在从URL提取方法论...")
        try:
            response = platform.chat_until_success(prompt)
        except Exception as e:
            PrettyOutput.auto_print("❌ 提取失败")
            PrettyOutput.auto_print(f"❌ 提取方法论失败: {str(e)}")
            raise typer.Exit(code=1)

        # 提取YAML部分
        methodologies_start = response.find("<methodologies>") + len("<methodologies>")
        methodologies_end = response.find("</methodologies>")
        if methodologies_start == -1 or methodologies_end == -1:
            PrettyOutput.auto_print("❌ 响应格式无效")
            PrettyOutput.auto_print("❌ 大模型未返回有效的<methodologies>格式")
            raise typer.Exit(code=1)

        yaml_content = response[methodologies_start:methodologies_end].strip()

        try:
            data = yaml.safe_load(yaml_content)
            extracted_methodologies = {
                item["problem_type"]: item["content"] for item in data
            }
        except (yaml.YAMLError, KeyError, TypeError) as e:
            PrettyOutput.auto_print("❌ YAML解析失败")
            PrettyOutput.auto_print(f"❌ YAML解析错误: {str(e)}")
            raise typer.Exit(code=1)

        if not extracted_methodologies:
            PrettyOutput.auto_print("⚠️ 未提取到有效方法论")
            return
        PrettyOutput.auto_print("✅ 提取到有效方法论")

        # 加载现有方法论并合并（新数据覆盖旧数据）
        existing_methodologies = _load_methodologies_from_dir(methodology_dir)
        merged_data = {**existing_methodologies, **extracted_methodologies}

        # 保存合并后的方法论
        for problem_type, content in merged_data.items():
            safe_filename = hashlib.md5(problem_type.encode("utf-8")).hexdigest()
            file_path = os.path.join(methodology_dir, f"{safe_filename}.json")

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"problem_type": problem_type, "content": content, "scope": scope},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

        PrettyOutput.auto_print(
            f"✅ 成功从URL提取 {len(extracted_methodologies)} 个{scope}方法论到 {methodology_dir}"
        )
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 从URL提取失败: {str(e)}")
        raise typer.Exit(code=1)


def main() -> None:
    """Application entry point"""
    app()


if __name__ == "__main__":
    main()
