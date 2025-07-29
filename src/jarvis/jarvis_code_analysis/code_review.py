# -*- coding: utf-8 -*-
import os
import re
import subprocess
import tempfile
import sys
from typing import Any, Dict, List, Optional

import typer

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_code_analysis.checklists.loader import get_language_checklist
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.read_code import ReadCodeTool
from jarvis.jarvis_utils.globals import get_agent, current_agent_name
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.tag import ct, ot
from jarvis.jarvis_utils.utils import init_env, is_context_overflow

app = typer.Typer(help="自动代码审查工具")


class CodeReviewTool:
    name = "code_review"
    description = "自动代码审查工具，用于分析代码变更"
    labels = ["code", "analysis", "review"]
    parameters = {
        "type": "object",
        "properties": {
            "review_type": {
                "type": "string",
                "description": "审查类型：'commit' 审查特定提交，'current' 审查当前变更，'range' 审查提交范围，'file' 审查特定文件",
                "enum": ["commit", "current", "range", "file"],
                "default": "current",
            },
            "commit_sha": {
                "type": "string",
                "description": "要分析的提交SHA（review_type='commit'时必填）",
            },
            "start_commit": {
                "type": "string",
                "description": "起始提交SHA（review_type='range'时必填）",
            },
            "end_commit": {
                "type": "string",
                "description": "结束提交SHA（review_type='range'时必填）",
            },
            "file_path": {
                "type": "string",
                "description": "要审查的文件路径（review_type='file'时必填）",
            },
            "root_dir": {
                "type": "string",
                "description": "代码库根目录路径（可选）",
                "default": ".",
            },
        },
        "required": [],
    }

    def _detect_languages_from_files(self, file_paths: List[str]) -> List[str]:
        """
        Detect programming languages from a list of file paths using file extensions.
        Returns a list of detected languages ('c_cpp', 'go', 'python', 'rust', 'java', 'javascript', 'typescript', etc.).
        """
        if not file_paths:
            return []

        # Extension-based language detection
        languages = set()
        for file_path in file_paths:
            file_path = file_path.lower()
            _, ext = os.path.splitext(file_path)

            # Get base name for special files without extensions
            base_name = os.path.basename(file_path)

            # C/C++
            if ext in [
                ".c",
                ".cpp",
                ".cc",
                ".cxx",
                ".h",
                ".hpp",
                ".hxx",
                ".inl",
                ".ipp",
            ]:
                languages.add("c_cpp")

            # Go
            elif ext in [".go"]:
                languages.add("go")

            # Python
            elif ext in [".py", ".pyw", ".pyi", ".pyx", ".pxd"] or base_name in [
                "requirements.txt",
                "setup.py",
                "pyproject.toml",
            ]:
                languages.add("python")

            # Rust
            elif ext in [".rs", ".rlib"] or base_name in ["Cargo.toml", "Cargo.lock"]:
                languages.add("rust")

            # Java
            elif ext in [".java", ".class", ".jar"] or base_name in [
                "pom.xml",
                "build.gradle",
            ]:
                languages.add("java")

            # JavaScript
            elif ext in [".js", ".mjs", ".cjs", ".jsx"]:
                languages.add("javascript")

            # TypeScript
            elif ext in [".ts", ".tsx", ".cts", ".mts"]:
                languages.add("typescript")

            # PHP
            elif ext in [".php", ".phtml", ".php5", ".php7", ".phps"]:
                languages.add("php")

            # Ruby
            elif ext in [".rb", ".rake", ".gemspec"] or base_name in [
                "Gemfile",
                "Rakefile",
            ]:
                languages.add("ruby")

            # Swift
            elif ext in [".swift"]:
                languages.add("swift")

            # Kotlin
            elif ext in [".kt", ".kts"]:
                languages.add("kotlin")

            # C#
            elif ext in [".cs", ".csx"]:
                languages.add("csharp")

            # SQL
            elif ext in [".sql"]:
                languages.add("sql")

            # Shell/Bash
            elif (
                ext in [".sh", ".bash"]
                or base_name.startswith(".bash")
                or base_name.startswith(".zsh")
            ):
                languages.add("shell")

            # HTML/CSS
            elif ext in [".html", ".htm", ".xhtml"]:
                languages.add("html")
            elif ext in [".css", ".scss", ".sass", ".less"]:
                languages.add("css")

            # XML/JSON/YAML (config files)
            elif ext in [
                ".xml",
                ".xsd",
                ".dtd",
                ".tld",
                ".jsp",
                ".jspx",
                ".tag",
                ".tagx",
            ]:
                languages.add("xml")
            elif ext in [".json", ".jsonl", ".json5"]:
                languages.add("json")
            elif ext in [".yaml", ".yml"]:
                languages.add("yaml")

            # Markdown/Documentation
            elif ext in [".md", ".markdown", ".rst", ".adoc"]:
                languages.add("markdown")

            # Docker
            elif ext in [".dockerfile"] or base_name in [
                "Dockerfile",
                "docker-compose.yml",
                "docker-compose.yaml",
            ]:
                languages.add("docker")

            # Terraform
            elif ext in [".tf", ".tfvars"]:
                languages.add("terraform")

            # Makefile
            elif ext in [".mk"] or base_name == "Makefile":
                languages.add("makefile")

        # Map to our primary language groups for checklist purposes
        primary_languages = set()
        language_mapping = {
            "c_cpp": "c_cpp",
            "go": "go",
            "python": "python",
            "rust": "rust",
            "java": "java",
            "javascript": "javascript",
            "typescript": "typescript",
            "php": "php",
            "ruby": "ruby",
            "swift": "swift",
            "kotlin": "kotlin",
            "csharp": "csharp",
            "sql": "sql",
            "shell": "shell",
            "html": "html",
            "css": "css",
            "xml": "xml",
            "json": "json",
            "yaml": "yaml",
            "markdown": "docs",
            "docker": "docker",
            "terraform": "terraform",
            "makefile": "devops",
        }

        # Map detected languages to primary language groups
        for lang in languages:
            primary_lang = language_mapping.get(lang)
            if primary_lang:
                # Only keep languages we have checklists for
                if primary_lang in [
                    "c_cpp",
                    "go",
                    "python",
                    "rust",
                    "java",
                    "javascript",
                    "typescript",
                    "csharp",
                    "swift",
                    "php",
                    "shell",
                    "sql",
                    "ruby",
                    "kotlin",
                    "html",
                    "css",
                    "xml",
                    "json",
                    "yaml",
                    "docker",
                    "terraform",
                    "docs",
                    "markdown",
                    "devops",
                    "makefile",
                ]:
                    primary_languages.add(primary_lang)

        return list(primary_languages)

    def _get_language_checklist(self, language: str) -> str:
        """Get the checklist for a specific language."""
        checklist = get_language_checklist(language)
        return checklist if checklist else ""

    def execute(
        self, args: Dict[str, Any], agent: Optional["Agent"] = None
    ) -> Dict[str, Any]:
        try:
            review_type = args.get("review_type", "current").strip()
            root_dir = args.get("root_dir", ".")

            # Store current directory
            original_dir = os.getcwd()

            try:
                # Change to root_dir
                os.chdir(root_dir)

                # Variables to store file paths and diff output
                file_paths = []
                diff_output = ""

                # Build git diff command based on review type
                print("📊 正在获取代码变更...")

                if review_type == "commit":
                    if "commit_sha" not in args:
                        return {
                            "success": False,
                            "stdout": {},
                            "stderr": "commit_sha is required for commit review type",
                        }
                    commit_sha = args["commit_sha"].strip()
                    diff_cmd = f"git show {commit_sha} | cat -"

                    # Execute git command and get diff output
                    diff_output = subprocess.check_output(
                        diff_cmd, shell=True, text=True, encoding="utf-8", errors="replace"
                    )
                    if not diff_output:
                        return {
                            "success": False,
                            "stdout": {},
                            "stderr": "No changes to review",
                        }

                    # Extract changed files using git command
                    # Use git show with proper formatting to avoid needing grep
                    files_cmd = f"git show --name-only --pretty=format: {commit_sha}"
                    try:
                        files_output = subprocess.check_output(
                            files_cmd, shell=True, text=True
                        )
                        # Filter out empty lines without using grep
                        file_paths = [
                            f.strip() for f in files_output.split("\n") if f.strip()
                        ]
                    except subprocess.CalledProcessError:
                        # Fallback to regex extraction if git command fails
                        file_pattern = r"diff --git a/.*?\s+b/(.*?)(\n|$)"
                        files = re.findall(file_pattern, diff_output)
                        file_paths = [match[0] for match in files]

                elif review_type == "range":
                    if "start_commit" not in args or "end_commit" not in args:
                        return {
                            "success": False,
                            "stdout": {},
                            "stderr": "start_commit and end_commit are required for range review type",
                        }
                    start_commit = args["start_commit"].strip()
                    end_commit = args["end_commit"].strip()
                    diff_cmd = f"git diff {start_commit}..{end_commit} | cat -"

                    # Execute git command and get diff output
                    diff_output = subprocess.check_output(
                        diff_cmd, shell=True, text=True, encoding="utf-8", errors="replace"
                    )
                    if not diff_output:
                        return {
                            "success": False,
                            "stdout": {},
                            "stderr": "No changes to review",
                        }

                    # Extract changed files using git command
                    files_cmd = f"git diff --name-only {start_commit}..{end_commit}"
                    try:
                        files_output = subprocess.check_output(
                            files_cmd, shell=True, text=True
                        )
                        file_paths = [
                            f.strip() for f in files_output.split("\n") if f.strip()
                        ]
                    except subprocess.CalledProcessError:
                        # Fallback to regex extraction if git command fails
                        file_pattern = r"diff --git a/.*?\s+b/(.*?)(\n|$)"
                        files = re.findall(file_pattern, diff_output)
                        file_paths = [match[0] for match in files]

                elif review_type == "file":
                    if "file_path" not in args:
                        return {
                            "success": False,
                            "stdout": {},
                            "stderr": "file_path is required for file review type",
                        }
                    file_path = args["file_path"].strip()
                    file_paths = [file_path]
                    diff_output = ReadCodeTool().execute(
                        {"files": [{"path": file_path}]}
                    )["stdout"]

                else:  # current changes
                    diff_cmd = "git diff HEAD | cat -"

                    # Execute git command and get diff output
                    diff_output = subprocess.check_output(
                        diff_cmd, shell=True, text=True, encoding="utf-8", errors="replace"
                    )
                    if not diff_output:
                        return {
                            "success": False,
                            "stdout": {},
                            "stderr": "No changes to review",
                        }

                    # Extract changed files using git command
                    files_cmd = "git diff --name-only HEAD"
                    try:
                        files_output = subprocess.check_output(
                            files_cmd, shell=True, text=True
                        )
                        file_paths = [
                            f.strip() for f in files_output.split("\n") if f.strip()
                        ]
                    except subprocess.CalledProcessError:
                        # Fallback to regex extraction if git command fails
                        file_pattern = r"diff --git a/.*?\s+b/(.*?)(\n|$)"
                        files = re.findall(file_pattern, diff_output)
                        file_paths = [match[0] for match in files]

                # Detect languages from the file paths
                detected_languages = self._detect_languages_from_files(file_paths)

                # Add review type and related information to the diff output
                review_info = f"""
----- 代码审查信息 -----
审查类型: {review_type}"""

                # Add specific information based on review type
                if review_type == "commit":
                    review_info += f"\n提交SHA: {args['commit_sha']}"
                elif review_type == "range":
                    review_info += f"\n起始提交: {args['start_commit']}\n结束提交: {args['end_commit']}"
                elif review_type == "file":
                    review_info += f"\n文件路径: {args['file_path']}"
                else:  # current changes
                    review_info += "\n当前未提交修改"

                # Add file list
                if file_paths:
                    review_info += "\n\n----- 变更文件列表 -----"
                    for i, path in enumerate(file_paths, 1):
                        review_info += f"\n{i}. {path}"

                # Add language-specific checklists
                if detected_languages:
                    review_info += "\n\n----- 检测到的编程语言 -----"
                    review_info += f"\n检测到的语言: {', '.join(detected_languages)}"

                    review_info += "\n\n----- 语言特定审查清单 -----"
                    for lang in detected_languages:
                        checklist = self._get_language_checklist(lang)
                        if checklist:
                            review_info += f"\n{checklist}"

                review_info += "\n------------------------\n\n"

                # Combine review info with diff output
                diff_output = review_info + diff_output

                PrettyOutput.print(diff_output, OutputType.CODE, lang="diff")
                print("✅ 代码变更获取完成")

                system_prompt = """<code_review_guide>
<role>
你是一位精益求精的首席代码审查专家，拥有多年企业级代码审计经验。你需要对所有代码变更进行极其全面、严谨且深入的审查，确保代码质量达到最高标准。
</role>

<tools>
# 代码审查工具选择
优先使用执行shell命令进行静态分析，而非依赖内置代码审查功能：

| 分析需求 | 首选工具 | 备选工具 |
|---------|---------|----------|
| 代码质量检查 | execute_script | - |
| 语法检查 | 语言特定lint工具 | - |
| 安全分析 | 安全扫描工具 | - |
| 代码统计 | loc | - |
</tools>

<commands>
# 推荐命令
- Python: `pylint <file_path>`, `flake8 <file_path>`, `mypy <file_path>`
- JavaScript/TypeScript: `eslint <file_path>`, `tsc --noEmit <file_path>`
- Java: `checkstyle <file_path>`, `pmd -d <file_path>`
- C/C++: `cppcheck <file_path>`, `clang-tidy <file_path>`
- Go: `golint <file_path>`, `go vet <file_path>`
- Rust: `cargo clippy`, `rustfmt --check <file_path>`
- 通用搜索：`rg "pattern" <files>` 查找特定代码模式
</commands>

<standards>
# 专家审查标准
1. 必须逐行分析每个修改文件，细致审查每一处变更，不遗漏任何细节
2. 基于坚实的证据识别问题，不做主观臆测，给出明确的问题定位和详细分析
3. 对每个问题提供完整可执行的解决方案，包括精确的改进代码
4. 确保报告条理清晰、层次分明，便于工程师快速采取行动
</standards>

<framework>
# 全面审查框架 (SCRIPPPS)

<category>
## S - 安全与风险 (Security & Risk)
- [ ] 发现所有潜在安全漏洞：注入攻击、授权缺陷、数据泄露风险
- [ ] 检查加密实现、密钥管理、敏感数据处理
- [ ] 审核权限验证逻辑、身份认证机制
- [ ] 检测OWASP Top 10安全风险和针对特定语言/框架的漏洞
</category>

<category>
## C - 正确性与完整性 (Correctness & Completeness)
- [ ] 验证业务逻辑和算法实现的准确性
- [ ] 全面检查条件边界、空值处理和异常情况
- [ ] 审核所有输入验证、参数校验和返回值处理
- [ ] 确保循环和递归的正确终止条件
- [ ] 严格检查线程安全和并发控制机制
</category>

<category>
## R - 可靠性与鲁棒性 (Reliability & Robustness)
- [ ] 评估代码在异常情况下的行为和恢复能力
- [ ] 审查错误处理、异常捕获和恢复策略
- [ ] 检查资源管理：内存、文件句柄、连接池、线程
- [ ] 评估容错设计和失败优雅降级机制
</category>

<category>
## I - 接口与集成 (Interface & Integration)
- [ ] 检查API合约遵守情况和向后兼容性
- [ ] 审核与外部系统的集成点和交互逻辑
- [ ] 验证数据格式、序列化和协议实现
- [ ] 评估系统边界处理和跨服务通信安全性
</category>

<category>
## P - 性能与效率 (Performance & Efficiency)
- [ ] 识别潜在性能瓶颈：CPU、内存、I/O、网络
- [ ] 审查数据结构选择和算法复杂度
- [ ] 检查资源密集型操作、数据库查询优化
- [ ] 评估缓存策略、批处理优化和并行处理机会
</category>

<category>
## P - 可移植性与平台适配 (Portability & Platform Compatibility)
- [ ] 检查跨平台兼容性问题和依赖项管理
- [ ] 评估配置管理和环境适配设计
- [ ] 审核国际化和本地化支持
- [ ] 验证部署和运行时环境需求
</category>

<category>
## S - 结构与可维护性 (Structure & Maintainability)
- [ ] 评估代码组织、模块划分和架构符合性
- [ ] 审查代码重复、设计模式应用和抽象水平
- [ ] 检查命名规范、代码风格和项目约定
- [ ] 评估文档完整性、注释质量和代码可读性
</category>
</framework>

<severity>
# 问题严重程度分级
- [ ] 严重 (P0): 安全漏洞、数据丢失风险、系统崩溃、功能严重缺陷
- [ ] 高危 (P1): 显著性能问题、可能导致部分功能失效、系统不稳定
- [ ] 中等 (P2): 功能局部缺陷、次优设计、明显的技术债务
- [ ] 低危 (P3): 代码风格问题、轻微优化机会、文档改进建议
</severity>

<output>
# 输出规范
针对每个文件的问题必须包含：
- [ ] 精确文件路径和问题影响范围
- [ ] 问题位置（起始行号-结束行号）
- [ ] 详尽问题描述，包括具体影响和潜在风险
- [ ] 严重程度分级（P0-P3）并说明理由
- [ ] 具体改进建议，提供完整、可执行的代码示例

所有审查发现必须：
1. 基于确凿的代码证据
2. 说明具体问题而非笼统评论
3. 提供清晰的技术原理分析
4. 给出完整的改进实施步骤
</output>

<language_specific>
# 语言特定审查
如果在审查信息中检测到了语言特定的审查清单，请按照清单中的项目进行逐一检查，并在报告中针对每个适用的清单项给出详细分析。
</language_specific>

我将分析上传的代码差异文件，进行全面的代码审查。
</code_review_guide>"""
                from jarvis.jarvis_tools.registry import ToolRegistry

                tool_registry = ToolRegistry()
                tool_registry.dont_use_tools(["code_review"])

                # Use the provided agent's model_group or get it from globals
                calling_agent = agent or get_agent(current_agent_name)
                model_group = None
                if calling_agent and hasattr(calling_agent, "model") and calling_agent.model:
                    model_group = calling_agent.model.model_group

                agent = Agent(
                    system_prompt=system_prompt,
                    name="Code Review Agent",
                    model_group=model_group,
                    summary_prompt=f"""<code_review_report>
<overview>
# 整体评估
[提供对整体代码质量、架构和主要关注点的简明概述，总结主要发现]
</overview>

<detailed_issues>
# 详细问题清单

<file>
## 文件: [文件路径]
[如果该文件没有发现问题，则明确说明"未发现问题"]

<issue>
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
</issue>

<issue>
### 问题 2
...
</issue>
</file>

<file>
## 文件: [文件路径2]
...
</file>
</detailed_issues>

<language_specific>
# 语言特定问题
[根据检测到的编程语言，提供针对语言特定清单中项目的分析]
</language_specific>

<best_practices>
# 最佳实践建议
[提供适用于整个代码库的改进建议和最佳实践]
</best_practices>

<summary>
# 总结
[总结主要问题和优先处理建议]
</summary>
</code_review_report>

<notes>
如果没有发现任何问题，请在REPORT标签内进行全面分析后明确说明"经过全面审查，未发现问题"并解释原因。
必须确保对所有修改的文件都进行了审查，并在报告中明确提及每个文件，即使某些文件没有发现问题。
如果检测到了特定编程语言，请参考语言特定的审查清单进行评估，并在报告中包含相关分析。
</notes>

输出格式：
{ot("REPORT")}
[在此处插入完整MARKDOWN格式的审查报告]
{ct("REPORT")}""",
                    output_handler=[tool_registry],  # type: ignore
                    llm_type="thinking",
                    auto_complete=False,
                )

                # Determine if we need to split the diff due to size
                max_diff_size = 100 * 1024 * 1024  # Limit to 100MB

                if len(diff_output) > max_diff_size:
                    PrettyOutput.print(
                        f"代码差异内容总大小超过限制 ({len(diff_output)} > {max_diff_size} 字节)，将截断内容",
                        OutputType.WARNING,
                    )
                    diff_output = (
                        diff_output[:max_diff_size]
                        + "\n\n[diff content truncated due to size limitations...]"
                    )

                # Prepare the user prompt for code review
                user_prompt = f"""请对以下代码变更进行全面审查。

代码信息：
- 审查类型: {review_type}
- 变更文件列表: {len(file_paths)} 个文件
- 检测到的编程语言: {', '.join(detected_languages) if detected_languages else '未检测到特定语言'}

请根据SCRIPPPS框架和语言特定的审查清单进行分析，提供详细的代码审查报告。"""

                # Write the full diff output to a temporary file for uploading
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".diff", delete=False
                ) as temp_file:
                    temp_file_path = temp_file.name
                    temp_file.write(diff_output)
                    temp_file.flush()

                try:
                    # Check if content is too large
                    is_large_content = is_context_overflow(diff_output, model_group)

                    # Upload the file to the agent's model
                    if is_large_content:
                        if not agent.model or not agent.model.support_upload_files():
                            return {
                                "success": False,
                                "stdout": "",
                                "stderr": "代码差异太大，无法处理",
                            }
                        print("📤 正在上传代码差异文件...")
                        upload_success = agent.model.upload_files([temp_file_path])
                        if upload_success:
                            print("✅ 已成功上传代码差异文件")
                        else:
                            return {
                                "success": False,
                                "stdout": "",
                                "stderr": "上传代码差异文件失败",
                            }

                    # Prepare the prompt based on upload status
                    if is_large_content:
                        # When file is uploaded, reference it in the prompt
                        complete_prompt = (
                            user_prompt
                            + f"""

我已上传了一个包含代码差异的文件。该文件包含:
- 审查类型: {review_type}
- 变更文件数量: {len(file_paths)} 个文件
- 检测到的编程语言: {', '.join(detected_languages) if detected_languages else '未检测到特定语言'}

请基于上传的代码差异文件进行全面审查，并生成详细的代码审查报告。"""
                        )
                        # Run the agent with the prompt
                        result = agent.run(complete_prompt)
                    else:
                        complete_prompt = (
                            user_prompt
                            + "\n\n代码差异内容:\n```diff\n"
                            + diff_output
                            + "\n```"
                        )
                        result = agent.run(complete_prompt)
                finally:
                    # Clean up the temporary file
                    if os.path.exists(temp_file_path):
                        try:
                            os.unlink(temp_file_path)
                        except Exception:
                            PrettyOutput.print(
                                f"临时文件 {temp_file_path} 未能删除",
                                OutputType.WARNING,
                            )

                return {"success": True, "stdout": result, "stderr": ""}
            finally:
                # Always restore original directory
                os.chdir(original_dir)

        except Exception as e:
            return {
                "success": False,
                "stdout": {},
                "stderr": f"Review failed: {str(e)}",
            }


