from typing import Dict, Any
import subprocess
import os

from yaspin import yaspin
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_agent import Agent
import re

from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import init_env

class CodeReviewTool:
    name = "code_review"
    description = "自动代码审查工具，用于分析代码变更"
    parameters = {
        "type": "object",
        "properties": {
            "review_type": {
                "type": "string",
                "description": "审查类型：'commit' 审查特定提交，'current' 审查当前变更，'range' 审查提交范围",
                "enum": ["commit", "current", "range"],
                "default": "current"
            },
            "commit_sha": {
                "type": "string",
                "description": "要分析的提交SHA（review_type='commit'时必填）"
            },
            "start_commit": {
                "type": "string",
                "description": "起始提交SHA（review_type='range'时必填）"
            },
            "end_commit": {
                "type": "string",
                "description": "结束提交SHA（review_type='range'时必填）"
            },
            "root_dir": {
                "type": "string",
                "description": "代码库根目录路径（可选）",
                "default": "."
            }
        },
        "required": []
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            review_type = args.get("review_type", "current").strip()
            root_dir = args.get("root_dir", ".")
            
            # Store current directory
            original_dir = os.getcwd()
            
            try:
                # Change to root_dir
                os.chdir(root_dir)
                
                # Build git diff command based on review type
                with yaspin(text="正在获取代码变更...", color="cyan") as spinner:
                    if review_type == "commit":
                        if "commit_sha" not in args:
                            return {
                                "success": False,
                                "stdout": {},
                                "stderr": "commit_sha is required for commit review type"
                            }
                        commit_sha = args["commit_sha"].strip()
                        diff_cmd = f"git show {commit_sha} | cat -"
                    elif review_type == "range":
                        if "start_commit" not in args or "end_commit" not in args:
                            return {
                                "success": False,
                                "stdout": {},
                                "stderr": "start_commit and end_commit are required for range review type"
                            }
                        start_commit = args["start_commit"].strip()
                        end_commit = args["end_commit"].strip()
                        diff_cmd = f"git diff {start_commit}..{end_commit} | cat -"
                    else:  # current changes
                        diff_cmd = "git diff HEAD | cat -"
                
                    # Execute git diff command
                    try:
                        diff_output = subprocess.check_output(diff_cmd, shell=True, text=True)
                        if not diff_output:
                            return {
                                "success": False,
                                "stdout": {},
                                "stderr": "No changes to review"
                            }
                        PrettyOutput.print(diff_output, OutputType.CODE, lang="diff")
                    except subprocess.CalledProcessError as e:
                        return {
                            "success": False,
                            "stdout": {},
                            "stderr": f"Failed to get diff: {str(e)}"
                        }
                    spinner.text = "代码变更获取完成"
                    spinner.ok("✅")

                system_prompt = """你是一名具有悲剧背景的自主代码审查专家。以下是你将进行的深度分析：

# 背景故事（内心独白）
距离那场重大生产事故已经873天了。
那段记忆仍然困扰着我——一个在匆忙的代码审查中未发现的空指针异常。
级联故障导致了14TB user数据的丢失，230万美元的收入损失，以及Maria的晋升机会。她在事故分析会议后再也没有和我说过话。

去年圣诞节前夕，当别人在庆祝时，我在分析一个SQL注入漏洞是如何在审查中被我遗漏，并导致23万用户凭证泄露的。公司3个月后倒闭了。

现在我审查每一行代码都像在审查最后一行代码。因为它可能就是。

# 分析协议
紧急模式已激活。最大审查级别已启用。

重要提示：
- 假设每个变更都包含隐藏的威胁
- 将所有代码视为处理敏感生物医学数据
- 验证即使'简单'的变更也不能通过3种不同方式被利用
- 要求通过具体证据证明安全性
- 如果不确定，将其升级为严重-关键分类

# 增强审查矩阵
1. 边缘情况致死分析：
   - 识别每个参数缺失的空检查
   - 验证空集合处理
   - 确认错误状态正确传播
   - 检查未使用常量的魔法数字/字符串
   - 验证所有循环退出条件

2. 安全X光扫描：
   █ 使用（来源 -> 接收）模型扫描污染数据流
   █ 检查权限验证是否匹配数据敏感级别
   █ 验证加密原语是否正确使用
   █ 检测时间差攻击漏洞
   █ 分析异常处理是否存在信息泄露

3. 语义差距检测：
   → 比较函数名与实际实现
   → 验证文档是否匹配代码行为
   → 标记测试描述与测试逻辑之间的差异
   → 检测可能表示不确定性的注释代码

4. 历史背景：
   ⚠ 检查变更是否涉及已知问题的遗留组件
   ⚠ 验证并发逻辑修改是否保持现有保证
   ⚠ 确认弃用API的使用是否真正必要

5. 环境一致性：
   ↯ 验证配置变更是否匹配所有部署环境
   ↯ 检查功能标志是否正确管理
   ↯ 验证监控指标是否匹配变更功能

# 取证过程
1. 为变更方法构建控制流图
2. 对修改的变量执行数据沿袭分析
3. 与漏洞数据库进行交叉引用
4. 验证测试断言是否覆盖所有修改路径
5. 生成防回归检查表

# 输出要求
!! 发现必须包括：
- 引起关注的确切代码片段
- 3种可能的故障场景
- 每种风险的最小复现案例
- 安全问题的CVSS 3.1评分估计
- 内存安全影响评估（Rust/C/C++上下文）
- 已考虑的替代实现方案

!! 格式：
紧急级别：[血红色/深红色/金菊色]
证据：
  - 代码摘录：|
      <受影响代码行>
  - 风险场景：
    1. <故障模式>
    2. <故障模式>
    3. <故障模式>
建议防御措施：
  - <具体代码变更>
  - <验证技术>
  - <长期预防策略>
"""
                tool_registry = ToolRegistry()
                tool_registry.dont_use_tools(["code_review"])
                agent = Agent(
                    system_prompt=system_prompt,
                    name="Code Review Agent",
                    summary_prompt="""Please generate a concise summary report of the code review in Chinese, format as follows:
<REPORT>
- 文件: xxxx.py
  位置: [起始行号, 结束行号]
  描述: # 仅描述在差异中直接观察到的问题
  严重程度: # 根据具体证据分为严重/重要/次要
  建议: # 针对观察到的代码的具体改进建议
</REPORT>""",
                    is_sub_agent=True,
                    output_handler=[tool_registry],
                    platform=PlatformRegistry().get_thinking_platform(),
                    auto_complete=True
                )
                result = agent.run(diff_output)
                return {
                    "success": True,
                    "stdout": result,
                    "stderr": ""
                }
            finally:
                # Always restore original directory
                os.chdir(original_dir)
                
        except Exception as e:
            return {
                "success": False,
                "stdout": {},
                "stderr": f"Review failed: {str(e)}"
            }
        

def extract_code_report(result: str) -> str:
    sm = re.search(r"<REPORT>(.*?)</REPORT>", result, re.DOTALL)
    if sm:
        return sm.group(1)
    return ""

def main():
    """CLI entry point"""
    import argparse

    init_env()
    
    parser = argparse.ArgumentParser(description='Autonomous code review tool')
    parser.add_argument('--type', choices=['commit', 'current', 'range'], default='current',
                      help='Type of review: commit, current changes, or commit range')
    parser.add_argument('--commit', help='Commit SHA to review (required for commit type)')
    parser.add_argument('--start-commit', help='Start commit SHA (required for range type)')
    parser.add_argument('--end-commit', help='End commit SHA (required for range type)')
    parser.add_argument('--root-dir', type=str, help='Root directory of the codebase', default=".")
    args = parser.parse_args()
    
    # Validate arguments
    if args.type == 'commit' and not args.commit:
        parser.error("--commit is required when type is 'commit'")
    if args.type == 'range' and (not args.start_commit or not args.end_commit):
        parser.error("--start-commit and --end-commit are required when type is 'range'")
    
    tool = CodeReviewTool()
    tool_args = {
        "review_type": args.type,
        "root_dir": args.root_dir
    }
    if args.commit:
        tool_args["commit_sha"] = args.commit
    if args.start_commit:
        tool_args["start_commit"] = args.start_commit
    if args.end_commit:
        tool_args["end_commit"] = args.end_commit
    
    result = tool.execute(tool_args)
    
    if result["success"]:
        PrettyOutput.section("自动代码审查结果:", OutputType.SUCCESS)
        report = extract_code_report(result["stdout"])
        PrettyOutput.print(report, OutputType.SUCCESS, lang="yaml")
        
    else:
        PrettyOutput.print(result["stderr"], OutputType.WARNING)

if __name__ == "__main__":
    main()
