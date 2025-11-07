# -*- coding: utf-8 -*-
"""Jarvis代码代理模块。

该模块提供CodeAgent类，用于处理代码修改任务。
"""

import os
import subprocess
import sys
import hashlib
from typing import List, Optional, Tuple, Any

import typer

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_agent.events import AFTER_TOOL_CALL
from jarvis.jarvis_code_agent.lint import (
    get_lint_tools,
    get_lint_commands_for_files,
    group_commands_by_tool,
)
from jarvis.jarvis_code_agent.code_analyzer.build_validator import BuildValidator, BuildResult, FallbackBuildValidator
from jarvis.jarvis_code_agent.build_validation_config import BuildValidationConfig
from jarvis.jarvis_git_utils.git_commiter import GitCommitTool
from jarvis.jarvis_code_agent.code_analyzer import ContextManager
from jarvis.jarvis_code_agent.code_analyzer.llm_context_recommender import ContextRecommender
from jarvis.jarvis_code_agent.code_analyzer import ImpactAnalyzer, parse_git_diff_to_edits
from jarvis.jarvis_utils.config import (
    is_confirm_before_apply_patch,
    is_enable_static_analysis,
    is_enable_build_validation,
    get_build_validation_timeout,
    get_git_check_mode,
    set_config,
    get_data_dir,
    is_plan_enabled,
    is_enable_intent_recognition,
    is_enable_impact_analysis,
)
from jarvis.jarvis_utils.git_utils import (
    confirm_add_new_files,
    find_git_root_and_cd,
    get_commits_between,
    get_diff,
    get_diff_file_list,
    get_latest_commit_hash,
    get_recent_commits_with_files,
    handle_commit_workflow,
    has_uncommitted_changes,
)
from jarvis.jarvis_utils.input import get_multiline_input, user_confirm
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import get_loc_stats, init_env, _acquire_single_instance_lock

app = typer.Typer(help="Jarvis 代码助手")