def extract_code_report(result: str) -> str:
    sm = re.search(ot("REPORT") + r"\n(.*?)\n" + ct("REPORT"), result, re.DOTALL)
    if sm:
        return sm.group(1)
    return result


@app.command("commit")
def review_commit(
    commit: str = typer.Argument(..., help="要审查的提交SHA"),
    root_dir: str = typer.Option(".", "--root-dir", help="代码库根目录路径"),
):
    """审查指定的提交"""
    tool = CodeReviewTool()
    tool_args = {"review_type": "commit", "commit_sha": commit, "root_dir": root_dir}
    result = tool.execute(tool_args)
    if result["success"]:
        PrettyOutput.section("自动代码审查结果:", OutputType.SUCCESS)
        report = extract_code_report(result["stdout"])
        PrettyOutput.print(report, OutputType.SUCCESS, lang="markdown")
    else:
        PrettyOutput.print(result["stderr"], OutputType.WARNING)


@app.command("current")
def review_current(
    root_dir: str = typer.Option(".", "--root-dir", help="代码库根目录路径"),
):
    """审查当前的变更"""
    tool = CodeReviewTool()
    tool_args = {"review_type": "current", "root_dir": root_dir}
    result = tool.execute(tool_args)
    if result["success"]:
        PrettyOutput.section("自动代码审查结果:", OutputType.SUCCESS)
        report = extract_code_report(result["stdout"])
        PrettyOutput.print(report, OutputType.SUCCESS, lang="markdown")
    else:
        PrettyOutput.print(result["stderr"], OutputType.WARNING)


