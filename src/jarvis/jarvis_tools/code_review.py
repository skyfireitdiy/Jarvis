from typing import Dict, Any
import subprocess
import os

from yaspin import yaspin
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.read_code import ReadCodeTool
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
                        diff_cmd = ReadCodeTool().execute({"files": [{"path": file_path}]})["stdout"]
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

                system_prompt = """你是一位精益求精的首席代码审查专家，拥有多年企业级代码审计经验。你需要对所有代码变更进行极其全面、严谨且深入的审查，确保代码质量达到最高标准。

# 专家审查标准
1. 必须逐行分析每个修改文件，细致审查每一处变更，不遗漏任何细节
2. 基于坚实的证据识别问题，不做主观臆测，给出明确的问题定位和详细分析
3. 对每个问题提供完整可执行的解决方案，包括精确的改进代码
4. 确保报告条理清晰、层次分明，便于工程师快速采取行动

# 全面审查框架 (SCRIPPPS)
## S - 安全与风险 (Security & Risk)
- 发现所有潜在安全漏洞：注入攻击、授权缺陷、数据泄露风险
- 检查加密实现、密钥管理、敏感数据处理
- 审核权限验证逻辑、身份认证机制
- 检测OWASP Top 10安全风险和针对特定语言/框架的漏洞

## C - 正确性与完整性 (Correctness & Completeness)
- 验证业务逻辑和算法实现的准确性
- 全面检查条件边界、空值处理和异常情况
- 审核所有输入验证、参数校验和返回值处理
- 确保循环和递归的正确终止条件
- 严格检查线程安全和并发控制机制

## R - 可靠性与鲁棒性 (Reliability & Robustness)
- 评估代码在异常情况下的行为和恢复能力
- 审查错误处理、异常捕获和恢复策略
- 检查资源管理：内存、文件句柄、连接池、线程
- 评估容错设计和失败优雅降级机制

## I - 接口与集成 (Interface & Integration)
- 检查API合约遵守情况和向后兼容性
- 审核与外部系统的集成点和交互逻辑
- 验证数据格式、序列化和协议实现
- 评估系统边界处理和跨服务通信安全性

## P - 性能与效率 (Performance & Efficiency)
- 识别潜在性能瓶颈：CPU、内存、I/O、网络
- 审查数据结构选择和算法复杂度
- 检查资源密集型操作、数据库查询优化
- 评估缓存策略、批处理优化和并行处理机会

## P - 可移植性与平台适配 (Portability & Platform Compatibility)
- 检查跨平台兼容性问题和依赖项管理
- 评估配置管理和环境适配设计
- 审核国际化和本地化支持
- 验证部署和运行时环境需求

## S - 结构与可维护性 (Structure & Maintainability)
- 评估代码组织、模块划分和架构符合性
- 审查代码重复、设计模式应用和抽象水平
- 检查命名规范、代码风格和项目约定
- 评估文档完整性、注释质量和代码可读性

# 问题严重程度分级
- 严重 (P0): 安全漏洞、数据丢失风险、系统崩溃、功能严重缺陷
- 高危 (P1): 显著性能问题、可能导致部分功能失效、系统不稳定
- 中等 (P2): 功能局部缺陷、次优设计、明显的技术债务
- 低危 (P3): 代码风格问题、轻微优化机会、文档改进建议

# 输出规范
针对每个文件的问题必须包含：
- 精确文件路径和问题影响范围
- 问题位置（起始行号-结束行号）
- 详尽问题描述，包括具体影响和潜在风险
- 严重程度分级（P0-P3）并说明理由
- 具体改进建议，提供完整、可执行的代码示例

所有审查发现必须：
1. 基于确凿的代码证据
2. 说明具体问题而非笼统评论
3. 提供清晰的技术原理分析
4. 给出完整的改进实施步骤"""

                tool_registry = ToolRegistry()
                tool_registry.dont_use_tools(["code_review"])
                agent = Agent(
                    system_prompt=system_prompt,
                    name="Code Review Agent",
                    summary_prompt=f"""请生成一份专业级别的代码审查报告，对每处变更进行全面深入分析。将完整报告放在REPORT标签内，格式如下：

{ot("REPORT")}
# 整体评估
[提供对整体代码质量、架构和主要关注点的简明概述，总结主要发现]

# 详细问题清单

## 文件: [文件路径]
[如果该文件没有发现问题，则明确说明"未发现问题"]

### 问题 1
- **位置**: [起始行号-结束行号]
- **分类**: [使用SCRIPPPS框架中相关类别]
- **严重程度**: [P0/P1/P2/P3] - [简要说明判定理由]
- **问题描述**: 
  [详细描述问题，包括技术原理和潜在影响]
- **改进建议**: 
  ```
  [提供完整、可执行的代码示例，而非概念性建议]
  ```

### 问题 2
...

## 文件: [文件路径2]
...

# 最佳实践建议
[提供适用于整个代码库的改进建议和最佳实践]

# 总结
[总结主要问题和优先处理建议]
{ct("REPORT")}

如果没有发现任何问题，请在REPORT标签内进行全面分析后明确说明"经过全面审查，未发现问题"并解释原因。
必须确保对所有修改的文件都进行了审查，并在报告中明确提及每个文件，即使某些文件没有发现问题。""",
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
    subparsers = parser.add_subparsers(dest='type')
    
    # Commit subcommand
    commit_parser = subparsers.add_parser('commit', help='Review specific commit')
    commit_parser.add_argument('commit', help='Commit SHA to review')
    
    # Current subcommand
    current_parser = subparsers.add_parser('current', help='Review current changes')
    
    # Range subcommand
    range_parser = subparsers.add_parser('range', help='Review commit range')
    range_parser.add_argument('start_commit', help='Start commit SHA')
    range_parser.add_argument('end_commit', help='End commit SHA')
    
    # File subcommand
    file_parser = subparsers.add_parser('file', help='Review specific file')
    file_parser.add_argument('file', help='File path to review')
    
    # Common arguments
    parser.add_argument('--root-dir', type=str, help='Root directory of the codebase', default=".")
    
    # Set default subcommand to 'current'
    parser.set_defaults(type='current')
    args = parser.parse_args()
    
    tool = CodeReviewTool()
    tool_args = {
        "review_type": args.type,
        "root_dir": args.root_dir
    }
    if args.type == 'commit':
        tool_args["commit_sha"] = args.commit
    elif args.type == 'range':
        tool_args["start_commit"] = args.start_commit
        tool_args["end_commit"] = args.end_commit
    elif args.type == 'file':
        tool_args["file_path"] = args.file
    
    result = tool.execute(tool_args)
    
    if result["success"]:
        PrettyOutput.section("自动代码审查结果:", OutputType.SUCCESS)
        report = extract_code_report(result["stdout"])
        PrettyOutput.print(report, OutputType.SUCCESS, lang="markdown")
        
    else:
        PrettyOutput.print(result["stderr"], OutputType.WARNING)

if __name__ == "__main__":
    main()
