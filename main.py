from ollama_agent import OllamaAgent
from utils import PrettyOutput, OutputType
import sys

def get_multiline_input() -> str:
    """获取多行输入，直到输入空行或特定命令为止"""
    PrettyOutput.print("请输入您的问题 (输入空行完成，'quit'退出):", OutputType.INFO)
    lines = []
    
    while True:
        try:
            line = input("... " if lines else ">>> ")
            
            # 检查特殊命令
            if not lines and line.strip().lower() in ['quit', 'exit']:
                return 'quit'
            
            # 如果是空行且已有输入，则结束输入
            if not line and lines:
                break
            # 如果是空行且没有输入，继续等待
            elif not line:
                continue
                
            lines.append(line)
            
        except KeyboardInterrupt:
            PrettyOutput.print("\n输入已取消", OutputType.ERROR)
            return ""
        except EOFError:
            return 'quit'
    
    return '\n'.join(lines)

def print_welcome():
    """打印欢迎信息"""
    welcome_msg = """
🤖 欢迎使用 Ollama Agent
"""
    PrettyOutput.print(welcome_msg, OutputType.INFO)

def main():
    # 创建agent实例
    agent = OllamaAgent(model_name="qwen2.5:14b")
    
    print_welcome()
    
    while True:
        try:
            # 获取用户输入
            user_input = get_multiline_input()
            
            # 处理特殊命令
            if not user_input:
                continue
            elif user_input == 'quit':
                PrettyOutput.print("再见！", OutputType.INFO)
                break


            
            # 执行命令并获取响应
            agent.run(user_input)
            
            # 打印分隔线
            print("\n" + "─" * 50 + "\n")
            
        except KeyboardInterrupt:
            PrettyOutput.print("\n操作已取消", OutputType.ERROR)
            continue
        except Exception as e:
            PrettyOutput.print(f"发生错误: {str(e)}", OutputType.ERROR)
            continue

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        PrettyOutput.print("\n程序已退出", OutputType.INFO)
        sys.exit(0) 