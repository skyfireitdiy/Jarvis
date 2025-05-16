
import sys
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import init_env


def main() -> int:
    """命令行工具入口，提供工具列表查看和工具调用功能"""
    import argparse
    import json

    init_env()

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

    args = parser.parse_args()

    # 初始化工具注册表
    registry = ToolRegistry()

    if args.command == "list":
        tools = registry.get_all_tools()

        if args.json:
            if args.detailed:
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
                if args.detailed:
                    print(f"   参数:")
                    print(tool["parameters"])

    elif args.command == "call":
        tool_name = args.tool_name
        tool_obj = registry.get_tool(tool_name)

        if not tool_obj:
            PrettyOutput.print(f"错误: 工具 '{tool_name}' 不存在", OutputType.ERROR)
            available_tools = ", ".join([t["name"] for t in registry.get_all_tools()])
            print(f"可用工具: {available_tools}")
            return 1

        # 获取参数
        tool_args = {}
        if args.args:
            try:
                tool_args = json.loads(args.args)
            except json.JSONDecodeError:
                PrettyOutput.print("错误: 参数必须是有效的JSON格式", OutputType.ERROR)
                return 1

        elif args.args_file:
            try:
                with open(args.args_file, "r", encoding="utf-8") as f:
                    tool_args = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                PrettyOutput.print(
                    f"错误: 无法从文件加载参数: {str(e)}", OutputType.ERROR
                )
                return 1

        # 检查必需参数
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

        # 执行工具
        result = registry.execute_tool(tool_name, tool_args)

        # 显示结果
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
