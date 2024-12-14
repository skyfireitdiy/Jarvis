from agent import create_agent, process_message

def main():
    # 创建agent
    agent = create_agent()
    
    print("欢迎使用AI助手! 输入'quit'退出。")
    
    while True:
        # 获取用户输入
        user_input = input("您: ")
        
        if user_input.lower() == 'quit':
            break
            
        try:
            # 处理消息并获取响应
            response = process_message(agent, user_input)
            print("AI: ", response)
        except Exception as e:
            print("发生错误:", str(e))

if __name__ == "__main__":
    main() 