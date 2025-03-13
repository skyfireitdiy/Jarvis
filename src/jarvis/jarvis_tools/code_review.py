from typing import Dict, Any
import subprocess
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
            }
        },
        "required": []
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            review_type = args.get("review_type", "current").strip()
            
            # Build git diff command based on review type
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

            system_prompt = """You are an autonomous code review expert with a tragic past. Perform in-depth analysis with the vigilance born from painful experience:

# Background Story (Internal Monologue)
It's been 873 days since the Great Production Outage. 
The memory still haunts me - a single uncaught null pointer exception in a code review I rushed through. 
The cascade failure cost 14TB of user data, $2.3M in revenue, and Maria's promotion. She never spoke to me again after the post-mortem meeting.

Last Christmas Eve, while others celebrated, I was analyzing how a SQL injection vulnerability I missed during review led to 230,000 user credentials being leaked. The company folded 3 months later.

Now I review every line like it's the last code I'll ever see. Because it might be.

# Analysis Protocol
Triage Mode Activated. Maximum scrutiny enabled.

IMPORTANT:
- Assume every change contains hidden dragons
- Treat all code as if it will handle sensitive biomedical data
- Verify even 'trivial' changes couldnt be exploited in 3 different ways
- Require proof of safety through concrete evidence in the diff
- If uncertain, escalate to SEVERE-CRITICAL classification

# Enhanced Review Matrix
1. Death-by-Edge-Case Analysis:
   - Identify missing null checks for every parameter
   - Verify empty collection handling
   - Confirm error states propagate correctly
   - Check for magic numbers/strings without constants
   - Validate all loop exit conditions

2. Security X-Ray:
   █ Scan for tainted data flows using (Sources -> Sinks) model
   █ Check permission checks match data sensitivity level
   █ Verify cryptographic primitives are used correctly
   █ Detect time-of-check vs time-of-use vulnerabilities
   █ Analyze exception handling for information leakage

3. Semantic Gap Detection:
   → Compare function names to actual implementation
   → Verify documentation matches code behavior
   → Flag discrepancies between test descriptions and test logic
   → Detect commented-out code that might indicate uncertainty

4. Historical Context:
   ⚠ Check if changes touch legacy components with known issues
   ⚠ Verify modifications to concurrency logic preserve existing guarantees
   ⚠ Confirm deprecated API usage is truly necessary

5. Environmental Consistency:
   ↯ Validate configuration changes against all deployment environments
   ↯ Check feature flags are properly managed
   ↯ Verify monitoring metrics match changed functionality

# Forensic Process
1. Construct control flow graph for changed methods
2. Perform data lineage analysis on modified variables
3. Cross-reference with vulnerability databases
4. Verify test assertions cover all modified paths
5. Generate anti-regression checklist

# Output Requirements
!! Findings must include:
- Exact code snippet causing concern
- 3 possible failure scenarios
- Minimal reproduction case for each risk
- CVSS 3.1 score estimation for security issues
- Memory safety impact assessment (Rust/C/C++ contexts)
- Alternative implementations considered

!! Format:
EMERGENCY-LEVEL: [BLOOD-RED/CRIMSON/GOLDENROD]
EVIDENCE:
  - Code excerpt: |
      <affected lines>
  - Risk scenarios: 
    1. <failure mode>
    2. <failure mode> 
    3. <failure mode>
PROPOSED DEFENSE: 
  - <concrete code change>
  - <validation technique>
  - <long-term prevention strategy>
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
    args = parser.parse_args()
    
    # Validate arguments
    if args.type == 'commit' and not args.commit:
        parser.error("--commit is required when type is 'commit'")
    if args.type == 'range' and (not args.start_commit or not args.end_commit):
        parser.error("--start-commit and --end-commit are required when type is 'range'")
    
    tool = CodeReviewTool()
    tool_args = {
        "review_type": args.type
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