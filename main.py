from agents import DialogueManager
from utils import print_colored
import sys

def main():
    print_colored("欢迎使用AI永久对话系统！", "yellow")
    print_colored("正在检查系统状态...", "white")
    
    try:
        dialogue_manager = DialogueManager()
        print_colored("系统就绪！", "green")
    except ConnectionError as e:
        print_colored(f"系统初始化失败：\n{str(e)}", "red")
        return
    
    print_colored("\n请输入初始消息（A发送给B的第一条消息）：", "cyan")
    
    try:
        initial_message = input("> ").strip()
        
        if not initial_message:
            print_colored("消息不能为空！", "red")
            return
        
        task_id = dialogue_manager.start_dialogue(initial_message)
        print_colored(f"\n对话ID: {task_id}", "white")
        print_colored("开始永久对话...\n", "yellow")
        print_colored("(按Ctrl+C可以终止对话)\n", "magenta")
        
        # 打印初始消息
        print_colored(f"\nA: {initial_message}", "blue")
        
        dialogue_manager.continue_dialogue()
            
    except KeyboardInterrupt:
        print_colored("\n\n对话已手动中断", "yellow")
        if dialogue_manager.current_conversation:
            dialogue_manager.current_conversation.complete("interrupted")
            dialogue_manager.current_conversation.save()
            print_colored(f"对话记录已保存至: conversations/task_{task_id}.json", "cyan")
    
    except Exception as e:
        print_colored(f"\n发生错误: {str(e)}", "red")
    
    print_colored("\n程序已终止", "yellow")

if __name__ == "__main__":
    main()