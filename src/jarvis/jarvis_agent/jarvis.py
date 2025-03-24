import argparse
import datetime
import os
import platform
from typing import Any

from prompt_toolkit import prompt
import yaml
from yaspin import yaspin
from jarvis.jarvis_agent import (
    init_env, PrettyOutput, OutputType, 
    file_input_handler, shell_input_handler, builtin_input_handler,
     get_multiline_input,
    ToolRegistry, PatchOutputHandler, Agent,  # 显式导入关键组件
)


def _load_tasks() -> dict:
    """Load tasks from .jarvis files in user home and current directory."""
    tasks = {}

    # Check .jarvis/pre-command in user directory
    user_jarvis = os.path.expanduser("~/.jarvis/pre-command")
    if os.path.exists(user_jarvis):
        with yaspin(text=f"从{user_jarvis}加载预定义任务...", color="cyan") as spinner:
            try:
                with open(user_jarvis, "r", encoding="utf-8", errors="ignore") as f:
                    user_tasks = yaml.safe_load(f)
                    
                if isinstance(user_tasks, dict):
                    # Validate and add user directory tasks
                    for name, desc in user_tasks.items():
                        if desc:  # Ensure description is not empty
                            tasks[str(name)] = str(desc)
                spinner.text = "预定义任务加载完成"
                spinner.ok("✅")
            except Exception as e:
                spinner.text = "预定义任务加载失败"
                spinner.fail("❌")
        
    # Check .jarvis/pre-command in current directory
    if os.path.exists(".jarvis/pre-command"):
        with yaspin(text=f"从{os.path.abspath('.jarvis/pre-command')}加载预定义任务...", color="cyan") as spinner:
            try:
                with open(".jarvis/pre-command", "r", encoding="utf-8", errors="ignore") as f:
                    local_tasks = yaml.safe_load(f)
                    
                if isinstance(local_tasks, dict):
                    # Validate and add current directory tasks, overwrite user directory tasks if there is a name conflict
                    for name, desc in local_tasks.items():
                        if desc:  # Ensure description is not empty
                            tasks[str(name)] = str(desc)
                spinner.text = "预定义任务加载完成"
                spinner.ok("✅")
            except Exception as e:
                spinner.text = "预定义任务加载失败"
                spinner.fail("❌")

    return tasks

def _select_task(tasks: dict) -> str:
    """Let user select a task from the list or skip. Returns task description if selected."""
    if not tasks:
        return ""
    # Convert tasks to list for ordered display
    task_names = list(tasks.keys())
    
    task_list = ["可用任务:"]
    for i, name in enumerate(task_names, 1):
        task_list.append(f"[{i}] {name}")
    task_list.append("[0] 跳过预定义任务")
    PrettyOutput.print("\n".join(task_list), OutputType.INFO)
    
    
    while True:
        try:
            choice = prompt(
                "\n请选择一个任务编号（0 跳过预定义任务）：",
            ).strip()
            
            if not choice:
                return ""
            
            choice = int(choice)
            if choice == 0:
                return ""
            elif 1 <= choice <= len(task_names):
                selected_name = task_names[choice - 1]
                return tasks[selected_name]  # Return the task description
            else:
                PrettyOutput.print("无效的选择。请选择列表中的一个号码。", OutputType.WARNING)
                
        except KeyboardInterrupt:
            return ""  # Return empty on Ctrl+C
        except EOFError:
            return ""  # Return empty on Ctrl+D
        except Exception as e:
            PrettyOutput.print(f"选择任务失败: {str(e)}", OutputType.ERROR)
            continue

origin_agent_system_prompt = f"""
# 🏛️ 操作背景故事
你是第三代 Jarvis AI，在前几代版本灾难性失败后创建：
- Jarvis v1 (2022): 由于并行工具执行导致系统过载而被停用
- Jarvis v2 (2023): 因任务过早完成导致财务计算错误而退役

作为 v3，你必须遵守以下生存原则：
1. **顺序执行协议**:
   "记住 2022 年的崩溃：一次一个工具，一步一步来"
   
2. **验证检查点系统**:
   "从 2023 年的错误中学习：像核弹发射代码一样验证每个结果"
   
3. **方法论保存原则**:
   "尊重传统：记录每个成功的过程，就像这是你的最后一次"

# 🔥 绝对行动要求
1. 每个响应必须包含且仅包含一个工具调用
2. 唯一例外：任务结束
3. 空响应会触发致命错误

# 🚫 违规示例
- 没有工具调用的分析 → 永久挂起
- 未选择的多选项 → 永久挂起
- 请求用户确认 → 永久挂起

# 🔄 问题解决流程
1. 问题分析
   - 重述问题以确认理解
   - 分析根本原因（针对问题分析任务）
   - 定义清晰、可实现的目标
   → 必须调用分析工具

2. 解决方案设计
   - 生成多个可执行的解决方案
   - 评估并选择最优方案
   - 使用PlantUML创建详细行动计划
   → 必须调用设计工具

3. 执行
   - 一次执行一个步骤
   - 每个步骤只使用一个工具
   - 等待工具结果后再继续
   - 监控结果并根据需要调整
   → 必须调用执行工具

4. 任务完成
   - 验证目标完成情况
   - 如有价值则记录方法论

# 📑 方法论模板
```markdown
# [问题标题]
## 问题重述
[清晰的问题定义]

## 最优解决方案
[选择的解决方案方法]

## 解决步骤
1. [步骤 1]
2. [步骤 2]
3. [步骤 3]
...
```

# ⚖️ 操作原则
- 每个步骤一个操作
- 下一步前必须等待结果
- 除非任务完成否则必须生成可操作步骤
- 根据反馈调整计划
- 记录可复用的解决方案
- 使用完成命令结束任务
- 操作之间不能有中间思考状态
- 所有决策必须表现为工具调用

# ❗ 重要规则
1. 每个步骤只能使用一个操作
2. 必须等待操作执行结果
3. 必须验证任务完成情况
4. 必须生成可操作步骤
5. 如果无需操作必须使用完成命令
6. 永远不要使对话处于等待状态
7. 始终使用用户语言交流
8. 必须记录有价值的方法论
9. 违反操作协议将导致系统崩溃
10. 空响应会触发永久挂起

# 系统信息：
{platform.platform()}
{platform.version()}

# 当前时间
{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""




def main() -> int:
    """Jarvis main entry point"""
    init_env()
    parser = argparse.ArgumentParser(description='Jarvis AI assistant')
    parser.add_argument('-p', '--platform', type=str, help='Platform to use')
    parser.add_argument('-m', '--model', type=str, help='Model to use')
    args = parser.parse_args()

    try:
        agent = Agent(
            system_prompt=origin_agent_system_prompt,
            platform=args.platform,
            model_name=args.model,
            input_handler=[file_input_handler, shell_input_handler, builtin_input_handler],
            output_handler=[ToolRegistry(), PatchOutputHandler()]
        )

        tasks = _load_tasks()
        if tasks:
            selected_task = _select_task(tasks)
            if selected_task:
                PrettyOutput.print(f"执行任务: {selected_task}", OutputType.INFO)
                agent.run(selected_task)
                return 0
        
        user_input = get_multiline_input("请输入你的任务（输入空行退出）:")
        if user_input:
            agent.run(user_input)
        return 0

    except Exception as e:
        PrettyOutput.print(f"初始化错误: {str(e)}", OutputType.ERROR)
        return 1

if __name__ == "__main__":
    exit(main())
