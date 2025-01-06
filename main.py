from agent import Agent
from models import DDGSModel, OllamaModel
from tools import ToolRegistry
from utils import PrettyOutput, OutputType

def get_multiline_input() -> str:
    """获取多行输入"""
    PrettyOutput.print("\n请输入您的问题 (输入空行或'finish'完成):", OutputType.INFO)
    lines = []
    
    while True:
        try:
            line = input("... " if lines else ">>> ").strip()
            
            # 检查是否结束输入
            if not line or line.lower() == "finish":
                if not lines:  # 如果是第一行就输入空行或finish
                    return "finish"
                break
            
            lines.append(line)
            
        except KeyboardInterrupt:
            PrettyOutput.print("\n输入已取消", OutputType.ERROR)
            return "finish"
    
    return "\n".join(lines)

def main():
    # 创建Ollama模型实例
    # model = OllamaModel(model_name="qwen2.5:14b", api_base="http://localhost:11434")
    model = DDGSModel(model_name="claude-3-haiku")
    # 创建工具注册表
    tool_registry = ToolRegistry()
    
    # 创建Agent实例
    agent = Agent(model, tool_registry)
    
    # 启动对话
    PrettyOutput.print("\n🤖 欢迎使用AI助手 (输入空行或'finish'结束对话)", OutputType.INFO)
    
    while True:
        try:
            # 获取用户输入
            user_input = get_multiline_input()
            if user_input == "finish" or user_input == "":
                PrettyOutput.print("\n再见！期待下次为您服务！", OutputType.INFO)
                break
            
            # 执行对话
            agent.run(user_input)
            
            # 打印分隔线
            print("\n" + "─" * 50 + "\n")
                
        except KeyboardInterrupt:
            PrettyOutput.print("\n程序已退出", OutputType.INFO)
            break
        except Exception as e:
            PrettyOutput.print(f"发生错误: {str(e)}", OutputType.ERROR)
            break

if __name__ == "__main__":
    main() 