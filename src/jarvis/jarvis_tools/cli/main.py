import sys

from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import init_env


def main() -> int:
    """
    命令行工具入口，提供工具列表查看和工具调用功能

    功能:
        1. 列出所有可用工具 (list命令)
        2. 调用指定工具 (call命令)

    参数:
        通过命令行参数传递，包括:
        - list: 列出工具
            --json: 以JSON格式输出
            --detailed: 显示详细信息
        - call: 调用工具
            tool_name: 工具名称
            --args: 工具参数(JSON格式)
            --args-file: 从文件加载工具参数

    返回值:
        int: 0表示成功，非0表示错误
    """
    import argparse
    import json

    init_env("欢迎使用 Jarvis-Tools，您的工具系统已准备就绪！")

    parser = argparse.ArgumentParser(description="Jarvis 工具系统命令行界面")
    subparsers = parser.add_subparsers(dest="command", help="命令")

    # 列出工具子命令
    list_parser = subparsers.add_parser("list", help="列出所有可用工具")
    list_parser.add_argument("--json", action="store_true", help="以JSON格式输出")
    list_parser.add_argument("--detailed", action="store_true", help="显示详细信息")

    # 调用工具子命令
    call_parser = subparsers.add_parser("call", help="调用指定工具")
    call_parser.add_argument("tool_name", help="要调用的工具名称")
    call_parser.add_argument("--args", type=str, help="工具参数 (JSON格式)")
    call_parser.add_argument(
        "--args-file", type=str, help="从文件加载工具参数 (JSON格式)"
    )

    # 统计子命令
    stat_parser = subparsers.add_parser("stat", help="显示工具调用统计信息")
    stat_parser.add_argument("--json", action="store_true", help="以JSON格式输出")

    args = parser.parse_args()

    # 初始化工具注册表
    registry = ToolRegistry()

    if args.command == "list":
        tools = registry.get_all_tools()  # 从注册表获取所有工具信息

        if args.json:
            if args.detailed:
                print(
                    json.dumps(tools, indent=2, ensure_ascii=False)
                )  # 输出完整JSON格式
            else:
                simple_tools = [
                    {"name": t["name"], "description": t["description"]} for t in tools
                ]  # 简化工具信息
                print(json.dumps(simple_tools, indent=2, ensure_ascii=False))
        else:
            PrettyOutput.section("可用工具列表", OutputType.SYSTEM)  # 使用美化输出
            for tool in tools:
                print(f"\n✅ {tool['name']}")
                print(f"   描述: {tool['description']}")
                if args.detailed:
                    print(f"   参数:")
                    print(tool["parameters"])  # 显示详细参数信息

    elif args.command == "stat":
        from tabulate import tabulate

        stats = registry._get_tool_stats()
        tools = registry.get_all_tools()

        # 构建统计表格数据
        table_data = []
        for tool in tools:
            name = tool["name"]
            count = stats.get(name, 0)
            table_data.append([name, count])

        # 按调用次数降序排序
        table_data.sort(key=lambda x: x[1], reverse=True)

        if args.json:
            print(json.dumps(dict(table_data), indent=2))
        else:
            PrettyOutput.section("工具调用统计", OutputType.SYSTEM)
            print(
                tabulate(table_data, headers=["工具名称", "调用次数"], tablefmt="grid")
            )

        return 0

    elif args.command == "call":
        tool_name = args.tool_name
        tool_obj = registry.get_tool(tool_name)

        if not tool_obj:
            PrettyOutput.print(f"错误: 工具 '{tool_name}' 不存在", OutputType.ERROR)
            available_tools = ", ".join([t["name"] for t in registry.get_all_tools()])
            print(f"可用工具: {available_tools}")
            return 1

        # 获取参数: 支持从命令行直接传入或从文件加载
        tool_args = {}
        if args.args:
            try:
                tool_args = json.loads(args.args)  # 解析JSON格式参数
            except json.JSONDecodeError:
                PrettyOutput.print("错误: 参数必须是有效的JSON格式", OutputType.ERROR)
                return 1

        elif args.args_file:
            try:
                with open(args.args_file, "r", encoding="utf-8") as f:
                    tool_args = json.load(f)  # 从文件加载JSON参数
            except (json.JSONDecodeError, FileNotFoundError) as e:
                PrettyOutput.print(
                    f"错误: 无法从文件加载参数: {str(e)}", OutputType.ERROR
                )
                return 1

        # 检查必需参数是否完整
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
            return 1

        # 执行工具并处理结果
        result = registry.execute_tool(tool_name, tool_args)

        # 显示执行结果
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

        return 0 if result["success"] else 1

    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
