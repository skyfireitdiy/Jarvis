# -*- coding: utf-8 -*-
"""Jarvis Check - jck CLI命令接口

提供命令行接口用于检查系统工具的安装情况。
"""

import sys
import subprocess
import json
from typing import Optional

import typer
from typer import confirm

from jarvis.jarvis_jck.core import ToolChecker
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

# 创建 typer 应用
app = typer.Typer(help="Jarvis Check - 检查系统工具的安装情况，提供友好的安装建议")


def _format_tool_result(result: dict) -> str:
    """格式化单个工具的检查结果

    参数:
        result: 工具检查结果字典

    返回:
        格式化后的字符串
    """
    name = result["name"]
    description = result["description"]
    found = result["found"]
    version = result["version"]

    # 状态图标
    status_icon = "✅" if found else "❌"

    # 工具名称和描述
    lines = [f"{status_icon} {name} - {description}"]

    # 版本信息
    if found and version:
        lines.append(f"   版本: {version}")

    # 安装建议
    if not found:
        install_hint = result["install_hint"]
        lines.append("   💡 安装建议:")
        for hint_line in install_hint.strip().split("\n"):
            lines.append(f"      {hint_line}")

    return "\n".join(lines)


def _install_missing_tools(results: list) -> None:
    """安装未安装的工具

    参数:
        results: 工具检查结果列表
    """
    # 找出所有未安装的工具
    missing_tools = [r for r in results if not r["found"]]

    if not missing_tools:
        return

    # 构建工具名称列表（用于用户显示）
    tool_names = [r["name"] for r in missing_tools]
    tool_names_str = "、".join(tool_names)

    # 询问用户是否自动安装
    PrettyOutput.auto_print(
        f"\n⚠️  检测到 {len(missing_tools)} 个工具未安装: {tool_names_str}"
    )
    if not confirm("是否需要自动安装这些工具？", default=True):
        PrettyOutput.auto_print("ℹ️  跳过自动安装")
        return

    # 批量安装工具
    PrettyOutput.auto_print("\n🚀 开始自动安装工具...")

    # 构建包含完整工具配置的描述

    # 构建结构化的工具信息，便于大模型理解
    tools_info = []
    for tool in missing_tools:
        tools_info.append(
            {
                "name": tool["name"],
                "description": tool["description"],
                "install_hint": tool["install_hint"],
            }
        )

    # 将工具信息格式化为清晰的描述
    tools_json = json.dumps(tools_info, ensure_ascii=False, indent=2)
    combined_description = (
        f"请帮我安装以下 {len(missing_tools)} 个工具：\n\n"
        f"工具信息：\n"
        f"```json\n"
        f"{tools_json}\n"
        f"```\n\n"
        f"请根据每个工具的 install_hint 信息执行安装命令。"
    )

    try:
        # 使用 jvs -T 命令批量安装工具，传递完整的工具配置信息
        cmd = ["jvs", "-T", combined_description]
        subprocess.run(cmd)

    except FileNotFoundError:
        # jvs命令不存在，无法继续安装
        PrettyOutput.auto_print("❌ 找不到 'jvs' 命令，无法继续安装工具")
        PrettyOutput.auto_print("   请确保 jarvis 已正确安装后再试")
    except Exception as e:
        # 其他异常
        PrettyOutput.auto_print(f"❌ 批量安装时出错: {e}")

    PrettyOutput.auto_print("\n🔍 正在重新检查工具安装状态...")


def _print_results(results: list, summary: dict) -> None:
    """打印检查结果

    参数:
        results: 工具检查结果列表
        summary: 摘要统计
    """
    # 标题
    PrettyOutput.auto_print("🔍 Jarvis Check - 工具检查结果")

    # 分隔线
    PrettyOutput.auto_print("=" * 60)

    # 摘要
    total = summary["total"]
    found = summary["found"]
    missing = summary["missing"]

    PrettyOutput.auto_print(f"总计: {total} | 已安装: {found} | 未安装: {missing}")

    # 分隔线
    PrettyOutput.auto_print("=" * 60)

    # 每个工具的结果
    for result in results:
        formatted = _format_tool_result(result)
        PrettyOutput.print(
            formatted, OutputType.CODE if result["found"] else OutputType.ERROR
        )

    # 总结
    if missing > 0:
        PrettyOutput.auto_print(
            f"\n⚠️  发现 {missing} 个工具未安装，建议安装以获得更好的用户体验"
        )
    else:
        PrettyOutput.auto_print("\n✨ 所有工具都已安装！")


def _perform_check(
    checker: ToolChecker,
    tool_name: Optional[str],
    check_lint: bool,
    check_build: bool,
) -> tuple:
    """执行工具检查

    参数:
        checker: ToolChecker实例
        tool_name: 要检查的工具名称
        check_lint: 是否检查lint工具
        check_build: 是否检查构建工具

    返回:
        (results, summary) 元组
    """
    if tool_name:
        # 检查单个工具（优先于其他选项）
        result = checker.check_single_tool(tool_name)
        results = [result]
    elif check_lint:
        # 检查lint工具
        results = checker.check_lint_tools()
    elif check_build:
        # 检查构建工具
        results = checker.check_build_tools()
    else:
        # 检查所有工具（默认行为）
        results = checker.check_all_tools()

    summary = checker.get_summary(results)
    return results, summary


@app.command()
def check(
    tool_name: Optional[str] = typer.Argument(
        None, help="要检查的工具名称（可选），不指定则检查所有工具"
    ),
    as_json: bool = typer.Option(False, "--json", "-j", help="以JSON格式输出结果"),
    check_lint: bool = typer.Option(False, "--check-lint", "-l", help="检查lint工具"),
    check_build: bool = typer.Option(False, "--check-build", "-b", help="检查构建工具"),
) -> None:
    """检查工具安装情况

    不指定工具名称时检查所有工具，指定时只检查单个工具。
    """
    checker = ToolChecker()

    # 检查选项互斥
    check_flags = [check_lint, check_build]
    active_flags = sum(check_flags)
    if active_flags > 1:
        PrettyOutput.auto_print(
            "❌ 错误：--check-lint 和 --check-build 选项不能同时使用"
        )
        sys.exit(1)

    # 执行初始检查
    results, summary = _perform_check(checker, tool_name, check_lint, check_build)

    if as_json:
        # JSON格式输出：不询问安装，直接输出结果

        output = {
            "summary": summary,
            "results": results,
        }
        PrettyOutput.print(
            json.dumps(output, ensure_ascii=False, indent=2),
            OutputType.CODE,
            lang="json",
        )
    else:
        # 友好的文本输出
        # 如果有未安装工具，询问是否自动安装
        if summary["missing"] > 0:
            _install_missing_tools(results)
            # 重新检查工具状态（使用相同的检查逻辑确保一致性）
            results, summary = _perform_check(
                checker, tool_name, check_lint, check_build
            )

        # 输出最终结果
        _print_results(results, summary)

    # 如果有工具未安装，返回非零退出码
    if summary["missing"] > 0:
        sys.exit(1)


def main() -> None:
    """主入口函数"""
    app()


if __name__ == "__main__":
    main()
