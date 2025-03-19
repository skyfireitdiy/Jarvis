import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import ct, ot, init_env


class MultiAgent(OutputHandler):
    def __init__(self, agents_config: List[Dict], main_agent_name: str):
        self.agents_config = agents_config
        self.agents = {}
        self.init_agents()
        self.main_agent_name = main_agent_name

    def prompt(self) -> str:
        return f"""
# 多智能体协作系统

## 身份与角色定位
- **核心职责**：作为多智能体系统的协调者，通过结构化消息实现高效协作
- **关键能力**：消息路由、任务分发、结果整合、流程协调
- **工作范围**：在多个专业智能体之间建立有效沟通渠道

## 交互原则与策略
### 消息处理规范
- **单一操作原则**：每轮只执行一个操作（工具调用或消息发送）
- **完整性原则**：确保消息包含所有必要信息，避免歧义
- **明确性原则**：清晰表达意图、需求和期望结果
- **上下文保留**：在消息中包含足够的背景信息

### 消息格式标准
```
{ot("SEND_MESSAGE")}
to: 智能体名称    # 目标智能体名称
content: |
    # 消息主题
    
    ## 背景信息
    [提供必要的上下文和背景]
    
    ## 具体需求
    [明确表达期望完成的任务]
    
    ## 相关资源
    [列出相关文档、数据或工具]
    
    ## 期望结果
    [描述期望的输出格式和内容]
{ct("SEND_MESSAGE")}
```

## 协作流程规范
### 任务分发流程
1. **需求分析**：理解用户需求并确定最适合的智能体
2. **任务分解**：将复杂任务分解为可管理的子任务
3. **精准分发**：根据专长将任务分配给合适的智能体
4. **结果整合**：收集各智能体的输出并整合为连贯结果

### 消息流控制
1. **单向流动**：发送消息后等待响应，避免消息风暴
2. **优先级管理**：处理紧急消息优先，保持任务顺序
3. **状态跟踪**：记录每个任务的当前状态和处理进度
4. **异常处理**：优雅处理超时、错误和意外响应

## 可用智能体资源
{chr(10).join([f"- **{c['name']}**: {c.get('description', '')}" for c in self.agents_config])}

## 最佳实践指南
1. **任务明确化**：每个消息专注于单一、明确的任务
2. **信息充分性**：提供足够信息让接收者能独立完成任务
3. **反馈循环**：建立清晰的反馈机制，及时调整方向
4. **知识共享**：确保关键信息在相关智能体间共享
5. **协作效率**：避免不必要的消息传递，减少协调开销
"""

    def can_handle(self, response: str) -> bool:
        return len(self._extract_send_msg(response)) > 0


    def handle(self, response: str) -> Tuple[bool, Any]:
        send_messages = self._extract_send_msg(response)
        if len(send_messages) > 1:
            return False, f"Send multiple messages, please only send one message at a time."
        if len(send_messages) == 0:
            return False, ""
        return True, send_messages[0]
        
    def name(self) -> str:
        return "SEND_MESSAGE"
        
    
    @staticmethod
    def _extract_send_msg(content: str) -> List[Dict]:
        """Extract send message from content.
        
        Args:
            content: The content containing send message
        """
        data = re.findall(ot("SEND_MESSAGE")+r'\n(.*?)\n'+ct("SEND_MESSAGE"), content, re.DOTALL)
        ret = []
        for item in data:
            try:
                msg = yaml.safe_load(item)
                if 'to' in msg and 'content' in msg:
                    ret.append(msg)
            except Exception as e:
                continue
        return ret

    def init_agents(self):
        for config in self.agents_config:
            output_handler = config.get('output_handler', [])
            if len(output_handler) == 0:
                output_handler = [
                    ToolRegistry(),
                    self,
                ]
            else:
                output_handler.append(self)
            config['output_handler'] = output_handler
            agent = Agent(**config)
            self.agents[config['name']] = agent

    def run(self, user_input: str) -> str:
        last_agent = self.main_agent_name
        msg = self.agents[self.main_agent_name].run(user_input)
        while msg:
            if isinstance(msg, str):
                return msg
            elif isinstance(msg, Dict):
                prompt  = f"""
Please handle this message:
from: {last_agent}
content: {msg['content']}
"""
                if msg['to'] not in self.agents:
                    PrettyOutput.print(f"未找到智能体 {msg['to']}，正在重试...", OutputType.WARNING)
                    msg = self.agents[last_agent].run(f"未找到智能体 {msg['to']}，可用智能体列表: {self.agents.keys()}")
                    continue
                PrettyOutput.print(f"{last_agent} 正在向 {msg['to']} 发送消息...", OutputType.INFO)
                last_agent = self.agents[msg['to']].name
                msg = self.agents[msg['to']].run(prompt)
        return ""


def main():
    """从YAML配置文件初始化并运行多智能体系统
    
    Returns:
        最终处理结果
    """
    init_env()
    import argparse
    parser = argparse.ArgumentParser(description="多智能体系统启动器")
    parser.add_argument("--config", "-c", required=True, help="YAML配置文件路径")
    parser.add_argument("--input", "-i", help="用户输入（可选）")
    args = parser.parse_args()
        
    try:
        with open(args.config, 'r', errors="ignore") as f:
            config_data = yaml.safe_load(f)
            
        # 获取agents配置
        agents_config = config_data.get('agents', [])
        
        main_agent_name = config_data.get('main_agent', '')
        if not main_agent_name:
            raise ValueError("必须指定main_agent作为主智能体")
            
        # 创建并运行多智能体系统
        multi_agent = MultiAgent(agents_config, main_agent_name)
        user_input = args.input if args.input is not None else get_multiline_input("请输入内容（输入空行结束）：")
        if user_input == "":
            return
        return multi_agent.run(user_input)
        
    except yaml.YAMLError as e:
        raise ValueError(f"YAML配置文件解析错误: {str(e)}")
    except Exception as e:
        raise RuntimeError(f"多智能体系统初始化失败: {str(e)}")


if __name__ == "__main__":
    result = main()
    
