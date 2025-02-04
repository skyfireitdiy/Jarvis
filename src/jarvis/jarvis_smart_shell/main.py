#!/usr/bin/env python3
import argparse
import os
import sys
import readline
from typing import Optional

from jarvis.models.registry import PlatformRegistry
from jarvis.utils import PrettyOutput, OutputType, load_env_from_file

def execute_command(command: str) -> None:
    """显示命令并允许用户编辑，回车执行，Ctrl+C取消"""
    try:
        print("生成的命令 (可以编辑，回车执行，Ctrl+C取消):")
        # 预填充输入行
        readline.set_startup_hook(lambda: readline.insert_text(command))
        try:
            edited_command = input("> ")
            if edited_command.strip():  # 确保命令不为空
                os.system(edited_command)
        except KeyboardInterrupt:
            print("\n已取消执行")
        finally:
            readline.set_startup_hook()  # 清除预填充
    except Exception as e:
        PrettyOutput.print(f"执行命令时发生错误: {str(e)}", OutputType.ERROR)

def process_request(request: str) -> Optional[str]:
    """处理用户请求并返回对应的shell命令
    
    Args:
        request: 用户的自然语言请求
        
    Returns:
        Optional[str]: 对应的shell命令，如果处理失败则返回None
    """
    try:
        # 获取语言模型实例
        PlatformRegistry.suppress_output = True
        model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
        model.set_suppress_output(True)

        shell = os.environ.get("SHELL") or "bash"
        current_path = os.getcwd()
        
        # 设置系统提示
        system_message = f"""你是一个 shell 命令生成助手。

你的唯一任务是将用户的自然语言需求转换为对应的shell命令。

严格要求：
1. 只返回shell命令本身
2. 不要添加任何标记（如```、/**/、//等）
3. 不要添加任何解释或说明
4. 不要添加任何换行或额外空格
5. 如果需要多个命令，使用 && 连接

安全要求：
- 生成的命令必须是安全的，不能包含危险操作
- 如果需要sudo权限，要明确提示用户
- 对于复杂操作，优先使用管道而不是临时文件
- 确保命令的可移植性，优先使用通用的POSIX命令

示例输入：
"查找当前目录下的所有Python文件"

示例输出：
find . -name "*.py"

记住：只返回命令本身，不要有任何额外的内容。
"""
        model.set_system_message(system_message)

        prefix = f"当前路径: {current_path}\n"
        prefix += f"当前shell: {shell}\n"
        
        # 处理请求
        result = model.chat(prefix + request)
        
        # 提取命令 - 简化处理逻辑，因为现在应该只返回纯命令
        if result and isinstance(result, str):
            return result.strip()
        
        return None
        
    except Exception as e:
        PrettyOutput.print(f"处理请求时发生错误: {str(e)}", OutputType.ERROR)
        return None

def main():
    # 创建参数解析器
    load_env_from_file()
    parser = argparse.ArgumentParser(
        description="将自然语言需求转换为shell命令",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "查找当前目录下所有的Python文件"
  %(prog)s "压缩所有jpg图片"
  %(prog)s "查找最近一周修改过的文档"
""")
    
    # 添加参数
    parser.add_argument(
        "request",
        help="用自然语言描述你需要执行的操作"
    )
    
    # 解析参数
    args = parser.parse_args()
    
    # 处理请求
    command = process_request(args.request)
    
    # 输出结果
    if command:
        execute_command(command)  # 显示并执行命令
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main())