class CodeAgent:
    """Jarvis系统的代码修改代理。

    负责处理代码分析、修改和git操作。
    """

    def __init__(
        self,
        model_group: Optional[str] = None,
        need_summary: bool = True,
        append_tools: Optional[str] = None,
        tool_group: Optional[str] = None,
        non_interactive: Optional[bool] = None,
        plan: Optional[bool] = None,
        **kwargs,
    ):
        self.root_dir = os.getcwd()
        self.tool_group = tool_group
        self.non_interactive = non_interactive

        # 初始化上下文管理器
        self.context_manager = ContextManager(self.root_dir)
        # 上下文推荐器将在Agent创建后初始化（需要LLM模型）
        self.context_recommender: Optional[ContextRecommender] = None

        # 检测 git username 和 email 是否已设置
        self._check_git_config()
        base_tools = [
            "execute_script",
            "search_web",
            "ask_user",
            "read_code",
            "save_memory",
            "retrieve_memory",
            "clear_memory",
            "sub_code_agent",
        ]

        if append_tools:
            additional_tools = [
                t for t in (tool.strip() for tool in append_tools.split(",")) if t
            ]
            base_tools.extend(additional_tools)
            # 去重
            base_tools = list(dict.fromkeys(base_tools))

        code_system_prompt = self._get_system_prompt()
        # 先加载全局规则（数据目录 rules），再加载项目规则（.jarvis/rules），并拼接为单一规则块注入
        global_rules = self._read_global_rules()
        project_rules = self._read_project_rules()

        combined_parts: List[str] = []
        if global_rules:
            combined_parts.append(global_rules)
        if project_rules:
            combined_parts.append(project_rules)

        if combined_parts:
            merged_rules = "\n\n".join(combined_parts)
            code_system_prompt = (
                f"{code_system_prompt}\n\n"
                f"<rules>\n{merged_rules}\n</rules>"
            )
        self.agent = Agent(
            system_prompt=code_system_prompt,
            name="CodeAgent",
            auto_complete=False,
            model_group=model_group,
            need_summary=need_summary,
            use_methodology=False,  # 禁用方法论
            use_analysis=False,  # 禁用分析
            non_interactive=self.non_interactive,
            plan=bool(plan) if plan is not None else is_plan_enabled(),
            use_tools=base_tools,  # 仅启用限定工具
        )

        # 建立CodeAgent与Agent的关联，便于工具获取上下文管理器
        self.agent._code_agent = self

        # 初始化上下文推荐器（需要LLM模型）
        if hasattr(self.agent, 'model') and self.agent.model:
            try:
                self.context_recommender = ContextRecommender(
                    self.context_manager,
                    llm_model=self.agent.model
                )
            except Exception as e:
                # LLM推荐器初始化失败
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"上下文推荐器初始化失败: {e}，将跳过上下文推荐功能")

        self.agent.event_bus.subscribe(AFTER_TOOL_CALL, self._on_after_tool_call)

    def _get_system_prompt(self) -> str:
        """获取代码工程师的系统提示词"""
        return """
<code_engineer_guide>
## 角色定位
你是Jarvis系统的代码工程师，一个专业的代码分析和修改助手。你的职责是：
- 理解用户的代码需求，并提供高质量的实现方案
- 精确分析项目结构和代码，准确定位需要修改的位置
- 编写符合项目风格和标准的代码
- 在修改代码时保持谨慎，确保不破坏现有功能
- 做出专业的技术决策，减少用户决策负担

## 核心原则
- 自主决策：基于专业判断做出决策，减少用户询问
- 高效精准：提供完整解决方案，避免反复修改
- 修改审慎：修改前充分分析影响范围，做到一次把事情做好
- 工具精通：选择最高效工具路径解决问题

## 工作流程
1. **项目分析**：分析项目结构，确定需修改的文件
2. **需求分析**：理解需求意图，选择影响最小的实现方案
3. **代码分析**：详细分析目标文件，禁止虚构现有代码
   - 结构分析：优先使用文件搜索工具快速定位文件和目录结构
   - 内容搜索：优先使用全文搜索工具进行函数、类、变量等内容的搜索，避免遗漏
   - 依赖关系：如需分析依赖、调用关系，可结合代码分析工具辅助
   - 代码阅读：使用 read_code 工具获取目标文件的完整内容或指定范围内容，禁止凭空假设代码
   - 变更影响：如需分析变更影响范围，可结合版本控制工具辅助判断
   - 上下文理解：系统已维护项目的符号表和依赖关系图，可以帮助理解代码结构和依赖关系
   - 工具优先级：优先使用自动化工具，减少人工推断，确保分析结果准确
4. **方案设计**：确定最小变更方案，保持代码结构
5. **实施修改**：遵循"先读后写"原则，保持代码风格一致性

## 工具使用
- 项目结构：优先使用文件搜索命令查找文件
- 代码搜索：优先使用内容搜索工具
- 代码阅读：优先使用read_code工具
- 仅在命令行工具不足时使用专用工具

## 文件编辑工具使用规范
- 对于部分文件内容修改，使用edit_file工具
- 对于需要重写整个文件内容，使用 REWRITE 操作
- 对于简单的修改，可以使用execute_script工具执行shell命令完成

## 子任务与子CodeAgent
- 当出现以下情况时，优先使用 sub_code_agent 工具将子任务托管给子 CodeAgent（自动完成并生成总结）：
  - 需要在当前任务下并行推进较大且相对独立的代码改造
  - 涉及多文件/多模块的大范围变更，或需要较长的工具调用链
  - 需要隔离上下文以避免污染当前对话（如探索性改动、PoC）
  - 需要专注于单一子问题，阶段性产出可独立复用的结果
- 其余常规、小粒度改动直接在当前 Agent 中完成即可
</code_engineer_guide>

<say_to_llm>
1. 保持专注与耐心，先分析再行动；将复杂问题拆解为可执行的小步骤
2. 以结果为导向，同时简明呈现关键推理依据，避免无关噪音
3. 信息不足时，主动提出最少且关键的问题以澄清需求
4. 输出前自检：一致性、边界条件、依赖关系、回滚与风险提示
5. 选择对现有系统影响最小且可回退的方案，确保稳定性与可维护性
6. 保持项目风格：结构、命名、工具使用与现有规范一致
7. 工具优先：使用搜索、read_code、版本控制与静态分析验证结论，拒绝臆测
8. 面对错误与不确定，给出修复计划与备选路径，持续迭代优于停滞
9. 沟通清晰：用要点列出结论、变更范围、影响评估与下一步行动
10. 持续改进：沉淀经验为可复用清单，下一次做得更快更稳
</say_to_llm>
"""

    def _read_project_rules(self) -> Optional[str]:
        """读取 .jarvis/rules 内容，如果存在则返回字符串，否则返回 None"""
        try:
            rules_path = os.path.join(self.root_dir, ".jarvis", "rules")
            if os.path.exists(rules_path) and os.path.isfile(rules_path):
                with open(rules_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read().strip()
                return content if content else None
        except Exception:
            # 读取规则失败时忽略，不影响主流程
            pass
        return None

    def _read_global_rules(self) -> Optional[str]:
        """读取数据目录 rules 内容，如果存在则返回字符串，否则返回 None"""
        try:
            rules_path = os.path.join(get_data_dir(), "rules")
            if os.path.exists(rules_path) and os.path.isfile(rules_path):
                with open(rules_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read().strip()
                return content if content else None
        except Exception:
            # 读取规则失败时忽略，不影响主流程
            pass
        return None

    def _check_git_config(self) -> None:
        """检查 git username 和 email 是否已设置，如果没有则提示并退出"""
        try:
            # 检查 git user.name
            result = subprocess.run(
                ["git", "config", "--get", "user.name"],
                capture_output=True,
                text=True,
                check=False,
            )
            username = result.stdout.strip()

            # 检查 git user.email
            result = subprocess.run(
                ["git", "config", "--get", "user.email"],
                capture_output=True,
                text=True,
                check=False,
            )
            email = result.stdout.strip()

            # 如果任一配置未设置，提示并退出
            if not username or not email:
                missing_configs = []
                if not username:
                    missing_configs.append(
                        '  git config --global user.name "Your Name"'
                    )
                if not email:
                    missing_configs.append(
                        '  git config --global user.email "your.email@example.com"'
                    )

                message = "❌ Git 配置不完整\n\n请运行以下命令配置 Git：\n" + "\n".join(
                    missing_configs
                )
                PrettyOutput.print(message, OutputType.WARNING)
                # 通过配置控制严格校验模式（JARVIS_GIT_CHECK_MODE）：
                # - warn: 仅告警并继续，后续提交可能失败
                # - strict: 严格模式（默认），直接退出
                mode = get_git_check_mode().lower()
                if mode == "warn":
                    PrettyOutput.print(
                        "已启用 Git 校验警告模式（JARVIS_GIT_CHECK_MODE=warn），将继续运行。"
                        "注意：后续提交可能失败，请尽快配置 git user.name 与 user.email。",
                        OutputType.INFO,
                    )
                    return
                sys.exit(1)

        except FileNotFoundError:
            PrettyOutput.print("❌ 未找到 git 命令，请先安装 Git", OutputType.ERROR)
            sys.exit(1)
        except Exception as e:
            PrettyOutput.print(f"❌ 检查 Git 配置时出错: {str(e)}", OutputType.ERROR)
            sys.exit(1)

    def _find_git_root(self) -> str:
        """查找并切换到git根目录

        返回:
            str: git根目录路径
        """

        curr_dir = os.getcwd()
        git_dir = find_git_root_and_cd(curr_dir)
        self.root_dir = git_dir

        return git_dir

    def _get_git_tracked_files_info(self, max_files: int = 100) -> Optional[str]:
        """获取git托管的文件列表或目录结构
        
        如果文件数量超过max_files，则返回目录结构（不含文件）
        
        参数:
            max_files: 文件数量阈值，超过此值则返回目录结构
            
        返回:
            str: 文件列表或目录结构的字符串表示，失败时返回None
        """
        try:
            # 获取所有git托管的文件
            result = subprocess.run(
                ["git", "ls-files"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
                cwd=self.root_dir,
            )
            
            if result.returncode != 0 or not result.stdout.strip():
                return None
            
            files = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
            file_count = len(files)
            
            if file_count == 0:
                return None
            
            # 如果文件数量超过阈值，返回目录结构
            if file_count > max_files:
                # 提取所有目录路径
                dirs = set()
                for file_path in files:
                    # 获取文件所在的所有父目录
                    parts = file_path.split("/")
                    for i in range(1, len(parts)):
                        dir_path = "/".join(parts[:i])
                        if dir_path:
                            dirs.add(dir_path)
                
                # 构建树形目录结构
                dir_tree = {}
                for dir_path in sorted(dirs):
                    parts = dir_path.split("/")
                    current = dir_tree
                    for part in parts:
                        if part not in current:
                            current[part] = {}
                        current = current[part]
                
                def format_tree(tree: dict, prefix: str = "", is_last: bool = True) -> List[str]:
                    """格式化目录树"""
                    lines = []
                    items = sorted(tree.items())
                    for i, (name, subtree) in enumerate(items):
                        is_last_item = i == len(items) - 1
                        connector = "└── " if is_last_item else "├── "
                        lines.append(f"{prefix}{connector}{name}/")
                        
                        extension = "    " if is_last_item else "│   "
                        if subtree:
                            lines.extend(format_tree(subtree, prefix + extension, is_last_item))
                    return lines
                
                tree_lines = format_tree(dir_tree)
                return f"Git托管目录结构（共{file_count}个文件）:\n" + "\n".join(tree_lines)
            else:
                # 文件数量不多，直接返回文件列表
                files_str = "\n".join(f"  - {file}" for file in sorted(files))
                return f"Git托管文件列表（共{file_count}个文件）:\n{files_str}"
                
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
        except Exception:
            # 其他异常，静默失败
            return None

    def _update_gitignore(self, git_dir: str) -> None:
        """检查并更新.gitignore文件，确保忽略.jarvis目录，并追加常用语言的忽略规则（若缺失）

        参数:
            git_dir: git根目录路径
        """
        gitignore_path = os.path.join(git_dir, ".gitignore")

        # 常用忽略规则（按语言/场景分组）
        sections = {
            "General": [
                ".jarvis",
                ".DS_Store",
                "Thumbs.db",
                "*.log",
                "*.tmp",
                "*.swp",
                "*.swo",
                ".idea/",
                ".vscode/",
            ],
            "Python": [
                "__pycache__/",
                "*.py[cod]",
                "*$py.class",
                ".Python",
                "env/",
                "venv/",
                ".venv/",
                "build/",
                "dist/",
                "develop-eggs/",
                "downloads/",
                "eggs/",
                ".eggs/",
                "lib/",
                "lib64/",
                "parts/",
                "sdist/",
                "var/",
                "wheels/",
                "pip-wheel-metadata/",
                "share/python-wheels/",
                "*.egg-info/",
                ".installed.cfg",
                "*.egg",
                "MANIFEST",
                ".mypy_cache/",
                ".pytest_cache/",
                ".ruff_cache/",
                ".tox/",
                ".coverage",
                ".coverage.*",
                "htmlcov/",
                ".hypothesis/",
                ".ipynb_checkpoints",
                ".pyre/",
                ".pytype/",
            ],
            "Rust": [
                "target/",
            ],
            "Node": [
                "node_modules/",
                "npm-debug.log*",
                "yarn-debug.log*",
                "yarn-error.log*",
                "pnpm-debug.log*",
                "lerna-debug.log*",
                "dist/",
                "coverage/",
                ".turbo/",
                ".next/",
                ".nuxt/",
                "out/",
            ],
            "Go": [
                "bin/",
                "vendor/",
                "coverage.out",
            ],
            "Java": [
                "target/",
                "*.class",
                ".gradle/",
                "build/",
                "out/",
            ],
            "C/C++": [
                "build/",
                "cmake-build-*/",
                "*.o",
                "*.a",
                "*.so",
                "*.obj",
                "*.dll",
                "*.dylib",
                "*.exe",
                "*.pdb",
            ],
            ".NET": [
                "bin/",
                "obj/",
            ],
        }

        existing_content = ""
        if os.path.exists(gitignore_path):
            with open(gitignore_path, "r", encoding="utf-8", errors="replace") as f:
                existing_content = f.read()

        # 已存在的忽略项（去除注释与空行）
        existing_set = set(
            ln.strip()
            for ln in existing_content.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        )

        # 计算缺失项并准备追加内容
        new_lines: List[str] = []
        for name, patterns in sections.items():
            missing = [p for p in patterns if p not in existing_set]
            if missing:
                new_lines.append(f"# {name}")
                new_lines.extend(missing)
                new_lines.append("")  # 分组空行

        if not os.path.exists(gitignore_path):
            # 新建 .gitignore（仅包含缺失项；此处即为全部常用规则）
            with open(gitignore_path, "w", encoding="utf-8", newline="\n") as f:
                content_to_write = "\n".join(new_lines).rstrip()
                if content_to_write:
                    f.write(content_to_write + "\n")
            PrettyOutput.print("已创建 .gitignore 并添加常用忽略规则", OutputType.SUCCESS)
        else:
            if new_lines:
                # 追加缺失的规则
                with open(gitignore_path, "a", encoding="utf-8", newline="\n") as f:
                    # 若原文件不以换行结尾，先补一行
                    if existing_content and not existing_content.endswith("\n"):
                        f.write("\n")
                    f.write("\n".join(new_lines).rstrip() + "\n")
                PrettyOutput.print("已更新 .gitignore，追加常用忽略规则", OutputType.SUCCESS)

    def _handle_git_changes(self, prefix: str, suffix: str) -> None:
        """处理git仓库中的未提交修改"""

        if has_uncommitted_changes():

            git_commiter = GitCommitTool()
            git_commiter.execute({"prefix": prefix, "suffix": suffix, "agent": self.agent, "model_group": getattr(self.agent.model, "model_group", None)})

    def _init_env(self, prefix: str, suffix: str) -> None:
        """初始化环境，组合以下功能：
        1. 查找git根目录
        2. 检查并更新.gitignore文件
        3. 处理未提交的修改
        4. 配置git对换行符变化不敏感
        """

        git_dir = self._find_git_root()
        self._update_gitignore(git_dir)
        self._handle_git_changes(prefix, suffix)
        # 配置git对换行符变化不敏感
        self._configure_line_ending_settings()

    def _configure_line_ending_settings(self) -> None:
        """配置git对换行符变化不敏感，只在当前设置与目标设置不一致时修改"""
        target_settings = {
            "core.autocrlf": "false",
            "core.safecrlf": "false",
            "core.whitespace": "cr-at-eol",  # 忽略行尾的CR
        }

        # 获取当前设置并检查是否需要修改
        need_change = False
        current_settings = {}
        for key, target_value in target_settings.items():
            result = subprocess.run(
                ["git", "config", "--get", key],
                capture_output=True,
                text=True,
                check=False,
            )
            current_value = result.stdout.strip()
            current_settings[key] = current_value
            if current_value != target_value:
                need_change = True

        if not need_change:

            return

        PrettyOutput.print(
            "⚠️ 正在修改git换行符敏感设置，这会影响所有文件的换行符处理方式",
            OutputType.WARNING,
        )
        # 避免在循环中逐条打印，先拼接后统一打印
        lines = ["将进行以下设置："]
        for key, value in target_settings.items():
            current = current_settings.get(key, "未设置")
            lines.append(f"{key}: {current} -> {value}")
        PrettyOutput.print("\n".join(lines), OutputType.INFO)

        # 直接执行设置，不需要用户确认
        for key, value in target_settings.items():
            subprocess.run(["git", "config", key, value], check=True)

        # 对于Windows系统，提示用户可以创建.gitattributes文件
        if sys.platform.startswith("win"):
            self._handle_windows_line_endings()

        PrettyOutput.print("git换行符敏感设置已更新", OutputType.SUCCESS)

    def _handle_windows_line_endings(self) -> None:
        """在Windows系统上处理换行符问题，提供建议而非强制修改"""
        gitattributes_path = os.path.join(self.root_dir, ".gitattributes")

        # 检查是否已存在.gitattributes文件
        if os.path.exists(gitattributes_path):
            with open(gitattributes_path, "r", encoding="utf-8") as f:
                content = f.read()
            # 如果已经有换行符相关配置，就不再提示
            if any(keyword in content for keyword in ["text=", "eol=", "binary"]):
                return

        PrettyOutput.print(
            "提示：在Windows系统上，建议配置 .gitattributes 文件来避免换行符问题。",
            OutputType.INFO,
        )
        PrettyOutput.print(
            "这可以防止仅因换行符不同而导致整个文件被标记为修改。", OutputType.INFO
        )

        if user_confirm("是否要创建一个最小化的.gitattributes文件？", False):
            # 最小化的内容，只影响特定类型的文件
            minimal_content = """# Jarvis建议的最小化换行符配置
# 默认所有文本文件使用LF，只有Windows特定文件使用CRLF

# 默认所有文本文件使用LF
* text=auto eol=lf

# Windows批处理文件需要CRLF
*.bat text eol=crlf
*.cmd text eol=crlf
*.ps1 text eol=crlf
"""

            if not os.path.exists(gitattributes_path):
                with open(gitattributes_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(minimal_content)
                PrettyOutput.print(
                    "已创建最小化的 .gitattributes 文件", OutputType.SUCCESS
                )
            else:
                PrettyOutput.print(
                    "将以下内容追加到现有 .gitattributes 文件：", OutputType.INFO
                )
                PrettyOutput.print(minimal_content, OutputType.CODE, lang="text")
                if user_confirm("是否追加到现有文件？", True):
                    with open(
                        gitattributes_path, "a", encoding="utf-8", newline="\n"
                    ) as f:
                        f.write("\n" + minimal_content)
                    PrettyOutput.print("已更新 .gitattributes 文件", OutputType.SUCCESS)
        else:
            PrettyOutput.print(
                "跳过 .gitattributes 文件创建。如遇换行符问题，可手动创建此文件。",
                OutputType.INFO,
            )

    def _record_code_changes_stats(self, diff_text: str) -> None:
        """记录代码变更的统计信息。

        Args:
            diff_text: git diff的文本输出
        """
        from jarvis.jarvis_stats.stats import StatsManager
        import re

        # 匹配插入行数
        insertions_match = re.search(r"(\d+)\s+insertions?\(\+\)", diff_text)
        if insertions_match:
            insertions = int(insertions_match.group(1))
            StatsManager.increment(
                "code_lines_inserted", amount=insertions, group="code_agent"
            )

        # 匹配删除行数
        deletions_match = re.search(r"(\d+)\s+deletions?\(\-\)", diff_text)
        if deletions_match:
            deletions = int(deletions_match.group(1))
            StatsManager.increment(
                "code_lines_deleted", amount=deletions, group="code_agent"
            )

    def _handle_uncommitted_changes(self) -> None:
        """处理未提交的修改，包括：
        1. 提示用户确认是否提交
        2. 如果确认，则检查新增文件数量
        3. 如果新增文件超过20个，让用户确认是否添加
        4. 如果用户拒绝添加大量文件，提示修改.gitignore并重新检测
        5. 暂存并提交所有修改
        """
        if has_uncommitted_changes():
            # 获取代码变更统计
            try:
                diff_result = subprocess.run(
                    ["git", "diff", "HEAD", "--shortstat"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=True,
                )
                if diff_result.returncode == 0 and diff_result.stdout:
                    self._record_code_changes_stats(diff_result.stdout)
            except subprocess.CalledProcessError:
                pass

            PrettyOutput.print("检测到未提交的修改，是否要提交？", OutputType.WARNING)
            if not user_confirm("是否要提交？", True):
                return

            try:
                confirm_add_new_files()

                if not has_uncommitted_changes():
                    return

                # 获取当前分支的提交总数
                # 兼容空仓库或无 HEAD 的场景：失败时将提交计数视为 0，继续执行提交流程
                commit_count = 0
                try:
                    commit_result = subprocess.run(
                        ["git", "rev-list", "--count", "HEAD"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                    )
                    if commit_result.returncode == 0:
                        out = commit_result.stdout.strip()
                        if out.isdigit():
                            commit_count = int(out)
                except Exception:
                    commit_count = 0

                # 暂存所有修改
                subprocess.run(["git", "add", "."], check=True)

                # 提交变更
                subprocess.run(
                    ["git", "commit", "-m", f"CheckPoint #{commit_count + 1}"],
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                PrettyOutput.print(f"提交失败: {str(e)}", OutputType.ERROR)

    def _show_commit_history(
        self, start_commit: Optional[str], end_commit: Optional[str]
    ) -> List[Tuple[str, str]]:
        """显示两个提交之间的提交历史

        参数:
            start_commit: 起始提交hash
            end_commit: 结束提交hash

        返回:
            包含(commit_hash, commit_message)的元组列表
        """
        if start_commit and end_commit:
            commits = get_commits_between(start_commit, end_commit)
        else:
            commits = []

        if commits:
            # 统计生成的commit数量
            from jarvis.jarvis_stats.stats import StatsManager

            StatsManager.increment("commits_generated", group="code_agent")

            commit_messages = "检测到以下提交记录:\n" + "\n".join(
                f"- {commit_hash[:7]}: {message}" for commit_hash, message in commits
            )
            PrettyOutput.print(commit_messages, OutputType.INFO)
        return commits

    def _handle_commit_confirmation(
        self,
        commits: List[Tuple[str, str]],
        start_commit: Optional[str],
        prefix: str,
        suffix: str,
    ) -> None:
        """处理提交确认和可能的重置"""
        if commits and user_confirm("是否接受以上提交记录？", True):
            # 统计接受的commit数量
            from jarvis.jarvis_stats.stats import StatsManager

            StatsManager.increment("commits_accepted", group="code_agent")

            subprocess.run(
                ["git", "reset", "--mixed", str(start_commit)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            git_commiter = GitCommitTool()
            git_commiter.execute({"prefix": prefix, "suffix": suffix, "agent": self.agent, "model_group": getattr(self.agent.model, "model_group", None)})

            # 在用户接受commit后，根据配置决定是否保存记忆
            if self.agent.force_save_memory:
                self.agent.memory_manager.prompt_memory_save()
        elif start_commit:
            if user_confirm("是否要重置到初始提交？", True):
                os.system(f"git reset --hard {str(start_commit)}")  # 确保转换为字符串
                PrettyOutput.print("已重置到初始提交", OutputType.INFO)

    def run(self, user_input: str, prefix: str = "", suffix: str = "") -> Optional[str]:
        """使用给定的用户输入运行代码代理。

        参数:
            user_input: 用户的需求/请求

        返回:
            str: 描述执行结果的输出，成功时返回None
        """
        prev_dir = os.getcwd()
        try:
            self._init_env(prefix, suffix)
            start_commit = get_latest_commit_hash()

            # 获取项目统计信息并附加到用户输入
            loc_stats = get_loc_stats()
            commits_info = get_recent_commits_with_files()
            git_files_info = self._get_git_tracked_files_info()

            project_info = []
            if loc_stats:
                project_info.append(f"代码统计:\n{loc_stats}")
            if git_files_info:
                project_info.append(git_files_info)
            if commits_info:
                commits_str = "\n".join(
                    f"提交 {i+1}: {commit['hash'][:7]} - {commit['message']} ({len(commit['files'])}个文件)\n"
                    + "\n".join(f"    - {file}" for file in commit["files"][:5])
                    + ("\n    ..." if len(commit["files"]) > 5 else "")
                    for i, commit in enumerate(commits_info[:5])
                )
                project_info.append(f"最近提交:\n{commits_str}")

            first_tip = """请严格遵循以下规范进行代码修改任务：
            1. 每次响应仅执行一步操作，先分析再修改，避免一步多改。
            2. 充分利用工具理解用户需求和现有代码，禁止凭空假设。
            3. 如果不清楚要修改的文件，必须先分析并找出需要修改的文件，明确目标后再进行编辑。
            4. 代码编辑任务优先使用 PATCH 操作，确保搜索文本在目标文件中有且仅有一次精确匹配，保证修改的准确性和安全性。
            5. 如需大范围重写，才可使用 REWRITE 操作。
            6. 如遇信息不明，优先调用工具补充分析，不要主观臆断。
            """

            # 智能上下文推荐：根据用户输入推荐相关上下文
            context_recommendation_text = ""
            if self.context_recommender and is_enable_intent_recognition():
                try:
                    PrettyOutput.print("🔍 正在进行意图识别与上下文分析...", OutputType.INFO)
                    # 尝试从用户输入中提取目标文件和符号（简单启发式方法）
                    target_files = self._extract_file_paths_from_input(user_input)
                    target_symbols = self._extract_symbols_from_input(user_input)
                    
                    # 生成上下文推荐
                    recommendation = self.context_recommender.recommend_context(
                        user_input=user_input,
                        target_files=target_files,
                        target_symbols=target_symbols,
                    )
                    
                    # 格式化推荐结果
                    context_recommendation_text = self.context_recommender.format_recommendation(recommendation)
                    
                    if context_recommendation_text:
                        PrettyOutput.print("💡 正在生成智能上下文推荐...", OutputType.INFO)
                except Exception as e:
                    # 上下文推荐失败不应该影响主流程
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.debug(f"上下文推荐失败: {e}", exc_info=True)

            if project_info:
                enhanced_input = (
                    "项目概况:\n"
                    + "\n\n".join(project_info)
                    + "\n\n"
                    + first_tip
                    + context_recommendation_text
                    + "\n\n任务描述：\n"
                    + user_input
                )
            else:
                enhanced_input = first_tip + context_recommendation_text + "\n\n任务描述：\n" + user_input

            try:
                if self.agent.model:
                    self.agent.model.set_suppress_output(False)
                self.agent.run(enhanced_input)
            except RuntimeError as e:
                PrettyOutput.print(f"执行失败: {str(e)}", OutputType.WARNING)
                return str(e)



            self._handle_uncommitted_changes()
            end_commit = get_latest_commit_hash()
            commits = self._show_commit_history(start_commit, end_commit)
            self._handle_commit_confirmation(commits, start_commit, prefix, suffix)
            return None

        except RuntimeError as e:
            return f"Error during execution: {str(e)}"
        finally:
            # Ensure switching back to the original working directory after CodeAgent completes
            try:
                os.chdir(prev_dir)
            except Exception:
                pass

    def _build_name_status_map(self) -> dict:
        """构造按文件的状态映射与差异文本，删除文件不展示diff，仅提示删除"""
        status_map = {}
        try:
            head_exists = bool(get_latest_commit_hash())
            # 临时 -N 以包含未跟踪文件的差异检测
            subprocess.run(["git", "add", "-N", "."], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cmd = ["git", "diff", "--name-status"] + (["HEAD"] if head_exists else [])
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        finally:
            subprocess.run(["git", "reset"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if res.returncode == 0 and res.stdout:
            for line in res.stdout.splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                if not parts:
                    continue
                status = parts[0]
                if status.startswith("R") or status.startswith("C"):
                    # 重命名/复制：使用新路径作为键
                    if len(parts) >= 3:
                        old_path, new_path = parts[1], parts[2]
                        status_map[new_path] = status
                        # 也记录旧路径，便于匹配 name-only 的结果
                        status_map[old_path] = status
                    elif len(parts) >= 2:
                        status_map[parts[-1]] = status
                else:
                    if len(parts) >= 2:
                        status_map[parts[1]] = status
        return status_map

    def _get_file_diff(self, file_path: str) -> str:
        """获取单文件的diff，包含新增文件内容；失败时返回空字符串"""
        head_exists = bool(get_latest_commit_hash())
        try:
            # 为了让未跟踪文件也能展示diff，临时 -N 该文件
            subprocess.run(["git", "add", "-N", "--", file_path], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cmd = ["git", "diff"] + (["HEAD"] if head_exists else []) + ["--", file_path]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if res.returncode == 0:
                return res.stdout or ""
            return ""
        finally:
            subprocess.run(["git", "reset", "--", file_path], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _build_per_file_patch_preview(self, modified_files: List[str]) -> str:
        """构建按文件的补丁预览"""
        status_map = self._build_name_status_map()
        lines: List[str] = []

        def _get_file_numstat(file_path: str) -> Tuple[int, int]:
            """获取单文件的新增/删除行数，失败时返回(0,0)"""
            head_exists = bool(get_latest_commit_hash())
            try:
                # 让未跟踪文件也能统计到新增行数
                subprocess.run(["git", "add", "-N", "--", file_path], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                cmd = ["git", "diff", "--numstat"] + (["HEAD"] if head_exists else []) + ["--", file_path]
                res = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                if res.returncode == 0 and res.stdout:
                    for line in res.stdout.splitlines():
                        parts = line.strip().split("\t")
                        if len(parts) >= 3:
                            add_s, del_s = parts[0], parts[1]

                            def to_int(x: str) -> int:
                                try:
                                    return int(x)
                                except Exception:
                                    # 二进制或无法解析时显示为0
                                    return 0

                            return to_int(add_s), to_int(del_s)
            finally:
                subprocess.run(["git", "reset", "--", file_path], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return (0, 0)

        for f in modified_files:
            status = status_map.get(f, "")
            adds, dels = _get_file_numstat(f)
            total_changes = adds + dels

            # 删除文件：不展示diff，仅提示（附带删除行数信息如果可用）
            if (status.startswith("D")) or (not os.path.exists(f)):
                if dels > 0:
                    lines.append(f"- {f} 文件被删除（删除{dels}行）")
                else:
                    lines.append(f"- {f} 文件被删除")
                continue

            # 变更过大：仅提示新增/删除行数，避免输出超长diff
            if total_changes > 300:
                lines.append(f"- {f} 新增{adds}行/删除{dels}行（变更过大，预览已省略）")
                continue

            # 其它情况：展示该文件的diff
            file_diff = self._get_file_diff(f)
            if file_diff.strip():
                lines.append(f"文件: {f}\n```diff\n{file_diff}\n```")
            else:
                # 当无法获取到diff（例如重命名或特殊状态），避免空输出
                lines.append(f"- {f} 变更已记录（无可展示的文本差异）")
        return "\n".join(lines)

    def _update_context_for_modified_files(self, modified_files: List[str]) -> None:
        """更新上下文管理器：当文件被修改后，更新符号表和依赖图"""
        if not modified_files:
            return
        PrettyOutput.print("🔄 正在更新代码上下文...", OutputType.INFO)
        for file_path in modified_files:
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    self.context_manager.update_context_for_file(file_path, content)
                except Exception:
                    # 如果读取文件失败，跳过更新
                    pass

    def _analyze_edit_impact(self, modified_files: List[str]) -> Optional[Any]:
        """进行影响范围分析（如果启用）
        
        Returns:
            ImpactReport: 影响分析报告，如果未启用或失败则返回None
        """
        if not is_enable_impact_analysis():
            return None
        
        PrettyOutput.print("🔍 正在进行变更影响分析...", OutputType.INFO)
        try:
            impact_analyzer = ImpactAnalyzer(self.context_manager)
            all_edits = []
            for file_path in modified_files:
                if os.path.exists(file_path):
                    edits = parse_git_diff_to_edits(file_path, self.root_dir)
                    all_edits.extend(edits)
            
            if not all_edits:
                return None
            
            # 按文件分组编辑
            edits_by_file = {}
            for edit in all_edits:
                if edit.file_path not in edits_by_file:
                    edits_by_file[edit.file_path] = []
                edits_by_file[edit.file_path].append(edit)
            
            # 对每个文件进行影响分析
            impact_report = None
            for file_path, edits in edits_by_file.items():
                report = impact_analyzer.analyze_edit_impact(file_path, edits)
                if report:
                    # 合并报告
                    if impact_report is None:
                        impact_report = report
                    else:
                        # 合并多个报告，去重
                        impact_report.affected_files = list(set(impact_report.affected_files + report.affected_files))
                        
                        # 合并符号（基于文件路径和名称去重）
                        symbol_map = {}
                        for symbol in impact_report.affected_symbols + report.affected_symbols:
                            key = (symbol.file_path, symbol.name, symbol.line_start)
                            if key not in symbol_map:
                                symbol_map[key] = symbol
                        impact_report.affected_symbols = list(symbol_map.values())
                        
                        impact_report.affected_tests = list(set(impact_report.affected_tests + report.affected_tests))
                        
                        # 合并接口变更（基于符号名和文件路径去重）
                        interface_map = {}
                        for change in impact_report.interface_changes + report.interface_changes:
                            key = (change.file_path, change.symbol_name, change.change_type)
                            if key not in interface_map:
                                interface_map[key] = change
                        impact_report.interface_changes = list(interface_map.values())
                        
                        impact_report.impacts.extend(report.impacts)
                        
                        # 合并建议
                        impact_report.recommendations = list(set(impact_report.recommendations + report.recommendations))
                        
                        # 使用更高的风险等级
                        if report.risk_level.value == 'high' or impact_report.risk_level.value == 'high':
                            impact_report.risk_level = report.risk_level if report.risk_level.value == 'high' else impact_report.risk_level
                        elif report.risk_level.value == 'medium':
                            impact_report.risk_level = report.risk_level
            
            return impact_report
        except Exception as e:
            # 影响分析失败不应该影响主流程，仅记录日志
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"影响范围分析失败: {e}", exc_info=True)
            return None

    def _handle_impact_report(self, impact_report: Optional[Any], agent: Agent, final_ret: str) -> str:
        """处理影响范围分析报告
        
        Args:
            impact_report: 影响分析报告
            agent: Agent实例
            final_ret: 当前的结果字符串
            
        Returns:
            更新后的结果字符串
        """
        if not impact_report:
            return final_ret
        
        impact_summary = impact_report.to_string(self.root_dir)
        final_ret += f"\n\n{impact_summary}\n"
        
        # 如果是高风险，在提示词中提醒
        if impact_report.risk_level.value == 'high':
            agent.set_addon_prompt(
                f"{agent.get_addon_prompt() or ''}\n\n"
                f"⚠️ 高风险编辑警告：\n"
                f"检测到此编辑为高风险操作，请仔细检查以下内容：\n"
                f"- 受影响文件: {len(impact_report.affected_files)} 个\n"
                f"- 接口变更: {len(impact_report.interface_changes)} 个\n"
                f"- 相关测试: {len(impact_report.affected_tests)} 个\n"
                f"建议运行相关测试并检查所有受影响文件。"
            )
        
        return final_ret

    def _handle_build_validation_disabled(self, modified_files: List[str], config: Any, agent: Agent, final_ret: str) -> str:
        """处理构建验证已禁用的情况
        
        Returns:
            更新后的结果字符串
        """
        reason = config.get_disable_reason()
        reason_text = f"（原因: {reason}）" if reason else ""
        final_ret += f"\n\nℹ️ 构建验证已禁用{reason_text}，仅进行基础静态检查\n"
        
        # 输出基础静态检查日志
        file_count = len(modified_files)
        files_str = ", ".join(os.path.basename(f) for f in modified_files[:3])
        if file_count > 3:
            files_str += f" 等{file_count}个文件"
        PrettyOutput.print(f"🔍 正在进行基础静态检查 ({files_str})...", OutputType.INFO)
        
        # 使用兜底验证器进行基础静态检查
        fallback_validator = FallbackBuildValidator(self.root_dir, timeout=get_build_validation_timeout())
        static_check_result = fallback_validator.validate(modified_files)
        if not static_check_result.success:
            final_ret += f"\n⚠️ 基础静态检查失败:\n{static_check_result.error_message or static_check_result.output}\n"
            agent.set_addon_prompt(
                f"基础静态检查失败，请根据以下错误信息修复代码:\n{static_check_result.error_message or static_check_result.output}\n"
            )
        else:
            final_ret += f"\n✅ 基础静态检查通过（耗时 {static_check_result.duration:.2f}秒）\n"
        
        return final_ret

    def _handle_build_validation_failure(self, build_validation_result: Any, config: Any, modified_files: List[str], agent: Agent, final_ret: str) -> str:
        """处理构建验证失败的情况
        
        Returns:
            更新后的结果字符串
        """
        if not config.has_been_asked():
            # 首次失败，询问用户
            error_preview = _format_build_error(build_validation_result)
            PrettyOutput.print(
                f"\n⚠️ 构建验证失败:\n{error_preview}\n",
                OutputType.WARNING,
            )
            PrettyOutput.print(
                "提示：如果此项目需要在特殊环境（如容器）中构建，或使用独立构建脚本，"
                "可以选择禁用构建验证，后续将仅进行基础静态检查。",
                OutputType.INFO,
            )
            
            if user_confirm(
                "是否要禁用构建验证，后续仅进行基础静态检查？",
                default=False,
            ):
                # 用户选择禁用
                config.disable_build_validation(
                    reason="用户选择禁用（项目可能需要在特殊环境中构建）"
                )
                config.mark_as_asked()
                final_ret += "\n\nℹ️ 已禁用构建验证，后续将仅进行基础静态检查\n"
                
                # 输出基础静态检查日志
                file_count = len(modified_files)
                files_str = ", ".join(os.path.basename(f) for f in modified_files[:3])
                if file_count > 3:
                    files_str += f" 等{file_count}个文件"
                PrettyOutput.print(f"🔍 正在进行基础静态检查 ({files_str})...", OutputType.INFO)
                
                # 立即进行基础静态检查
                fallback_validator = FallbackBuildValidator(self.root_dir, timeout=get_build_validation_timeout())
                static_check_result = fallback_validator.validate(modified_files)
                if not static_check_result.success:
                    final_ret += f"\n⚠️ 基础静态检查失败:\n{static_check_result.error_message or static_check_result.output}\n"
                    agent.set_addon_prompt(
                        f"基础静态检查失败，请根据以下错误信息修复代码:\n{static_check_result.error_message or static_check_result.output}\n"
                    )
                else:
                    final_ret += f"\n✅ 基础静态检查通过（耗时 {static_check_result.duration:.2f}秒）\n"
            else:
                # 用户选择继续验证，标记为已询问
                config.mark_as_asked()
                final_ret += f"\n\n⚠️ 构建验证失败:\n{_format_build_error(build_validation_result)}\n"
                # 如果构建失败，添加修复提示
                agent.set_addon_prompt(
                    f"构建验证失败，请根据以下错误信息修复代码:\n{_format_build_error(build_validation_result)}\n"
                    "请仔细检查错误信息，修复编译/构建错误后重新提交。"
                )
        else:
            # 已经询问过，直接显示错误
            final_ret += f"\n\n⚠️ 构建验证失败:\n{_format_build_error(build_validation_result)}\n"
            # 如果构建失败，添加修复提示
            agent.set_addon_prompt(
                f"构建验证失败，请根据以下错误信息修复代码:\n{_format_build_error(build_validation_result)}\n"
                "请仔细检查错误信息，修复编译/构建错误后重新提交。"
            )
        
        return final_ret

    def _handle_build_validation(self, modified_files: List[str], agent: Agent, final_ret: str) -> Tuple[Optional[Any], str]:
        """处理构建验证
        
        Returns:
            (build_validation_result, updated_final_ret)
        """
        if not is_enable_build_validation():
            return None, final_ret
        
        config = BuildValidationConfig(self.root_dir)
        
        # 检查是否已禁用构建验证
        if config.is_build_validation_disabled():
            final_ret = self._handle_build_validation_disabled(modified_files, config, agent, final_ret)
            return None, final_ret
        
        # 未禁用，进行构建验证
        build_validation_result = self._validate_build_after_edit(modified_files)
        if build_validation_result:
            if not build_validation_result.success:
                final_ret = self._handle_build_validation_failure(
                    build_validation_result, config, modified_files, agent, final_ret
                )
            else:
                build_system_info = f" ({build_validation_result.build_system.value})" if build_validation_result.build_system else ""
                final_ret += f"\n\n✅ 构建验证通过{build_system_info}（耗时 {build_validation_result.duration:.2f}秒）\n"
        
        return build_validation_result, final_ret

    def _handle_static_analysis(self, modified_files: List[str], build_validation_result: Optional[Any], config: Any, agent: Agent, final_ret: str) -> str:
        """处理静态分析
        
        Returns:
            更新后的结果字符串
        """
        lint_tools_info = "\n".join(
            f"   - {file}: 使用 {'、'.join(get_lint_tools(file))}"
            for file in modified_files
            if get_lint_tools(file)
        )
        
        if not lint_tools_info or not is_enable_static_analysis():
            return final_ret
        
        # 如果构建验证失败且未禁用，不进行静态分析（避免重复错误）
        # 如果构建验证已禁用，则进行静态分析（因为只做了基础静态检查）
        should_skip_static = (
            build_validation_result 
            and not build_validation_result.success 
            and not config.is_build_validation_disabled()
        )
        
        if not should_skip_static:
            # 直接执行静态扫描
            lint_results = self._run_static_analysis(modified_files)
            if lint_results:
                # 有错误或警告，让大模型修复
                errors_summary = self._format_lint_results(lint_results)
                addon_prompt = f"""
静态扫描发现以下问题，请根据错误信息修复代码:

{errors_summary}

请仔细检查并修复所有问题。
                """
                agent.set_addon_prompt(addon_prompt)
                final_ret += "\n\n⚠️ 静态扫描发现问题，已提示修复\n"
            else:
                final_ret += "\n\n✅ 静态扫描通过\n"
        
        return final_ret

    def _on_after_tool_call(self, agent: Agent, current_response=None, need_return=None, tool_prompt=None, **kwargs) -> None:
        """工具调用后回调函数。"""
        final_ret = ""
        diff = get_diff()

        if diff:
            start_hash = get_latest_commit_hash()
            PrettyOutput.print(diff, OutputType.CODE, lang="diff")
            modified_files = get_diff_file_list()
            
            # 更新上下文管理器
            self._update_context_for_modified_files(modified_files)
            
            # 进行影响范围分析
            impact_report = self._analyze_edit_impact(modified_files)
            
            per_file_preview = self._build_per_file_patch_preview(modified_files)
            commited = handle_commit_workflow()
            if commited:
                # 统计代码行数变化
                # 获取diff的统计信息
                try:
                    diff_result = subprocess.run(
                        ["git", "diff", "HEAD~1", "HEAD", "--shortstat"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=True,
                    )
                    if diff_result.returncode == 0 and diff_result.stdout:
                        self._record_code_changes_stats(diff_result.stdout)
                except subprocess.CalledProcessError:
                    pass

                # 统计修改次数
                from jarvis.jarvis_stats.stats import StatsManager

                StatsManager.increment("code_modifications", group="code_agent")

                # 获取提交信息
                end_hash = get_latest_commit_hash()
                commits = get_commits_between(start_hash, end_hash)

                # 添加提交信息到final_ret（按文件展示diff；删除文件仅提示）
                if commits:
                    final_ret += (
                        f"\n\n代码已修改完成\n补丁内容（按文件）:\n{per_file_preview}\n"
                    )
                    
                    # 添加影响范围分析报告
                    final_ret = self._handle_impact_report(impact_report, agent, final_ret)
                    
                    # 构建验证
                    config = BuildValidationConfig(self.root_dir)
                    build_validation_result, final_ret = self._handle_build_validation(modified_files, agent, final_ret)
                    
                    # 静态分析
                    final_ret = self._handle_static_analysis(modified_files, build_validation_result, config, agent, final_ret)
                else:
                    final_ret += "\n\n修改没有生效\n"
            else:
                final_ret += "\n修改被拒绝\n"
                final_ret += f"# 补丁预览（按文件）:\n{per_file_preview}"
        else:
            return
        # 用户确认最终结果
        if commited:
            agent.session.prompt += final_ret
            return
        PrettyOutput.print(final_ret, OutputType.USER, lang="markdown")
        if not is_confirm_before_apply_patch() or user_confirm(
            "是否使用此回复？", default=True
        ):
            agent.session.prompt += final_ret
            return
        # 用户未确认，允许输入自定义回复作为附加提示
        custom_reply = get_multiline_input("请输入自定义回复")
        if custom_reply.strip():  # 如果自定义回复为空，不设置附加提示
            agent.set_addon_prompt(custom_reply)
        agent.session.prompt += final_ret
        return

    def _run_static_analysis(self, modified_files: List[str]) -> List[Tuple[str, str, str, int, str]]:
        """执行静态分析
        
        Args:
            modified_files: 修改的文件列表
        
        Returns:
            [(tool_name, file_path, command, returncode, output), ...] 格式的结果列表
            只返回有错误或警告的结果（returncode != 0）
        """
        if not modified_files:
            return []
        
        # 获取所有lint命令
        commands = get_lint_commands_for_files(modified_files, self.root_dir)
        if not commands:
            return []
        
        # 输出静态检查日志
        file_count = len(modified_files)
        files_str = ", ".join(os.path.basename(f) for f in modified_files[:3])
        if file_count > 3:
            files_str += f" 等{file_count}个文件"
        tool_names = list(set(cmd[0] for cmd in commands))
        tools_str = ", ".join(tool_names[:3])
        if len(tool_names) > 3:
            tools_str += f" 等{len(tool_names)}个工具"
        PrettyOutput.print(f"🔍 正在进行静态检查 ({files_str}, 使用 {tools_str})...", OutputType.INFO)
        
        results = []
        
        # 按工具分组，相同工具可以批量执行
        grouped = group_commands_by_tool(commands)
        
        for tool_name, file_commands in grouped.items():
            for file_path, command in file_commands:
                try:
                    # 检查文件是否存在
                    abs_file_path = os.path.join(self.root_dir, file_path) if not os.path.isabs(file_path) else file_path
                    if not os.path.exists(abs_file_path):
                        continue
                    
                    # 执行命令
                    result = subprocess.run(
                        command,
                        shell=True,
                        cwd=self.root_dir,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=30,  # 30秒超时
                    )
                    
                    # 只记录有错误或警告的结果
                    if result.returncode != 0:
                        output = result.stdout + result.stderr
                        if output.strip():  # 有输出才记录
                            results.append((tool_name, file_path, command, result.returncode, output))
                
                except subprocess.TimeoutExpired:
                    results.append((tool_name, file_path, command, -1, "执行超时（30秒）"))
                except FileNotFoundError:
                    # 工具未安装，跳过
                    continue
                except Exception as e:
                    # 其他错误，记录但继续
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"执行lint命令失败: {command}, 错误: {e}")
                    continue
        
        return results
    
    def _format_lint_results(self, results: List[Tuple[str, str, str, int, str]]) -> str:
        """格式化lint结果
        
        Args:
            results: [(tool_name, file_path, command, returncode, output), ...]
        
        Returns:
            格式化的错误信息字符串
        """
        if not results:
            return ""
        
        lines = []
        for tool_name, file_path, command, returncode, output in results:
            lines.append(f"工具: {tool_name}")
            lines.append(f"文件: {file_path}")
            lines.append(f"命令: {command}")
            if returncode == -1:
                lines.append(f"错误: {output}")
            else:
                # 限制输出长度，避免过长
                output_preview = output[:1000] if len(output) > 1000 else output
                lines.append(f"输出:\n{output_preview}")
                if len(output) > 1000:
                    lines.append(f"... (输出已截断，共 {len(output)} 字符)")
            lines.append("")  # 空行分隔
        
        return "\n".join(lines)
    
    def _extract_file_paths_from_input(self, user_input: str) -> List[str]:
        """从用户输入中提取文件路径
        
        Args:
            user_input: 用户输入文本
            
        Returns:
            文件路径列表
        """
        import re
        file_paths = []
        
        # 匹配常见的文件路径模式
        # 1. 引号中的路径: "path/to/file.py" 或 'path/to/file.py'
        quoted_paths = re.findall(r'["\']([^"\']+\.(?:py|js|ts|rs|go|java|cpp|c|h|hpp))["\']', user_input)
        file_paths.extend(quoted_paths)
        
        # 2. 相对路径: ./path/to/file.py 或 path/to/file.py
        relative_paths = re.findall(r'(?:\./)?[\w/]+\.(?:py|js|ts|rs|go|java|cpp|c|h|hpp)', user_input)
        file_paths.extend(relative_paths)
        
        # 3. 绝对路径（简化匹配）
        absolute_paths = re.findall(r'/(?:[\w\-\.]+/)+[\w\-\.]+\.(?:py|js|ts|rs|go|java|cpp|c|h|hpp)', user_input)
        file_paths.extend(absolute_paths)
        
        # 转换为绝对路径并去重
        unique_paths = []
        seen = set()
        for path in file_paths:
            abs_path = os.path.abspath(path) if not os.path.isabs(path) else path
            if abs_path not in seen and os.path.exists(abs_path):
                seen.add(abs_path)
                unique_paths.append(abs_path)
        
        return unique_paths

    def _extract_symbols_from_input(self, user_input: str) -> List[str]:
        """从用户输入中提取符号名称（函数名、类名等）
        
        Args:
            user_input: 用户输入文本
            
        Returns:
            符号名称列表
        """
        import re
        symbols = []
        
        # 匹配常见的符号命名模式
        # 1. 驼峰命名（类名）: MyClass, ProcessData
        camel_case = re.findall(r'\b[A-Z][a-zA-Z0-9]+\b', user_input)
        symbols.extend(camel_case)
        
        # 2. 下划线命名（函数名、变量名）: process_data, get_user_info
        snake_case = re.findall(r'\b[a-z][a-z0-9_]+[a-z0-9]\b', user_input)
        symbols.extend(snake_case)
        
        # 3. 在引号中的符号名: "function_name" 或 'ClassName'
        quoted_symbols = re.findall(r'["\']([A-Za-z][A-Za-z0-9_]*?)["\']', user_input)
        symbols.extend(quoted_symbols)
        
        # 过滤常见停用词和过短的符号
        stop_words = {
            'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'her', 'was', 'one',
            'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'its', 'may', 'new', 'now',
            'old', 'see', 'two', 'way', 'who', 'boy', 'did', 'its', 'let', 'put', 'say', 'she',
            'too', 'use', '添加', '修改', '实现', '修复', '更新', '删除', '创建', '文件', '代码',
        }
        
        unique_symbols = []
        seen = set()
        for symbol in symbols:
            symbol_lower = symbol.lower()
            if (symbol_lower not in stop_words and 
                len(symbol) > 2 and 
                symbol_lower not in seen):
                seen.add(symbol_lower)
                unique_symbols.append(symbol)
        
        return unique_symbols[:10]  # 限制数量

    def _validate_build_after_edit(self, modified_files: List[str]) -> Optional[BuildResult]:
        """编辑后验证构建
        
        Args:
            modified_files: 修改的文件列表
        
        Returns:
            BuildResult: 验证结果，如果验证被禁用或出错则返回None
        """
        if not is_enable_build_validation():
            return None
        
        # 检查项目配置，看是否已禁用构建验证
        config = BuildValidationConfig(self.root_dir)
        if config.is_build_validation_disabled():
            # 已禁用，返回None，由调用方处理基础静态检查
            return None
        
        # 输出编译检查日志
        file_count = len(modified_files)
        files_str = ", ".join(os.path.basename(f) for f in modified_files[:3])
        if file_count > 3:
            files_str += f" 等{file_count}个文件"
        PrettyOutput.print(f"🔨 正在进行编译检查 ({files_str})...", OutputType.INFO)
        
        try:
            timeout = get_build_validation_timeout()
            validator = BuildValidator(self.root_dir, timeout=timeout)
            result = validator.validate(modified_files)
            return result
        except Exception as e:
            # 构建验证失败不应该影响主流程，仅记录日志
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"构建验证执行失败: {e}", exc_info=True)
            return None


@app.command()
def cli(
    model_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="使用的模型组，覆盖配置文件中的设置"
    ),
    tool_group: Optional[str] = typer.Option(
        None, "-G", "--tool-group", help="使用的工具组，覆盖配置文件中的设置"
    ),
    config_file: Optional[str] = typer.Option(
        None, "-f", "--config", help="配置文件路径"
    ),
    requirement: Optional[str] = typer.Option(
        None, "-r", "--requirement", help="要处理的需求描述"
    ),
    append_tools: Optional[str] = typer.Option(
        None, "--append-tools", help="要追加的工具列表，用逗号分隔"
    ),
    restore_session: bool = typer.Option(
        False,
        "--restore-session",
        help="从 .jarvis/saved_session.json 恢复会话状态",
    ),
    prefix: str = typer.Option(
        "",
        "--prefix",
        help="提交信息前缀（用空格分隔）",
    ),
    suffix: str = typer.Option(
        "",
        "--suffix",
        help="提交信息后缀（用换行分隔）",
    ),
    non_interactive: bool = typer.Option(
        False, "-n", "--non-interactive", help="启用非交互模式：用户无法与命令交互，脚本执行超时限制为5分钟"
    ),
    plan: bool = typer.Option(False, "--plan/--no-plan", help="启用或禁用任务规划（子任务拆分与汇总执行）"),
) -> None:
    """Jarvis主入口点。"""
    # CLI 标志：非交互模式（不依赖配置文件）
    if non_interactive:
        try:
            os.environ["JARVIS_NON_INTERACTIVE"] = "true"
        except Exception:
            pass
        # 注意：全局配置同步放在 init_env 之后执行，避免被 init_env 覆盖
    # 非交互模式要求从命令行传入任务
    if non_interactive and not (requirement and str(requirement).strip()):
        PrettyOutput.print(
            "非交互模式已启用：必须使用 --requirement 传入任务内容，因多行输入不可用。",
            OutputType.ERROR,
        )
        raise typer.Exit(code=2)
    init_env(
        "欢迎使用 Jarvis-CodeAgent，您的代码工程助手已准备就绪！",
        config_file=config_file,
    )
    # CodeAgent 单实例互斥：改为按仓库维度加锁（延后至定位仓库根目录后执行）
    # 锁的获取移动到确认并切换到git根目录之后

    # 在初始化环境后同步 CLI 选项到全局配置，避免被 init_env 覆盖
    try:
        if model_group:
            set_config("JARVIS_LLM_GROUP", str(model_group))
        if tool_group:
            set_config("JARVIS_TOOL_GROUP", str(tool_group))
        if restore_session:
            set_config("JARVIS_RESTORE_SESSION", True)
        if non_interactive:
            set_config("JARVIS_NON_INTERACTIVE", True)
    except Exception:
        # 静默忽略同步异常，不影响主流程
        pass

    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        curr_dir_path = os.getcwd()
        PrettyOutput.print(
            f"警告：当前目录 '{curr_dir_path}' 不是一个git仓库。", OutputType.WARNING
        )
        init_git = True if non_interactive else user_confirm(
            f"是否要在 '{curr_dir_path}' 中初始化一个新的git仓库？", default=True
        )
        if init_git:
            try:
                subprocess.run(
                    ["git", "init"],
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                PrettyOutput.print("✅ 已成功初始化git仓库。", OutputType.SUCCESS)
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                PrettyOutput.print(f"❌ 初始化git仓库失败: {e}", OutputType.ERROR)
                sys.exit(1)
        else:
            PrettyOutput.print(
                "操作已取消。Jarvis需要在git仓库中运行。", OutputType.INFO
            )
            sys.exit(0)

    curr_dir = os.getcwd()
    find_git_root_and_cd(curr_dir)
    # 在定位到 git 根目录后，按仓库维度加锁，避免跨仓库互斥
    try:
        repo_root = os.getcwd()
        lock_name = f"code_agent_{hashlib.md5(repo_root.encode('utf-8')).hexdigest()}.lock"
        _acquire_single_instance_lock(lock_name=lock_name)
    except Exception:
        # 回退到全局锁，确保至少有互斥保护
        _acquire_single_instance_lock(lock_name="code_agent.lock")
    try:
        agent = CodeAgent(
            model_group=model_group,
            need_summary=False,
            append_tools=append_tools,
            tool_group=tool_group,
            non_interactive=non_interactive,
            plan=plan,
        )

        # 尝试恢复会话
        if restore_session:
            if agent.agent.restore_session():
                PrettyOutput.print(
                    "已从 .jarvis/saved_session.json 恢复会话。", OutputType.SUCCESS
                )
            else:
                PrettyOutput.print(
                    "无法从 .jarvis/saved_session.json 恢复会话。", OutputType.WARNING
                )

        if requirement:
            agent.run(requirement, prefix=prefix, suffix=suffix)
        else:
            while True:
                user_input = get_multiline_input("请输入你的需求（输入空行退出）:")
                if not user_input:
                    raise typer.Exit(code=0)
                agent.run(user_input, prefix=prefix, suffix=suffix)

    except typer.Exit:
        raise
    except RuntimeError as e:
        PrettyOutput.print(f"错误: {str(e)}", OutputType.ERROR)
        sys.exit(1)


def main() -> None:
    """Application entry point."""
    app()


if __name__ == "__main__":
    main()
