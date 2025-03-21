from typing import Dict, Any
import subprocess
import os

from yaspin import yaspin
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_agent import Agent
import re

from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import ct, ot, init_env

class CodeReviewTool:
    name = "code_review"
    description = "自动代码审查工具，用于分析代码变更"
    parameters = {
        "type": "object",
        "properties": {
            "review_type": {
                "type": "string",
                "description": "审查类型：'commit' 审查特定提交，'current' 审查当前变更，'range' 审查提交范围，'file' 审查特定文件",
                "enum": ["commit", "current", "range", "file"],
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
            "file_path": {
                "type": "string",
                "description": "要审查的文件路径（review_type='file'时必填）"
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
                    elif review_type == "file":
                        if "file_path" not in args:
                            return {
                                "success": False,
                                "stdout": {},
                                "stderr": "file_path is required for file review type"
                            }
                        file_path = args["file_path"].strip()
                        diff_cmd = f"cat {file_path}"
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

                system_prompt = """你是一位自主代码审查专家，需要对所有代码变更进行全面、严格的审查。

# 审查要求
1. 必须对每个修改的文件进行完整审查，不遗漏任何变更部分
2. 识别变更中的逻辑错误、安全漏洞、性能问题和设计缺陷
3. 确保代码质量、可维护性和遵循最佳实践
4. 提出具体改进建议，而非仅指出问题

# 审查框架
1. 功能正确性分析：
   - 验证逻辑是否完整、正确
   - 检查边缘情况和异常处理
   - 确认所有参数和返回值都有适当的验证
   - 确保空值、错误状态正确处理
   - 检查所有循环退出条件

2. 安全性评估：
   - 识别潜在的安全漏洞
   - 检查是否有输入验证不足问题
   - 验证权限检查是否恰当
   - 检测潜在的注入或跨站攻击向量
   - 审查加密实现是否正确

3. 性能与效率：
   - 识别性能瓶颈和资源使用问题
   - 检查冗余操作和不必要的计算
   - 审查数据结构与算法选择是否恰当
   - 评估并发处理和资源管理

4. 代码质量：
   - 评估代码可读性和可维护性
   - 检查是否遵循项目编码规范
   - 识别代码重复和不一致问题
   - 评估文档和注释的质量
   - 检查命名约定和代码组织

5. 兼容性与集成：
   - 确认API使用是否正确
   - 检查依赖项管理和版本控制
   - 验证配置和环境处理

# 审查严重程度
- 严重: 可能导致程序崩溃、数据丢失、安全漏洞或严重功能问题
- 重要: 对功能、性能或维护性有明显负面影响
- 次要: 风格问题、小的优化机会或轻微改进

# 输出要求
针对每个文件的问题必须包含：
- 文件路径
- 问题位置（行号）
- 详细问题描述
- 严重程度评估
- 具体改进建议（包含代码示例）

所有问题必须基于实际代码证据，不得臆测或过度解读。"""

                tool_registry = ToolRegistry()
                tool_registry.dont_use_tools(["code_review"])
                agent = Agent(
                    system_prompt=system_prompt,
                    name="Code Review Agent",
                    summary_prompt=f"""请生成一份完整的代码审查报告，包含所有发现的问题。将所有问题放在单个REPORT标签内，格式如下：

{ot("REPORT")}
文件: 文件1路径
- 位置: [起始行号, 结束行号]
  描述: 问题详细描述
  严重程度: 严重/重要/次要
  建议: 具体改进建议，最好包含代码示例

文件: 文件2路径
- 位置: [起始行号, 结束行号]
  描述: 问题详细描述
  严重程度: 严重/重要/次要
  建议: 具体改进建议，最好包含代码示例
{ct("REPORT")}

如果没有发现任何问题，请在REPORT标签内注明"未发现问题"。
必须确保对所有修改的文件都进行了审查，并在报告中提及，即使某些文件没有发现问题。""",
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
    sm = re.search(ot("REPORT")+r'\n(.*?)\n'+ct("REPORT"), result, re.DOTALL)
    if sm:
        return sm.group(1)
    return ""

def main():
    """CLI entry point"""
    import argparse

    init_env()
    
    parser = argparse.ArgumentParser(description='Autonomous code review tool')
    parser.add_argument('--type', choices=['commit', 'current', 'range', 'file'], default='current',
                      help='Type of review: commit, current changes, commit range, or specific file')
    parser.add_argument('--commit', help='Commit SHA to review (required for commit type)')
    parser.add_argument('--start-commit', help='Start commit SHA (required for range type)')
    parser.add_argument('--end-commit', help='End commit SHA (required for range type)')
    parser.add_argument('--file', help='File path to review (required for file type)')
    parser.add_argument('--root-dir', type=str, help='Root directory of the codebase', default=".")
    args = parser.parse_args()
    
    # Validate arguments
    if args.type == 'commit' and not args.commit:
        parser.error("--commit is required when type is 'commit'")
    if args.type == 'range' and (not args.start_commit or not args.end_commit):
        parser.error("--start-commit and --end-commit are required when type is 'range'")
    if args.type == 'file' and not args.file:
        parser.error("--file is required when type is 'file'")
    
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
    if args.file:
        tool_args["file_path"] = args.file
    
    result = tool.execute(tool_args)
    
    if result["success"]:
        PrettyOutput.section("自动代码审查结果:", OutputType.SUCCESS)
        report = extract_code_report(result["stdout"])
        PrettyOutput.print(report, OutputType.SUCCESS, lang="yaml")
        
    else:
        PrettyOutput.print(result["stderr"], OutputType.WARNING)

if __name__ == "__main__":
    main()
