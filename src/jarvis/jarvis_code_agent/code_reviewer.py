# -*- coding: utf-8 -*-
"""代码审查模块。

将 CodeAgent 中的 review 相关逻辑独立出来，
支持通过 @Review 内置命令触发单次代码审查。
"""

import json
import re
from typing import Any, Optional

from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.tag import ot
from jarvis.jarvis_utils.git_utils import (
    get_diff,
    get_diff_between_commits,
    get_latest_commit_hash,
)


class CodeReviewer:
    """独立的代码审查器。

    从 CodeAgent 中提取的审查逻辑，支持单次审查和审查+修复循环。
    可通过 @Review 命令触发单次审查，也可由 CodeAgent 内部调用完整审查循环。
    """

    def __init__(
        self,
        model: Any = None,
        start_commit: Optional[str] = None,
        non_interactive: bool = True,
        quick_mode: bool = False,
    ) -> None:
        """初始化代码审查器。

        参数:
            model: 模型实例（用于生成审查目标）
            start_commit: 起始 commit hash
            non_interactive: 是否非交互模式
            quick_mode: 是否极速模式
        """
        self.model = model
        self.start_commit = start_commit
        self.non_interactive = non_interactive
        self.quick_mode = quick_mode

    def truncate_diff_for_review(self, git_diff: str, token_ratio: float = 0.4) -> str:
        """截断 git diff 以适应 token 限制（用于 review）。"""
        if not git_diff or not git_diff.strip():
            return git_diff

        from jarvis.jarvis_utils.embedding import get_context_token_count
        from jarvis.jarvis_utils.config import get_max_input_token_count

        max_input_tokens = get_max_input_token_count()
        max_diff_tokens = int(max_input_tokens * token_ratio)
        diff_token_count = get_context_token_count(git_diff)

        if diff_token_count <= max_diff_tokens:
            return git_diff

        files = set()
        pattern = r"^diff --git a/([^\s]+) b/([^\s]+)$"
        for line in git_diff.split("\n"):
            match = re.match(pattern, line)
            if match:
                file_a = match.group(1)
                file_b = match.group(2)
                files.add(file_b)
                if file_a != file_b:
                    files.add(file_a)
        modified_files = sorted(list(files))

        lines = git_diff.split("\n")
        truncated_lines = []
        current_tokens = 0

        for line in lines:
            line_tokens = get_context_token_count(line)
            if current_tokens + line_tokens > max_diff_tokens:
                truncated_lines.append("")
                truncated_lines.append(
                    "# ⚠️ diff 内容过大，已截断显示。如需查看完整内容，请使用 git diff 命令。"
                )
                truncated_lines.append(
                    f"# 原始diff共 {len(lines)} 行，{diff_token_count} tokens"
                )
                truncated_lines.append(
                    f"# 显示前 {len(truncated_lines) - 3} 行，约 {current_tokens} tokens"
                )
                truncated_lines.append(
                    f"# 限制: {max_diff_tokens} tokens (输入窗口的 {token_ratio * 100:.0f}%)"
                )

                if self.start_commit:
                    truncated_lines.append("")
                    truncated_lines.append(f"# 起始 Commit ID: {self.start_commit}")

                if modified_files:
                    truncated_lines.append("")
                    truncated_lines.append(
                        f"# 完整修改文件列表（共 {len(modified_files)} 个文件）："
                    )
                    for file_path in modified_files:
                        truncated_lines.append(f"#   - {file_path}")

                break

            truncated_lines.append(line)
            current_tokens += line_tokens

        return "\n".join(truncated_lines)

    def generate_review_target(self, max_retries: int = 3) -> str:
        """生成代码审查的目标和验收准则。

        注意：本方法会获取当前 git diff 并基于实际代码变更生成验收标准，
        而不是基于完整的对话历史，以避免将已提交的代码也包含在验收标准中。
        """
        from jarvis.jarvis_platform.registry import PlatformRegistry

        if self.model is None:
            PrettyOutput.auto_print("⚠ 模型实例不存在，无法生成审查目标")
            return "任务目标: 完成用户需求\n验收准则: 代码修改应正确完成用户需求"

        messages = self.model.get_messages()
        if not messages:
            PrettyOutput.auto_print("⚠ 无历史消息，无法生成审查目标")
            return "任务目标: 完成用户需求\n验收准则: 代码修改应正确完成用户需求"

        try:
            new_model = PlatformRegistry().get_smart_platform()
        except Exception as e:
            PrettyOutput.auto_print(f"⚠ 创建模型实例失败: {e}")
            return "任务目标: 完成用户需求\n验收准则: 代码修改应正确完成用户需求"

        new_model.set_messages(messages)
        new_model.set_suppress_output(False)

        # 获取当前 git diff 并截断，用于生成更精准的验收标准
        git_diff = self.check_and_get_git_diff()
        diff_for_prompt = ""
        if git_diff:
            # 使用 0.2 的 token 比例截断 diff，避免占用过多上下文
            diff_for_prompt = self.truncate_diff_for_review(git_diff, token_ratio=0.2)

        prompt = """请根据对话历史和代码变更，总结本次代码审查应关注的任务目标和验收准则。

【重要提示】
- **只关注当前未提交的代码变更**：如果对话历史中包含多次修复迭代，请只关注最终当前的代码状态
- **忽略已提交的代码**：不要将历史对话中已经提交过的代码纳入验收标准
- **基于实际变更生成验收标准**：参考下方的代码变更摘要，确保验收标准与实际修改匹配

请确保输出包含以下四个关键部分（必须包含这些关键字）：
1. 任务目标 - 说明本次代码修改应该完成什么
2. 验收准则 - 具体的、可验证的准则，用于判断代码修改是否正确完成
3. 关键变更点 - 本次修改涉及的关键变更点
4. 关键信息导航 - 提供审查时需要关注的关键信息位置，包括：
   - 关键文件路径：本次修改涉及的文件完整路径
   - 关键函数/类位置：修改涉及的函数名、类名及其所在文件和行号范围
   - 关键依赖关系：修改影响的上下游模块或接口
   - 关键配置/常量：涉及的配置项、常量定义位置

请不要抑制模型的输出，尽可能详细和完整地总结。不需要输出JSON格式。

**重要：你的输出中必须原样包含以下4个关键词（不能省略或替换为同义词），否则验证将失败：**
- "任务目标"
- "验收准则"
- "关键变更点"
- "关键信息导航"""

        # 如果有代码变更摘要，添加到 prompt 中
        if diff_for_prompt:
            prompt += f"\n\n【代码变更摘要】\n```diff\n{diff_for_prompt}\n```"

        # 如果有 start_commit，在 prompt 中追加提示，只走查该 commit 之后的代码
        if self.start_commit:
            prompt += (
                f"\n\n<start_commit_context>\n"
                f"本次任务的初始 Git Commit 是：`{self.start_commit}`\n"
                f"请只走查该 commit 之后的代码变更，"
                f"不需要审查该 commit 之前已有的代码。\n"
                f"</start_commit_context>"
            )

        required_keywords = ["任务目标", "验收准则", "关键变更点", "关键信息导航"]

        for retry in range(max_retries):
            try:
                if retry == 0:
                    PrettyOutput.auto_print("🎯 正在生成代码审查目标...")
                else:
                    PrettyOutput.auto_print(
                        f"🔧 第 {retry + 1}/{max_retries} 次重试生成审查目标..."
                    )

                response = new_model.chat_until_success(prompt)
                if not response:
                    continue

                response_str = str(response)

                missing_keywords = [
                    kw for kw in required_keywords if kw not in response_str
                ]
                if missing_keywords:
                    PrettyOutput.auto_print(
                        f"⚠ 审查目标缺少关键字: {', '.join(missing_keywords)}"
                    )
                    prompt += f"\n\n你上次的输出如下：\n```\n{response_str}\n```\n\n注意：上次输出缺少以下关键字: {', '.join(missing_keywords)}，请基于上次输出补充完整，确保所有关键字都出现。"
                    continue

                PrettyOutput.auto_print("✅ 审查目标生成成功")
                PrettyOutput.print_markdown(response_str, title="📋 代码审查目标")
                return response_str

            except Exception as e:
                PrettyOutput.auto_print(f"⚠ 生成审查目标时出错: {e}")
                continue

        user_input = ""
        for msg in messages:
            if msg.get("role") == "user" and msg.get("content"):
                user_input = msg["content"]
                break

        if user_input:
            PrettyOutput.auto_print("⚠ 所有重试失败，回退到用户原始需求")
            return f"任务目标: {user_input}\n验收准则: 代码修改应正确完成用户需求"
        else:
            PrettyOutput.auto_print("⚠ 所有重试失败，使用默认审查目标")
            return "任务目标: 完成用户需求\n验收准则: 代码修改应正确完成用户需求"

    def build_review_prompts(
        self,
        review_target: str,
        git_diff: str,
        modification_history: Optional[str] = None,
        start_commit: Optional[str] = None,
    ) -> tuple:
        """构建 review Agent 的 prompts。"""
        system_prompt = """你是代码审查专家。你的任务是审查代码修改是否正确完成了用户需求。

审查标准：
1. 功能完整性：代码修改是否完整实现了用户需求的所有功能点？
2. 代码正确性：修改的代码逻辑是否正确，有无明显的 bug 或错误？
3. 代码质量：代码是否符合最佳实践，有无明显的代码异味？
4. 潜在风险：修改是否可能引入新的问题或破坏现有功能？

审查要求：
- 仔细阅读用户需求、代码生成总结（summary）和代码修改（git diff）
- **对代码生成总结中的关键信息进行充分验证**：不能盲目信任总结，必须结合 git diff 和实际代码逐条核对
- 如需了解更多上下文，必须使用 read_code 工具读取相关文件以验证总结中提到的行为/位置/文件是否真实存在并符合描述
- 基于实际代码进行审查，不要凭空假设
- 如果代码生成总结与实际代码不一致，应以实际代码为准，并将不一致情况作为问题记录
- 只关注本次修改相关的问题，不要审查无关代码
- **尊重用户原始需求**：如果用户在需求中明确支持某个方案或实现方式，不应将其判定为风险或问题，除非该方案存在明显的错误或违反安全原则"""

        commit_info = f"【起始 Commit】\n{start_commit}\n\n" if start_commit else ""
        user_prompt = f"""请审查以下代码修改是否正确完成了用户需求。

【任务目标与验收准则】
{review_target}

{commit_info}【完整的修改历史】
{modification_history if modification_history else "无修改历史（如为空，说明主 Agent 未生成总结或未进行修复）"}

【代码修改（Git Diff）】
```diff
{git_diff}

```

请仔细审查代码修改，并特别注意：

- 修改历史包含了初始生成和所有修复阶段的总结
- 不要直接相信总结中的描述，而是将其视为"待核实的说明"
- 对总结中提到的每一个关键修改点（如函数/文件/行为变化），都应在 git diff 或实际代码中找到对应依据
- 如发现总结与实际代码不一致，必须在审查结果中指出

如需要可使用 read_code 工具查看更多上下文。

如果审查完毕，直接输出 {ot("!!!COMPLETE!!!")}，不要输出其他任何内容。
"""

        summary_prompt = """请输出 JSON 格式的审查结果，格式如下：

```json
{
  "ok": true/false,
  "issues": [
    {
      "type": "问题类型",
      "description": "问题描述",
      "location": "问题位置（文件:行号）",
      "suggestion": "修复建议"
    }
  ],
  "summary": "审查总结"
}
```

注意：
- 如果代码修改完全满足用户需求且无明显问题，设置 ok 为 true
- 如果存在需要修复的问题，设置 ok 为 false，并在 issues 中列出所有问题
- 每个问题都要提供具体的修复建议"""

        return system_prompt, user_prompt, summary_prompt

    def _try_parse_json(self, content: str) -> tuple:
        """尝试解析JSON，返回(成功, 结果, json字符串)"""
        # 首先尝试匹配 ```json ... ``` 代码块
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", content)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # 尝试匹配裸 JSON 对象
            json_match = re.search(r'\{[\s\S]*"ok"[\s\S]*\}', content)
            if json_match:
                json_str = json_match.group(0)
            else:
                return False, None, None

        try:
            result = json.loads(json_str)
            if isinstance(result, dict):
                return True, result, json_str
            else:
                return False, None, json_str
        except json.JSONDecodeError:
            return False, None, json_str

    def parse_review_result(
        self,
        review_result: str,
        review_agent: Optional[Any] = None,
        max_retries: int = 3,
    ) -> dict:
        """解析 review 结果，支持格式修复。

        参数:
            review_result: review Agent 的输出
            review_agent: review Agent 实例，用于格式修复（可选）
            max_retries: 最大重试次数

        返回:
            dict: 解析后的审查结果，包含 ok/issues/summary 字段
        """
        default_result = {"ok": True, "issues": [], "summary": "审查完成"}

        if not review_result or not review_result.strip():
            return default_result

        # 第一次尝试解析
        success, result, json_str = self._try_parse_json(review_result)
        if success and result is not None:
            return {
                "ok": result.get("ok", True),
                "issues": result.get("issues", []),
                "summary": result.get("summary", ""),
            }

        # 如果没有提供review_agent，无法修复，回退到简单解析
        if review_agent is None:
            # 尝试从结果中提取 JSON（兼容旧逻辑）
            json_pattern = r"```json\s*\n([\s\S]*?)\n\s*```"
            json_matches = re.findall(json_pattern, review_result)

            if json_matches:
                for json_str in reversed(json_matches):
                    try:
                        result = json.loads(json_str.strip())
                        if isinstance(result, dict) and "ok" in result:
                            return result
                    except json.JSONDecodeError:
                        continue

            # 尝试直接解析整个结果
            try:
                result = json.loads(review_result.strip())
                if isinstance(result, dict) and "ok" in result:
                    return result
            except json.JSONDecodeError:
                pass

            # 尝试查找花括号包围的 JSON
            brace_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
            brace_matches = re.findall(brace_pattern, review_result)
            if brace_matches:
                for match in reversed(brace_matches):
                    try:
                        result = json.loads(match)
                        if isinstance(result, dict) and "ok" in result:
                            return result
                    except json.JSONDecodeError:
                        continue

            # 如果无法解析为 JSON，检查是否包含通过/失败的关键字
            result_lower = review_result.lower()
            if any(
                kw in result_lower
                for kw in ["通过", "pass", "ok", "no issue", "no problem", "没问题"]
            ):
                return default_result

            if any(
                kw in result_lower
                for kw in [
                    "问题",
                    "issue",
                    "bug",
                    "error",
                    "风险",
                    "risk",
                    "失败",
                    "fail",
                ]
            ):
                return {
                    "ok": False,
                    "issues": [
                        {
                            "type": "未解析",
                            "description": review_result,
                            "location": "未知",
                            "suggestion": "请手动检查",
                        }
                    ],
                    "summary": "审查发现可能存在问题，但无法自动解析详细结果",
                }

            return default_result

        # 尝试修复格式
        summary = review_result
        for retry in range(max_retries):
            PrettyOutput.auto_print(
                f"🔧 第 {retry + 1}/{max_retries} 次尝试修复 JSON 格式..."
            )

            fix_prompt = f"""
之前的review回复格式不正确，无法解析为有效的JSON格式。

原始回复内容：
```
{summary}
```

请严格按照以下JSON格式重新组织你的回复：

```json
{{
    "ok": true/false,  // 表示代码是否通过审查
    "summary": "总体评价和建议",  // 简短总结
    "issues": [  // 问题列表，如果没有问题则为空数组
        {{
            "type": "问题类型",  // 如: bug, style, performance, security等
            "description": "问题描述",
            "location": "问题位置",  // 文件名和行号
            "suggestion": "修复建议"
        }}
    ]
}}
```

确保回复只包含上述JSON格式，不要包含其他解释或文本。"""

            try:
                # 使用review_agent的底层model进行修复，保持review_agent的专用配置和系统prompt
                fixed_summary = review_agent.model.chat_until_success(fix_prompt)
                if fixed_summary:
                    success, result, _ = self._try_parse_json(str(fixed_summary))
                    if success and result is not None:
                        PrettyOutput.auto_print(
                            f"✅ JSON格式修复成功（第 {retry + 1} 次）"
                        )
                        return {
                            "ok": result.get("ok", True),
                            "issues": result.get("issues", []),
                            "summary": result.get("summary", ""),
                        }
                    else:
                        PrettyOutput.auto_print("⚠ 修复后的JSON仍无法解析")
                        summary = str(fixed_summary)  # 使用修复后的内容继续尝试
                else:
                    PrettyOutput.auto_print("⚠ 修复未返回结果")
            except Exception as e:
                PrettyOutput.auto_print(f"⚠ 修复JSON格式时出错: {e}")

        # 3次修复都失败，标记需要重新review
        PrettyOutput.auto_print("❌ JSON格式修复失败，需要重新进行review")
        return {
            "ok": False,
            "issues": [],
            "summary": "JSON_FORMAT_ERROR",
            "need_re_review": True,
        }

    def check_and_get_git_diff(self) -> Optional[str]:
        """检查并获取 git diff。"""
        try:
            if self.start_commit:
                latest_commit = get_latest_commit_hash()
                if latest_commit and self.start_commit != latest_commit:
                    git_diff = get_diff_between_commits(
                        self.start_commit, latest_commit
                    )
                else:
                    git_diff = get_diff()
            else:
                git_diff = get_diff()
        except Exception as e:
            PrettyOutput.auto_print(f"⚠ 获取 git diff 失败: {e}")
            return None

        if not git_diff or not git_diff.strip():
            return None

        return git_diff

    def run_single_review(
        self,
        review_target: Optional[str] = None,
        modification_history: Optional[str] = None,
        use_tools: Optional[list] = None,
        non_interactive: Optional[bool] = None,
        quick_mode: Optional[bool] = None,
    ) -> dict:
        """执行单次代码审查（不走修复循环）。

        供 @Review 命令调用，执行一次审查并返回结果。

        参数:
            review_target: 审查目标（如为None则自动生成）
            modification_history: 修改历史
            use_tools: Agent使用的工具列表（默认为None，使用内置默认）
            non_interactive: 是否非交互模式（默认使用初始化时的设置）
            quick_mode: 是否极速模式（默认使用初始化时的设置）

        返回:
            dict: 审查结果，包含 ok/issues/summary 字段
        """
        # 1. 获取 git diff
        git_diff = self.check_and_get_git_diff()
        if not git_diff:
            PrettyOutput.auto_print("⚠ 没有检测到代码修改，无需审查")
            return {"ok": True, "issues": [], "summary": "没有代码修改需要审查"}

        # 2. 截断 diff
        git_diff = self.truncate_diff_for_review(git_diff)

        # 3. 生成审查目标（如果未提供）
        if not review_target:
            review_target = self.generate_review_target()

        # 4. 构建 prompts
        system_prompt, user_prompt, summary_prompt = self.build_review_prompts(
            review_target=review_target,
            git_diff=git_diff,
            modification_history=modification_history,
            start_commit=self.start_commit,
        )

        # 5. 创建审查 Agent 并执行
        from jarvis.jarvis_platform.registry import PlatformRegistry
        from jarvis.jarvis_agent import Agent

        try:
            review_model = PlatformRegistry().get_smart_platform()
        except Exception as e:
            PrettyOutput.auto_print(f"⚠ 创建审查模型失败: {e}")
            return {"ok": True, "issues": [], "summary": f"审查模型创建失败: {e}"}

        # 使用传入参数或初始化时的设置
        effective_non_interactive = (
            non_interactive if non_interactive is not None else self.non_interactive
        )
        effective_quick_mode = quick_mode if quick_mode is not None else self.quick_mode

        if use_tools is not None:
            review_agent = Agent(
                model=review_model,
                system_prompt=system_prompt,
                name="Code Reviewer",
                need_summary=True,
                summary_prompt=summary_prompt,
                use_methodology=False,
                use_analysis=False,
                non_interactive=effective_non_interactive,
                quick_mode=effective_quick_mode,
                use_tools=use_tools,
            )
        else:
            review_agent = Agent(
                model=review_model,
                system_prompt=system_prompt,
                name="Code Reviewer",
                need_summary=True,
                summary_prompt=summary_prompt,
                use_methodology=False,
                use_analysis=False,
                non_interactive=effective_non_interactive,
                quick_mode=effective_quick_mode,
            )

        PrettyOutput.auto_print("🔍 正在执行代码审查...")
        review_result = review_agent.run(user_prompt)

        # 6. 解析审查结果
        if not review_result:
            return {"ok": True, "issues": [], "summary": "审查未返回结果"}

        parsed_result = self.parse_review_result(
            str(review_result), review_agent=review_agent
        )

        # 7. 展示审查结果
        if parsed_result.get("ok", True):
            PrettyOutput.auto_print("✅ 代码审查通过")
            if parsed_result.get("summary"):
                PrettyOutput.print_markdown(
                    parsed_result["summary"], title="📋 审查总结"
                )
        else:
            PrettyOutput.auto_print("❌ 代码审查发现问题")
            issues = parsed_result.get("issues", [])
            if issues:
                issues_text = "\n".join(
                    f"  {i + 1}. [{issue.get('type', '未知')}] {issue.get('description', '无描述')}"
                    f"\n     位置: {issue.get('location', '未知')}"
                    f"\n     建议: {issue.get('suggestion', '无建议')}"
                    for i, issue in enumerate(issues)
                )
                PrettyOutput.print_markdown(
                    f"发现 {len(issues)} 个问题：\n{issues_text}",
                    title="⚠️ 审查问题列表",
                )
            if parsed_result.get("summary"):
                PrettyOutput.print_markdown(
                    parsed_result["summary"], title="📋 审查总结"
                )

        return parsed_result

    @staticmethod
    def build_review_fix_prompt(review_result: dict) -> str:
        """根据审查结果构建修复prompt

        Args:
            review_result: run_single_review()返回的审查结果dict，包含ok/issues/summary字段

        Returns:
            结构化的修复prompt字符串，如果无问题则返回空字符串
        """
        issues = review_result.get("issues", [])
        if not issues:
            return ""

        issues_text = "\n".join(
            f"  {i + 1}. [{issue.get('type', '未知')}] {issue.get('description', '无描述')}"
            f"\n     位置: {issue.get('location', '未知')}"
            f"\n     建议: {issue.get('suggestion', '无建议')}"
            for i, issue in enumerate(issues)
        )

        prompt = f"""代码审查发现以下问题，请修复：

【审查结果】
{review_result.get("summary", "")}

【问题列表】
{issues_text}

请根据上述问题进行修复，确保代码正确实现用户需求。"""
        return prompt

    def run_review_with_fix(
        self,
        modification_history: str = "",
        max_iterations: int = 3,
        use_tools: Optional[list] = None,
        non_interactive: Optional[bool] = None,
        quick_mode: Optional[bool] = None,
        on_fix: Optional[Any] = None,
        on_generate_fix_summary: Optional[Any] = None,
        on_handle_uncommitted_changes: Optional[Any] = None,
    ) -> None:
        """执行审查+修复循环。

        每轮审查发现问题后，调用 on_fix 回调进行修复，然后继续下一轮审查，
        直到审查通过或达到最大迭代次数。

        参数:
            modification_history: 初始修改历史
            max_iterations: 最大审查轮数（0表示无限）
            use_tools: Agent使用的工具列表
            non_interactive: 是否非交互模式
            quick_mode: 是否极速模式
            on_fix: 修复回调函数，接收 fix_prompt 字符串，用于执行修复
            on_generate_fix_summary: 生成修复总结的回调函数，返回字符串
            on_handle_uncommitted_changes: 处理未提交更改的回调函数
        """
        from jarvis.jarvis_utils.input import user_confirm

        iteration = 0
        # 如果 max_iterations 为 0，表示无限 review
        is_infinite = max_iterations == 0

        while is_infinite or iteration < max_iterations:
            iteration += 1

            # 每轮review开始前询问用户
            effective_non_interactive = (
                non_interactive if non_interactive is not None else self.non_interactive
            )
            if not user_confirm(
                f"是否进行第 {iteration} 轮代码审查？",
                default=True if effective_non_interactive else False,
            ):
                PrettyOutput.auto_print(f"ℹ️ 用户跳过第 {iteration} 轮代码审查")
                break

            # 获取 git diff
            git_diff = self.check_and_get_git_diff()
            if git_diff is None:
                return

            # 每轮审查开始前显示清晰的提示信息
            if is_infinite:
                PrettyOutput.auto_print(
                    f"🔄 代码审查循环 - 第 {iteration} 轮（无限模式）"
                )
            else:
                PrettyOutput.auto_print(
                    f"🔄 代码审查循环 - 第 {iteration}/{max_iterations} 轮"
                )

            if is_infinite:
                PrettyOutput.auto_print(
                    f"🔍 开始第 {iteration} 轮代码审查...（无限模式）"
                )
            else:
                PrettyOutput.auto_print(
                    f"🔍 开始第 {iteration}/{max_iterations} 轮代码审查..."
                )

            # 对 git diff 进行 token 限制处理
            truncated_git_diff = self.truncate_diff_for_review(
                git_diff, token_ratio=0.4
            )
            if truncated_git_diff != git_diff:
                PrettyOutput.auto_print("⚠️ git diff 过长，已截断以适应 token 限制")

            # 生成审查目标
            review_target = self.generate_review_target()

            # 构建 review prompts
            sys_prompt, usr_prompt, sum_prompt = self.build_review_prompts(
                review_target,
                truncated_git_diff,
                modification_history,
                self.start_commit,
            )

            # 创建并运行 review agent
            from jarvis.jarvis_agent import Agent

            effective_quick_mode = (
                quick_mode if quick_mode is not None else self.quick_mode
            )

            if use_tools is not None:
                review_agent = Agent(
                    system_prompt=sys_prompt,
                    name=f"CodeReview-Agent-{iteration}",
                    summary_prompt=sum_prompt,
                    need_summary=True,
                    auto_complete=True,
                    use_tools=use_tools,
                    non_interactive=effective_non_interactive,
                    use_methodology=False,
                    use_analysis=False,
                    quick_mode=effective_quick_mode,
                )
            else:
                review_agent = Agent(
                    system_prompt=sys_prompt,
                    name=f"CodeReview-Agent-{iteration}",
                    summary_prompt=sum_prompt,
                    need_summary=True,
                    auto_complete=True,
                    non_interactive=effective_non_interactive,
                    use_methodology=False,
                    use_analysis=False,
                    quick_mode=effective_quick_mode,
                )

            # 运行 review
            summary = review_agent.run(usr_prompt)

            # 解析审查结果，支持格式修复和重新review
            result = self.parse_review_result(
                str(summary) if summary else "", review_agent=review_agent
            )

            # 检查是否需要重新review（JSON格式错误3次修复失败）
            if result.get("need_re_review", False):
                PrettyOutput.auto_print(
                    f"🔄 JSON格式修复失败，重新进行代码审查（第 {iteration} 轮）"
                )
                # 跳过当前迭代，重新开始review流程
                continue

            if result["ok"]:
                PrettyOutput.auto_print(f"✅ 代码审查通过（第 {iteration} 轮）")
                if result.get("summary"):
                    PrettyOutput.auto_print(f"   {result['summary']}")
                return

            # 审查未通过，需要修复
            PrettyOutput.auto_print(f"⚠️ 代码审查发现问题（第 {iteration} 轮）")
            for i, issue in enumerate(result.get("issues", []), 1):
                issue_type = issue.get("type", "未知")
                description = issue.get("description", "无描述")
                location = issue.get("location", "未知位置")
                suggestion = issue.get("suggestion", "无建议")
                PrettyOutput.auto_print(f"   {i}. [{issue_type}] {description}")
                PrettyOutput.auto_print(f"      位置: {location}")
                PrettyOutput.auto_print(f"      建议: {suggestion}")

            # 只有在非无限模式下才检查是否达到最大迭代次数
            if not is_infinite and iteration >= max_iterations:
                PrettyOutput.auto_print(
                    f"⚠️ 已达到最大审查轮数（{max_iterations} 轮），停止审查"
                )
                return

            # 构建修复 prompt
            fix_prompt = self.build_review_fix_prompt(result)

            PrettyOutput.auto_print("🔧 开始修复问题...")

            # 调用修复回调
            if on_fix:
                try:
                    on_fix(fix_prompt)
                except RuntimeError as e:
                    PrettyOutput.auto_print(f"⚠️ 修复过程中出错: {e}")
                    return

            # 处理未提交的更改
            if on_handle_uncommitted_changes:
                on_handle_uncommitted_changes()

            # 生成修复总结并追加到修改历史
            if on_generate_fix_summary:
                fix_summary = on_generate_fix_summary()
                PrettyOutput.auto_print(f"🔍 修复总结: {fix_summary}")
                if fix_summary:
                    modification_history += (
                        f"\n\n【第 {iteration} 轮修复总结】\n{fix_summary}"
                    )
