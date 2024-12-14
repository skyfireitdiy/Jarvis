from langchain_ollama import ChatOllama
from langchain.agents import AgentExecutor, initialize_agent, AgentType
from langchain.prompts import MessagesPlaceholder, SystemMessagePromptTemplate
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from tools import get_tools
import os

# 加载环境变量
load_dotenv()

def create_agent():
    # 初始化 Ollama 模型
    llm = ChatOllama(
        model="llama3",
        base_url="http://localhost:11434",
        temperature=0.7,
        top_p=0.9,
        top_k=50,
        repeat_penalty=1.1
    )
    
    # 获取工具列表
    tools = get_tools()

    # 初始化记忆组件
    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True
    )
    
    # 设置系统消息
    system_message = """你是一个专业的AI助手，能够帮助用户解决各种问题。你可以：
1. 搜索并提供最新信息
2. 查询百科知识
3. 进行数学计算和数据处理
4. 回答用户的各类问题

请用中文回答，保持友好和专业的态度。确保回答准确、清晰且有帮助。"""
    
    # 创建代理
    agent = initialize_agent(
        tools=tools,
        llm=llm,
        agent=AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
        verbose=True,
        max_iterations=3,
        early_stopping_method="generate",
        memory=memory,
        handle_parsing_errors=True,
        agent_kwargs={
            "system_message": system_message
        }
    )
    
    return agent

def process_message(agent: AgentExecutor, message: str) -> str:
    """处理用户消息并返回响应"""
    try:
        print("\n=== 开始新的对话 ===")
        print(f"Human: {message}")
        
        # 运行代理
        response = agent.invoke({"input": message})
        
        print("\n=== 完整回答 ===")
        print(f"AI: {response['output']}")
        print("==================\n")
        
        return response["output"]
        
    except Exception as e:
        return f"处理消息时发生错误: {str(e)}"