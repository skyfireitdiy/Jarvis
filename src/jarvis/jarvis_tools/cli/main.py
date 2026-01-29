import json
from typing import Optional

import typer

from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.output import OutputType
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.utils import init_env

app = typer.Typer(help="Jarvis 工具系统命令行界面")


@app.command("list")
def list_tools(
    as_json: bool = typer.Option(False, "--json", help="以JSON格式输出"),
    detailed: bool = typer.Option(False, "--detailed", help="显示详细信息"),
) -> None:
    """列出所有可用工具"""
    registry = ToolRegistry()
    tools = registry.get_all_tools()

    if as_json:
        if detailed:
            PrettyOutput.print(
                json.dumps(tools, indent=2, ensure_ascii=False),
                OutputType.CODE,
                lang="json",
            )
        else:
            simple_tools = [
                {"name": t["name"], "description": t["description"]} for t in tools
            ]
            PrettyOutput.print(
                json.dumps(simple_tools, indent=2, ensure_ascii=False),
                OutputType.CODE,
                lang="json",
            )
    else:
        PrettyOutput.auto_print("📋 可用工具列表")
        # 为避免 PrettyOutput 对每行加框造成信息稀疏，先拼接字符串再统一打印
        lines = []
        import json as _json  # local import to ensure available

        for tool in tools:
            lines.append(f"\n{tool['name']}")
            lines.append(f"   描述: {tool['description']}")
            if detailed:
                lines.append("   参数:")
                # 使用 Markdown 代码块统一展示参数
                lines.append("```json")
                try:
                    lines.append(
                        _json.dumps(tool["parameters"], ensure_ascii=False, indent=2)
                    )
                except Exception:
                    lines.append(str(tool.get("parameters")))
                lines.append("```")
        PrettyOutput.print("\n".join(lines), OutputType.CODE, lang="markdown")


@app.command("stat")
def stat_tools(
    as_json: bool = typer.Option(False, "--json", help="以JSON格式输出"),
    last_days: Optional[int] = typer.Option(
        None, "--days", help="显示最近N天的统计（默认显示所有历史数据）"
    ),
    format: str = typer.Option(
        "table", "--format", help="显示格式: table, chart, summary"
    ),
) -> None:
    """显示工具调用统计信息（已废弃，jarvis-stats功能已移除）"""
    PrettyOutput.auto_print("⚠️ jarvis-stats 功能已移除，此命令不再可用")


@app.command("call")
def call_tool(
    tool_name: str = typer.Argument(..., help="要调用的工具名称"),
    args: Optional[str] = typer.Option(None, "--args", help="工具参数 (JSON格式)"),
    args_file: Optional[str] = typer.Option(
        None, "--args-file", help="从文件加载工具参数 (JSON格式)"
    ),
) -> None:
    """调用指定工具"""
    registry = ToolRegistry()
    tool_obj = registry.get_tool(tool_name)

    if not tool_obj:
        PrettyOutput.auto_print(f"❌ 错误: 工具 '{tool_name}' 不存在")
        available_tools = ", ".join([t["name"] for t in registry.get_all_tools()])
        PrettyOutput.auto_print(f"ℹ️ 可用工具: {available_tools}")
        raise typer.Exit(code=1)

    tool_args = {}
    if args:
        try:
            tool_args = json.loads(args)
        except Exception:
            PrettyOutput.auto_print("❌ 错误: 参数必须是有效的JSON格式")
            raise typer.Exit(code=1)
    elif args_file:
        try:
            with open(args_file, "r", encoding="utf-8") as f:
                tool_args = json.load(f)
        except (Exception, FileNotFoundError) as e:
            PrettyOutput.auto_print(f"❌ 错误: 无法从文件加载参数: {str(e)}")
            raise typer.Exit(code=1)

    required_params = tool_obj.parameters.get("required", [])
    missing_params = [p for p in required_params if p not in tool_args]

    if missing_params:
        # 先拼接提示与参数说明，再统一打印，避免循环中逐条打印
        params = tool_obj.parameters.get("properties", {})
        lines = [
            f"错误: 缺少必需参数: {', '.join(missing_params)}",
            "",
            "参数说明:",
        ]
        for param_name in required_params:
            param_info = params.get(param_name, {})
            desc = param_info.get("description", "无描述")
            lines.append(f"  - {param_name}: {desc}")
        PrettyOutput.auto_print("❌ " + "\n❌ ".join(lines))
        raise typer.Exit(code=1)

    result = registry.execute_tool(tool_name, tool_args)

    if result["success"]:
        PrettyOutput.auto_print(f"✅ 工具 {tool_name} 执行成功")
    else:
        PrettyOutput.auto_print(f"❌ 工具 {tool_name} 执行失败")

    if result.get("stdout"):
        PrettyOutput.auto_print("📤 输出:")
        PrettyOutput.print(result["stdout"], OutputType.CODE, lang="text")

    if result.get("stderr"):
        PrettyOutput.auto_print("❌ 错误:")
        PrettyOutput.print(result["stderr"], OutputType.CODE, lang="text")

    if not result["success"]:
        raise typer.Exit(code=1)


def cli() -> None:
    """Typer application entry point"""
    init_env()
    app()


def main() -> None:
    """Main entry point for the script"""
    cli()


if __name__ == "__main__":
    main()
