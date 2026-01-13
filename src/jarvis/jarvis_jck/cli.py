# -*- coding: utf-8 -*-
"""Jarvis Check - jck CLI命令接口

提供命令行接口用于检查系统工具的安装情况。
"""

import sys
from typing import Optional

import typer

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


def _print_results(results: list, summary: dict) -> None:
    """打印检查结果

    参数:
        results: 工具检查结果列表
        summary: 摘要统计
    """
    # 标题
    PrettyOutput.auto_print("🔍 Jarvis Check - 工具检查结果")

    # 分隔线
    PrettyOutput.print("=" * 60, OutputType.INFO)

    # 摘要
    total = summary["total"]
    found = summary["found"]
    missing = summary["missing"]

    PrettyOutput.auto_print(f"总计: {total} | 已安装: {found} | 未安装: {missing}")

    # 分隔线
    PrettyOutput.print("=" * 60, OutputType.INFO)

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
        PrettyOutput.print(
            "❌ 错误：--check-lint 和 --check-build 选项不能同时使用", OutputType.ERROR
        )
        sys.exit(1)

    if tool_name:
        # 检查单个工具（优先于其他选项）
        result = checker.check_single_tool(tool_name)
        results = [result]
        summary = checker.get_summary(results)
    elif check_lint:
        # 检查lint工具
        results = checker.check_lint_tools()
        summary = checker.get_summary(results)
    elif check_build:
        # 检查构建工具
        results = checker.check_build_tools()
        summary = checker.get_summary(results)
    else:
        # 检查所有工具（默认行为）
        results = checker.check_all_tools()
        summary = checker.get_summary(results)

    if as_json:
        # JSON格式输出
        import json

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
        _print_results(results, summary)

    # 如果有工具未安装，返回非零退出码
    if summary["missing"] > 0:
        sys.exit(1)


def main() -> None:
    """主入口函数"""
    app()


if __name__ == "__main__":
    main()
