import sys
import json
from typing import Optional

import typer
from tabulate import tabulate

from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import init_env

app = typer.Typer(help="Jarvis 工具系统命令行界面")


@app.command("list")
def list_tools(
    as_json: bool = typer.Option(False, "--json", help="以JSON格式输出"),
    detailed: bool = typer.Option(False, "--detailed", help="显示详细信息"),
):
    """列出所有可用工具"""
    registry = ToolRegistry()
    tools = registry.get_all_tools()

    if as_json:
        if detailed:
            print(json.dumps(tools, indent=2, ensure_ascii=False))
        else:
            simple_tools = [
                {"name": t["name"], "description": t["description"]} for t in tools
            ]
            print(json.dumps(simple_tools, indent=2, ensure_ascii=False))
    else:
        PrettyOutput.section("可用工具列表", OutputType.SYSTEM)
        for tool in tools:
            print(f"\n✅ {tool['name']}")
            print(f"   描述: {tool['description']}")
            if detailed:
                print("   参数:")
                print(tool["parameters"])


@app.command("stat")
def stat_tools(as_json: bool = typer.Option(False, "--json", help="以JSON格式输出")):
    """显示工具调用统计信息"""
    registry = ToolRegistry()
    stats = registry._get_tool_stats()
    tools = registry.get_all_tools()

    table_data = []
    for tool in tools:
        name = tool["name"]
        count = stats.get(name, 0)
        table_data.append([name, count])

    table_data.sort(key=lambda x: x[1], reverse=True)

    if as_json:
        print(json.dumps(dict(table_data), indent=2))
    else:
        PrettyOutput.section("工具调用统计", OutputType.SYSTEM)
        print(tabulate(table_data, headers=["工具名称", "调用次数"], tablefmt="grid"))


@app.command("call")
def call_tool(
    tool_name: str = typer.Argument(..., help="要调用的工具名称"),
    args: Optional[str] = typer.Option(None, "--args", help="工具参数 (JSON格式)"),
    args_file: Optional[str] = typer.Option(
        None, "--args-file", help="从文件加载工具参数 (JSON格式)"
    ),
):
    """调用指定工具"""
    registry = ToolRegistry()
    tool_obj = registry.get_tool(tool_name)

    if not tool_obj:
        PrettyOutput.print(f"错误: 工具 '{tool_name}' 不存在", OutputType.ERROR)
        available_tools = ", ".join([t["name"] for t in registry.get_all_tools()])
        print(f"可用工具: {available_tools}")
        raise typer.Exit(code=1)

    tool_args = {}
    if args:
        try:
            tool_args = json.loads(args)
        except json.JSONDecodeError:
            PrettyOutput.print("错误: 参数必须是有效的JSON格式", OutputType.ERROR)
            raise typer.Exit(code=1)
    elif args_file:
        try:
            with open(args_file, "r", encoding="utf-8") as f:
                tool_args = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            PrettyOutput.print(
                f"错误: 无法从文件加载参数: {str(e)}", OutputType.ERROR
            )
            raise typer.Exit(code=1)

    required_params = tool_obj.parameters.get("required", [])
    missing_params = [p for p in required_params if p not in tool_args]

    if missing_params:
        PrettyOutput.print(
            f"错误: 缺少必需参数: {', '.join(missing_params)}", OutputType.ERROR
        )
        print("\n参数说明:")
        params = tool_obj.parameters.get("properties", {})
        for param_name in required_params:
            param_info = params.get(param_name, {})
            desc = param_info.get("description", "无描述")
            print(f"  - {param_name}: {desc}")
        raise typer.Exit(code=1)

    result = registry.execute_tool(tool_name, tool_args)

    if result["success"]:
        PrettyOutput.section(f"工具 {tool_name} 执行成功", OutputType.SUCCESS)
    else:
        PrettyOutput.section(f"工具 {tool_name} 执行失败", OutputType.ERROR)

    if result.get("stdout"):
        print("\n输出:")
        print(result["stdout"])

    if result.get("stderr"):
        PrettyOutput.print("\n错误:", OutputType.ERROR)
        print(result["stderr"])

    if not result["success"]:
        raise typer.Exit(code=1)


def main():
    init_env("欢迎使用 Jarvis-Tools，您的工具系统已准备就绪！")
    app()


if __name__ == "__main__":
    main()