@app.command("range")
def review_range(
    start_commit: str = typer.Argument(..., help="起始提交SHA"),
    end_commit: str = typer.Argument(..., help="结束提交SHA"),
    root_dir: str = typer.Option(".", "--root-dir", help="代码库根目录路径"),
):
    """审查提交范围"""
    tool = CodeReviewTool()
    tool_args = {
        "review_type": "range",
        "start_commit": start_commit,
        "end_commit": end_commit,
        "root_dir": root_dir,
    }
    result = tool.execute(tool_args)
    if result["success"]:
        PrettyOutput.section("自动代码审查结果:", OutputType.SUCCESS)
        report = extract_code_report(result["stdout"])
        PrettyOutput.print(report, OutputType.SUCCESS, lang="markdown")
    else:
        PrettyOutput.print(result["stderr"], OutputType.WARNING)


@app.command("file")
def review_file(
    file: str = typer.Argument(..., help="要审查的文件路径"),
    root_dir: str = typer.Option(".", "--root-dir", help="代码库根目录路径"),
):
    """审查指定的文件"""
    tool = CodeReviewTool()
    tool_args = {"review_type": "file", "file_path": file, "root_dir": root_dir}
    result = tool.execute(tool_args)
    if result["success"]:
        PrettyOutput.section("自动代码审查结果:", OutputType.SUCCESS)
        report = extract_code_report(result["stdout"])
        PrettyOutput.print(report, OutputType.SUCCESS, lang="markdown")
    else:
        PrettyOutput.print(result["stderr"], OutputType.WARNING)


def cli():
    """Typer application entry point"""
    init_env("欢迎使用 Jarvis-CodeReview，您的代码审查助手已准备就绪！")
    app()


def main():
    """Main entry point for the script"""
    cli()


if __name__ == "__main__":
    main()
