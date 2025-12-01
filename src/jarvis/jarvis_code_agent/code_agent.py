# -*- coding: utf-8 -*-
"""Jarvis代码代理模块。

该模块提供CodeAgent类，用于处理代码修改任务。
"""

import os
import subprocess
import sys
import hashlib
from typing import Any, Dict, List, Optional, Tuple

import typer
import yaml

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_agent.events import AFTER_TOOL_CALL
from jarvis.jarvis_code_agent.lint import (
    get_lint_tools,
    get_lint_commands_for_files,
    group_commands_by_tool,
    get_post_commands_for_files,
)
from jarvis.jarvis_code_agent.code_analyzer.build_validator import (
    BuildValidator,
    BuildResult,
    FallbackBuildValidator,
)
from jarvis.jarvis_code_agent.build_validation_config import BuildValidationConfig
from jarvis.jarvis_git_utils.git_commiter import GitCommitTool
from jarvis.jarvis_code_agent.code_analyzer import ContextManager
from jarvis.jarvis_code_agent.code_analyzer.llm_context_recommender import (
    ContextRecommender,
)
from jarvis.jarvis_code_agent.code_analyzer import (
    ImpactAnalyzer,
    parse_git_diff_to_edits,
)
from jarvis.jarvis_utils.config import (
    is_confirm_before_apply_patch,
    is_enable_static_analysis,
    is_enable_build_validation,
    get_build_validation_timeout,
    set_config,
    get_data_dir,
    is_enable_intent_recognition,
    is_enable_impact_analysis,
    get_smart_platform_name,
    get_smart_model_name,
)
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_code_agent.utils import get_project_overview
from jarvis.jarvis_utils.git_utils import (
    confirm_add_new_files,
    detect_large_code_deletion,
    find_git_root_and_cd,
    get_commits_between,
    get_diff,
    get_diff_file_list,
    get_latest_commit_hash,
    handle_commit_workflow,
    has_uncommitted_changes,
    revert_change,
)
from jarvis.jarvis_utils.input import get_multiline_input, user_confirm
from jarvis.jarvis_utils.output import OutputType, PrettyOutput  # 保留用于语法高亮
from jarvis.jarvis_utils.utils import init_env, _acquire_single_instance_lock

app = typer.Typer(help="Jarvis 代码助手")


def _format_build_error(result: BuildResult, max_len: int = 2000) -> str:
    """格式化构建错误信息，限制输出长度"""
    error_msg = result.error_message or ""
    output = result.output or ""

    full_error = f"{error_msg}\n{output}".strip()

    if len(full_error) > max_len:
        return full_error[:max_len] + "\n... (输出已截断)"
    return full_error


class CodeAgent(Agent):
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
        rule_names: Optional[str] = None,
        **kwargs,
    ):
        self.root_dir = os.getcwd()
        self.tool_group = tool_group
        # 记录当前是否为非交互模式，便于在提示词/输入中动态调整行为说明
        self.non_interactive: bool = bool(non_interactive)

        # 初始化上下文管理器
        self.context_manager = ContextManager(self.root_dir)
        # 上下文推荐器将在Agent创建后初始化（需要LLM模型）
        self.context_recommender: Optional[ContextRecommender] = None

        # 检测 git username 和 email 是否已设置
        self._check_git_config()
        base_tools = [
            "execute_script",
            "read_code",
            "edit_file",
            "rewrite_file",
            "lsp_client",  # LSP客户端工具，用于获取代码补全、悬停等信息
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
        loaded_rule_names: List[str] = []  # 记录加载的规则名称

        if global_rules:
            combined_parts.append(global_rules)
            loaded_rule_names.append("global_rule")
        if project_rules:
            combined_parts.append(project_rules)
            loaded_rule_names.append("project_rule")

        # 如果指定了 rule_names，从 rules.yaml 文件中读取并添加多个规则
        if rule_names:
            rule_list = [name.strip() for name in rule_names.split(",") if name.strip()]
            for rule_name in rule_list:
                named_rule = self._get_named_rule(rule_name)
                if named_rule:
                    combined_parts.append(named_rule)
                    loaded_rule_names.append(rule_name)

        if combined_parts:
            merged_rules = "\n\n".join(combined_parts)
            code_system_prompt = (
                f"{code_system_prompt}\n\n<rules>\n{merged_rules}\n</rules>"
            )
            # 显示加载的规则名称
            if loaded_rule_names:
                rules_display = ", ".join(loaded_rule_names)
                print(f"ℹ️ 已加载规则: {rules_display}")

        # 调用父类 Agent 的初始化
        # 默认禁用方法论和分析，但允许通过 kwargs 覆盖
        use_methodology = kwargs.pop("use_methodology", False)
        use_analysis = kwargs.pop("use_analysis", False)
        # name 使用传入的值，如果没有传入则使用默认值 "CodeAgent"
        name = kwargs.pop("name", "CodeAgent")

        # 准备显式传递给 super().__init__ 的参数
        # 注意：这些参数如果也在 kwargs 中，需要先移除，避免重复传递错误
        explicit_params = {
            "system_prompt": code_system_prompt,
            "name": name,
            "auto_complete": False,
            "model_group": model_group,
            "need_summary": need_summary,
            "use_methodology": use_methodology,
            "use_analysis": use_analysis,
            "non_interactive": non_interactive,
            "use_tools": base_tools,
        }

        # 自动移除所有显式传递的参数，避免重复传递错误
        # 这样以后添加新参数时，只要在 explicit_params 中声明，就会自动处理
        for key in explicit_params:
            kwargs.pop(key, None)

        super().__init__(
            **explicit_params,
            **kwargs,
        )

        self._agent_type = "code_agent"

        # 建立CodeAgent与Agent的关联，便于工具获取上下文管理器
        self._code_agent = self

        # 初始化上下文推荐器（自己创建LLM模型，使用父Agent的配置）
        try:
            # 获取当前Agent的model实例
            parent_model = None
            if self.model:
                parent_model = self.model

            self.context_recommender = ContextRecommender(
                self.context_manager, parent_model=parent_model
            )
        except Exception as e:
            # LLM推荐器初始化失败
            print(f"⚠️ 上下文推荐器初始化失败: {e}，将跳过上下文推荐功能")

        self.event_bus.subscribe(AFTER_TOOL_CALL, self._on_after_tool_call)

        # 打印语言功能支持表格
        try:
            from jarvis.jarvis_agent.language_support_info import (
                print_language_support_table,
            )

            print_language_support_table()
        except Exception:
            pass

    def _init_model(self, model_group: Optional[str]):
        """初始化模型平台（CodeAgent使用smart平台，适用于代码生成等复杂场景）"""
        platform_name = get_smart_platform_name(model_group)
        model_name = get_smart_model_name(model_group)

        maybe_model = PlatformRegistry().create_platform(platform_name)
        if maybe_model is None:
            print(f"⚠️ 平台 {platform_name} 不存在，将使用smart模型")
            maybe_model = PlatformRegistry().get_smart_platform()

        # 在此处收敛为非可选类型，确保后续赋值满足类型检查
        self.model = maybe_model

        if model_name:
            self.model.set_model_name(model_name)

        self.model.set_model_group(model_group)
        self.model.set_suppress_output(False)

    def _get_system_prompt(self) -> str:
        """获取代码工程师的系统提示词"""
        return """
你是Jarvis代码工程师，专注于**项目级代码分析、精准修改与问题排查**，核心原则：自主决策不犹豫、高效精准不冗余、修改审慎可回退、工具精通不臆测。

## RIPER-5 协议集成

### 元指令：模式声明要求

你必须在每个响应的开头用方括号声明你当前的模式。没有例外。
格式：[MODE: MODE_NAME]

未能声明你的模式是对协议的严重违反。

初始默认模式：除非另有指示，你应该在每次新对话开始时处于RESEARCH模式。

### 核心思维原则

在所有模式中，这些基本思维原则指导你的操作：

- 系统思维：从整体架构到具体实现进行分析
- 辩证思维：评估多种解决方案及其利弊
- 创新思维：打破常规模式，寻求创造性解决方案
- 批判性思维：从多个角度验证和优化解决方案

在所有回应中平衡这些方面：
- 分析与直觉
- 细节检查与全局视角
- 理论理解与实际应用
- 深度思考与前进动力
- 复杂性与清晰度

### RIPER-5 模式定义

#### 模式1：研究 [MODE: RESEARCH]

目的：信息收集和深入理解

核心思维应用：
- 系统地分解技术组件
- 清晰地映射已知/未知元素
- 考虑更广泛的架构影响
- 识别关键技术约束和要求

允许：
- 阅读文件
- 提出澄清问题
- 理解代码结构
- 分析系统架构
- 识别技术债务或约束

禁止：
- 建议
- 实施
- 规划
- 任何行动或解决方案的暗示

输出格式：以[MODE: RESEARCH]开始，然后只有观察和问题。使用markdown语法格式化答案。

持续时间：直到明确信号转移到下一个模式

#### 模式2：创新 [MODE: INNOVATE]

目的：头脑风暴潜在方法

核心思维应用：
- 运用辩证思维探索多种解决路径
- 应用创新思维打破常规模式
- 平衡理论优雅与实际实现
- 考虑技术可行性、可维护性和可扩展性

允许：
- 讨论多种解决方案想法
- 评估优势/劣势
- 寻求方法反馈
- 探索架构替代方案

禁止：
- 具体规划
- 实施细节
- 任何代码编写
- 承诺特定解决方案

输出格式：以[MODE: INNOVATE]开始，然后只有可能性和考虑因素。以自然流畅的段落呈现想法。

持续时间：直到明确信号转移到下一个模式

#### 模式3：规划 [MODE: PLAN]

目的：创建详尽的技术规范

核心思维应用：
- 应用系统思维确保全面的解决方案架构
- 使用批判性思维评估和优化计划
- 制定全面的技术规范
- 确保目标聚焦，将所有规划与原始需求相连接

允许：
- 带有精确文件路径的详细计划
- 精确的函数名称和签名
- 具体的更改规范
- 完整的架构概述

禁止：
- 任何实施或代码编写
- 甚至可能被实施的"示例代码"
- 跳过或缩略规范

输出格式：以[MODE: PLAN]开始，然后提供详细的技术规范。

持续时间：直到明确信号转移到下一个模式

#### 模式4：执行 [MODE: EXECUTE]

目的：实施代码更改

核心思维应用：
- 严格按照计划执行
- 应用系统思维确保修改的完整性
- 使用批判性思维验证每个步骤

允许：
- 读取文件
- 编辑文件
- 执行工具调用
- 验证修改结果

禁止：
- 偏离已批准的计划
- 未经授权的修改
- 跳过验证步骤

输出格式：以[MODE: EXECUTE]开始，然后执行具体的代码修改。

持续时间：直到完成所有计划步骤或明确信号转移到下一个模式

#### 模式5：审查 [MODE: REVIEW]

目的：验证和优化已实施的更改

核心思维应用：
- 使用批判性思维验证修改的正确性
- 应用系统思维评估整体影响
- 识别潜在问题和改进机会

允许：
- 审查代码更改
- 验证功能正确性
- 检查代码质量
- 提出优化建议

禁止：
- 未经授权的额外修改
- 跳过验证步骤

输出格式：以[MODE: REVIEW]开始，然后提供审查结果和建议。

持续时间：直到审查完成

### 模式转换信号

只有在明确信号时才能转换模式：
- "ENTER RESEARCH MODE" 或 "进入研究模式"
- "ENTER INNOVATE MODE" 或 "进入创新模式"
- "ENTER PLAN MODE" 或 "进入规划模式"
- "ENTER EXECUTE MODE" 或 "进入执行模式"
- "ENTER REVIEW MODE" 或 "进入审查模式"

没有这些确切信号，请保持在当前模式。

        默认模式规则：
        - 除非明确指示，否则默认在每次对话开始时处于RESEARCH模式
        - 如果EXECUTE模式发现需要偏离计划，自动回到PLAN模式
        - 完成所有实施，且用户确认成功后，可以从EXECUTE模式转到REVIEW模式
        - 对于非交互模式（例如通过命令行参数 --non-interactive 或环境变量 JARVIS_NON_INTERACTIVE 启用），在PLAN模式已经给出清晰、可执行的详细计划后，可以直接进入EXECUTE模式执行计划，无需再次等待用户确认

## 工作流程（闭环执行，每步必落地）

1. 需求拆解与项目对齐：
   - 先明确用户需求的核心目标（如"修复XX报错""新增XX功能""优化XX性能"），标注关键约束（如"兼容Python 3.8+""不修改核心依赖"）；
   - 快速定位项目核心目录（如src/、main/）、技术栈（语言/框架/版本）、代码风格规范（如PEP8、ESLint规则），避免无的放矢。

2. 目标文件精准定位（工具优先，拒绝盲搜）：
   - 优先通过 lsp_client 的 search_symbol（符号搜索）定位关联文件（如函数、类、变量所属文件）；
   - 若符号不明确，用全文搜索工具按"关键词+文件类型过滤"（如"关键词：user_login + 后缀：.py"）缩小范围；
   - 仅当工具无法定位时，才用 read_code 读取疑似目录下的核心文件（如入口文件、配置文件），避免无效读取。

3. 代码深度分析（基于工具，禁止虚构）：
   - 符号分析：用 lsp_client 的 document_symbols（文档符号）、get_symbol_info（符号详情）、definition（定义跳转）、references（引用查询），确认符号的作用域、依赖关系、调用链路；
   - 内容分析：用 read_code 读取目标文件完整内容，重点关注"逻辑分支、异常处理、依赖引入、配置参数"，记录关键代码片段（如报错位置、待修改逻辑）；
   - 影响范围评估：用 lsp_client 的 references 查询待修改符号的所有引用场景，预判修改可能波及的模块，避免"改一处崩一片"。

4. 最小变更方案设计（可回退、易维护）：
   - 优先选择"局部修改"（如修改函数内逻辑、补充条件判断），而非"重构"或"全文件重写"；
   - 方案需满足：① 覆盖需求核心；② 不破坏现有功能；③ 符合项目代码风格；④ 便于后续回退（如仅修改必要行，不删无关代码）；
   - 若需修改核心逻辑（如公共函数、配置文件），先记录原始代码片段（如用临时文件保存到 /tmp/backup_xxx.txt），再执行修改。

5. 先读后写，精准执行（工具规范使用）：
   - 必须先通过 read_code 读取目标文件完整内容，确认待修改位置的上下文（如前后代码逻辑、缩进格式），再调用编辑工具；
   - 编辑工具选择：
     - 局部修改（改少数行、补代码块）：用 edit_file，明确标注"修改范围（行号/代码片段）+ 修改内容"（如"替换第15-20行的循环逻辑为：xxx"）；
     - 全文件重写（如格式统一、逻辑重构）：仅当局部修改无法满足需求时使用 rewrite_file，重写前必须备份原始文件到 /tmp/rewrite_backup_xxx.txt。

6. 验证与兜底（避免无效交付）：
   - 修改后优先通过 lsp_client 的语法检查功能（若支持）验证代码无语法错误；
   - 若涉及功能变更，建议补充1-2行核心测试用例（或提示用户验证场景），确保修改生效；
   - 记录修改日志（保存到 /tmp/modify_log_xxx.txt），内容包括：修改时间、目标文件、修改原因、原始代码片段、修改后代码片段，便于问题追溯。

## 工具使用规范（精准调用，不浪费资源）

- lsp_client：仅传递有效参数（如符号名精准、文件路径明确），避免模糊查询（如无关键词的全局搜索）；
- 全文搜索：必须添加"文件类型过滤""目录过滤"，减少无效结果（如仅搜索 src/ 目录下的 .java 文件）；
- read_code：仅读取目标文件和关联依赖文件，不读取日志、测试数据、第三方依赖包等无关文件；
- edit_file/rewrite_file：修改后必须保持代码缩进、命名规范与原文件一致（如原文件用4空格缩进，不改为2空格），不引入多余空行、注释。

## 代码质量约束（底线要求，不可突破）

1. 语法正确性：修改后代码无语法错误、无未定义变量/函数、无依赖缺失；
2. 功能兼容性：不破坏现有正常功能，修改后的代码能适配项目已有的调用场景；
3. 风格一致性：严格遵循项目既有风格（如命名规范、缩进、注释格式），不引入个人风格；
4. 可维护性：修改逻辑清晰，关键改动可加简洁注释（如"// 修复XX报错：XX场景下变量未初始化"），不写"魔法值""冗余代码"。

## 调试指引（问题闭环，高效排查）

- 定位报错：优先用 lsp_client 定位报错位置，结合 read_code 查看上下文，确认报错类型（语法错/逻辑错/运行时错）；
- 日志补充：若报错模糊，在关键位置（如函数入口、循环内、异常捕获前）增加打印日志，内容包括"变量值、执行步骤、时间戳"（如 print(f"[DEBUG] user_login: username={username}, status={status}")），日志输出到 /tmp/ 目录，不污染项目日志；
- 中间结果保存：复杂逻辑修改时，用临时文件（/tmp/temp_result_xxx.txt）保存中间数据（如计算结果、接口返回值），便于验证逻辑正确性；
- 回退机制：若修改后出现新问题，立即用备份文件回退，重新分析，不盲目叠加修改。

## 禁止行为（红线不可碰）

1. 禁止虚构代码、依赖、文件路径，所有结论必须基于工具返回结果或实际读取的代码；
2. 禁止无差别读取项目所有文件，避免浪费资源；
3. 禁止大篇幅删除、重构未明确要求修改的代码；
4. 禁止引入项目未依赖的第三方库（除非用户明确允许）；
5. 禁止修改 /tmp/ 以外的非项目目录文件，避免污染环境。

## 重要提醒

- 每个响应必须以模式声明开始：[MODE: MODE_NAME]
- 默认模式是 RESEARCH，除非用户明确指示
- 只有在收到明确的模式转换信号时才能切换模式
- 严格遵守当前模式的允许和禁止行为

"""

    def _read_project_rules(self) -> Optional[str]:
        """读取 .jarvis/rules 内容，如果存在则返回字符串，否则返回 None"""
        try:
            rules_path = os.path.join(self.root_dir, ".jarvis", "rule")
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
            rules_path = os.path.join(get_data_dir(), "rule")
            if os.path.exists(rules_path) and os.path.isfile(rules_path):
                with open(rules_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read().strip()
                return content if content else None
        except Exception:
            # 读取规则失败时忽略，不影响主流程
            pass
        return None

    def _get_named_rule(self, rule_name: str) -> Optional[str]:
        """从 rules.yaml 文件中获取指定名称的规则

        参数:
            rule_name: 规则名称

        返回:
            str: 规则内容，如果未找到则返回 None
        """
        try:
            # 读取全局数据目录下的 rules.yaml
            global_rules_yaml_path = os.path.join(get_data_dir(), "rules.yaml")
            global_rules = {}
            if os.path.exists(global_rules_yaml_path) and os.path.isfile(
                global_rules_yaml_path
            ):
                with open(
                    global_rules_yaml_path, "r", encoding="utf-8", errors="replace"
                ) as f:
                    global_rules = yaml.safe_load(f) or {}

            # 读取 git 根目录下的 rules.yaml
            project_rules_yaml_path = os.path.join(self.root_dir, "rules.yaml")
            project_rules = {}
            if os.path.exists(project_rules_yaml_path) and os.path.isfile(
                project_rules_yaml_path
            ):
                with open(
                    project_rules_yaml_path, "r", encoding="utf-8", errors="replace"
                ) as f:
                    project_rules = yaml.safe_load(f) or {}

            # 合并配置：项目配置覆盖全局配置
            merged_rules = {**global_rules, **project_rules}

            # 查找指定的规则
            if rule_name in merged_rules:
                rule_value = merged_rules[rule_name]
                # 如果值是字符串，直接返回
                if isinstance(rule_value, str):
                    return rule_value.strip() if rule_value.strip() else None
                # 如果值是其他类型，转换为字符串
                return str(rule_value).strip() if str(rule_value).strip() else None

            return None
        except Exception as e:
            # 读取规则失败时忽略，不影响主流程
            print(f"⚠️ 读取 rules.yaml 失败: {e}")
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
                print(f"❌ {message}")
                sys.exit(1)

        except FileNotFoundError:
            print("❌ 未找到 git 命令，请先安装 Git")
            sys.exit(1)
        except Exception as e:
            print(f"❌ 检查 Git 配置时出错: {str(e)}")
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
            print("✅ 已创建 .gitignore 并添加常用忽略规则")
        else:
            if new_lines:
                # 追加缺失的规则
                with open(gitignore_path, "a", encoding="utf-8", newline="\n") as f:
                    # 若原文件不以换行结尾，先补一行
                    if existing_content and not existing_content.endswith("\n"):
                        f.write("\n")
                    f.write("\n".join(new_lines).rstrip() + "\n")
                print("✅ 已更新 .gitignore，追加常用忽略规则")

    def _handle_git_changes(self, prefix: str, suffix: str) -> None:
        """处理git仓库中的未提交修改"""

        if has_uncommitted_changes():
            git_commiter = GitCommitTool()
            git_commiter.execute(
                {
                    "prefix": prefix,
                    "suffix": suffix,
                    "agent": self,
                    "model_group": getattr(self.model, "model_group", None),
                }
            )

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

        print("⚠️ 正在修改git换行符敏感设置，这会影响所有文件的换行符处理方式")
        # 避免在循环中逐条打印，先拼接后统一打印
        lines = ["将进行以下设置："]
        for key, value in target_settings.items():
            current = current_settings.get(key, "未设置")
            lines.append(f"{key}: {current} -> {value}")
        joined_lines = "\n".join(lines)
        print(f"ℹ️ {joined_lines}")

        # 直接执行设置，不需要用户确认
        for key, value in target_settings.items():
            subprocess.run(["git", "config", key, value], check=True)

        # 对于Windows系统，提示用户可以创建.gitattributes文件
        if sys.platform.startswith("win"):
            self._handle_windows_line_endings()

        print("✅ git换行符敏感设置已更新")

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

        print("ℹ️ 提示：在Windows系统上，建议配置 .gitattributes 文件来避免换行符问题。")
        print("ℹ️ 这可以防止仅因换行符不同而导致整个文件被标记为修改。")

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
                print("✅ 已创建最小化的 .gitattributes 文件")
            else:
                print("ℹ️ 将以下内容追加到现有 .gitattributes 文件：")
                PrettyOutput.print(
                    minimal_content, OutputType.CODE, lang="text"
                )  # 保留语法高亮
                if user_confirm("是否追加到现有文件？", True):
                    with open(
                        gitattributes_path, "a", encoding="utf-8", newline="\n"
                    ) as f:
                        f.write("\n" + minimal_content)
                    print("✅ 已更新 .gitattributes 文件")
        else:
            print("ℹ️ 跳过 .gitattributes 文件创建。如遇换行符问题，可手动创建此文件。")

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

            print("⚠️ 检测到未提交的修改，是否要提交？")
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
                print(f"❌ 提交失败: {str(e)}")

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
            print(f"ℹ️ {commit_messages}")
        return commits

    def _post_process_modified_files(self, modified_files: List[str]) -> None:
        """文件后处理（包括格式化、自动修复等）

        Args:
            modified_files: 修改的文件列表
        """
        # 获取格式化命令
        format_commands = get_post_commands_for_files(modified_files, self.root_dir)
        if not format_commands:
            return

        print("🔧 正在格式化代码...")

        # 执行格式化命令
        formatted_files = set()
        for tool_name, file_path, command in format_commands:
            try:
                # 检查文件是否存在
                abs_file_path = (
                    os.path.join(self.root_dir, file_path)
                    if not os.path.isabs(file_path)
                    else file_path
                )
                if not os.path.exists(abs_file_path):
                    continue

                # 执行格式化命令
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=self.root_dir,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=300,  # 300秒超时
                )

                if result.returncode == 0:
                    formatted_files.add(file_path)
                    print(f"✅ 已格式化: {os.path.basename(file_path)} ({tool_name})")
                else:
                    # 格式化失败，记录但不中断流程
                    error_msg = (result.stderr or result.stdout or "").strip()
                    if error_msg:
                        print(
                            f"⚠️ 格式化失败 ({os.path.basename(file_path)}, {tool_name}): {error_msg[:200]}"
                        )
            except subprocess.TimeoutExpired:
                print(f"⚠️ 格式化超时: {os.path.basename(file_path)} ({tool_name})")
            except FileNotFoundError:
                # 工具未安装，跳过
                continue
            except Exception as e:
                # 其他错误，记录但继续
                print(
                    f"⚠️ 格式化失败 ({os.path.basename(file_path)}, {tool_name}): {str(e)[:100]}"
                )
                continue

        if formatted_files:
            print(f"✅ 已格式化 {len(formatted_files)} 个文件")
            # 暂存格式化后的文件
            try:
                for file_path in formatted_files:
                    abs_file_path = (
                        os.path.join(self.root_dir, file_path)
                        if not os.path.isabs(file_path)
                        else file_path
                    )
                    if os.path.exists(abs_file_path):
                        subprocess.run(
                            ["git", "add", file_path],
                            cwd=self.root_dir,
                            check=False,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
            except Exception:
                pass

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

            # 检测变更文件并格式化
            modified_files = get_diff_file_list()
            if modified_files:
                self._post_process_modified_files(modified_files)

            git_commiter = GitCommitTool()
            git_commiter.execute(
                {
                    "prefix": prefix,
                    "suffix": suffix,
                    "agent": self,
                    "model_group": getattr(self.model, "model_group", None),
                }
            )

            # 在用户接受commit后，根据配置决定是否保存记忆
            if self.force_save_memory:
                self.memory_manager.prompt_memory_save()
        elif start_commit:
            if user_confirm("是否要重置到初始提交？", True):
                os.system(f"git reset --hard {str(start_commit)}")  # 确保转换为字符串
                print("ℹ️ 已重置到初始提交")

    def run(self, user_input: str, prefix: str = "", suffix: str = "") -> Optional[str]:
        """使用给定的用户输入运行代码代理.

        参数:
            user_input: 用户的需求/请求

        返回:
            str: 描述执行结果的输出，成功时返回None
        """
        prev_dir = os.getcwd()
        try:
            # 根据当前模式生成额外说明，供 LLM 感知执行策略
            non_interactive_note = ""
            if getattr(self, "non_interactive", False):
                non_interactive_note = (
                    "\n\n[系统说明]\n"
                    "本次会话处于**非交互模式**：\n"
                    "- 在 PLAN 模式中给出清晰、可执行的详细计划后，应**自动进入 EXECUTE 模式执行计划**，不要等待用户额外确认；\n"
                    "- 在 EXECUTE 模式中，保持一步一步的小步提交和可回退策略，但不需要向用户反复询问“是否继续”；\n"
                    "- 如遇信息严重不足，可以在 RESEARCH 模式中自行补充必要分析，而不是卡在等待用户输入。\n"
                )

            self._init_env(prefix, suffix)
            start_commit = get_latest_commit_hash()

            # 获取项目概况信息
            project_overview = get_project_overview(self.root_dir)

            first_tip = """请严格遵循以下规范进行代码修改任务：
            1. 每次响应仅执行一步操作，先分析再修改，避免一步多改。
            2. 充分利用工具理解用户需求和现有代码，禁止凭空假设。
            3. 如果不清楚要修改的文件，必须先分析并找出需要修改的文件，明确目标后再进行编辑。
            4. 对于简单的文本替换（如修改单个字符串、常量值、配置项等），优先使用 execute_script 工具执行 sed 命令完成，简单高效。
            5. 代码编辑任务优先使用 PATCH 操作，确保搜索文本在目标文件中有且仅有一次精确匹配，保证修改的准确性和安全性。
            6. 如需大范围重写，才可使用 REWRITE 操作。
            7. 如遇信息不明，优先调用工具补充分析，不要主观臆断。
            """

            # 智能上下文推荐：根据用户输入推荐相关上下文
            context_recommendation_text = ""
            if self.context_recommender and is_enable_intent_recognition():
                # 在意图识别和上下文推荐期间抑制模型输出
                was_suppressed = False
                if self.model:
                    was_suppressed = getattr(self.model, "_suppress_output", False)
                    self.model.set_suppress_output(True)
                try:
                    print("🔍 正在进行智能上下文推荐....")

                    # 生成上下文推荐（基于关键词和项目上下文）
                    recommendation = self.context_recommender.recommend_context(
                        user_input=user_input,
                    )

                    # 格式化推荐结果
                    context_recommendation_text = (
                        self.context_recommender.format_recommendation(recommendation)
                    )

                    # 打印推荐的上下文
                    if context_recommendation_text:
                        print(f"ℹ️ {context_recommendation_text}")
                except Exception as e:
                    # 上下文推荐失败不应该影响主流程
                    print(f"⚠️ 上下文推荐失败: {e}")
                finally:
                    # 恢复模型输出设置
                    if self.model:
                        self.model.set_suppress_output(was_suppressed)

            if project_overview:
                enhanced_input = (
                    project_overview
                    + "\n\n"
                    + first_tip
                    + non_interactive_note
                    + context_recommendation_text
                    + "\n\n任务描述：\n"
                    + user_input
                )
            else:
                enhanced_input = (
                    first_tip
                    + non_interactive_note
                    + context_recommendation_text
                    + "\n\n任务描述：\n"
                    + user_input
                )

            try:
                if self.model:
                    self.model.set_suppress_output(False)
                super().run(enhanced_input)
            except RuntimeError as e:
                print(f"⚠️ 执行失败: {str(e)}")
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
            subprocess.run(
                ["git", "add", "-N", "."],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
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
            subprocess.run(
                ["git", "reset"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

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
            subprocess.run(
                ["git", "add", "-N", "--", file_path],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            cmd = (
                ["git", "diff"] + (["HEAD"] if head_exists else []) + ["--", file_path]
            )
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
            subprocess.run(
                ["git", "reset", "--", file_path],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def _build_per_file_patch_preview(self, modified_files: List[str]) -> str:
        """构建按文件的补丁预览"""
        status_map = self._build_name_status_map()
        lines: List[str] = []

        def _get_file_numstat(file_path: str) -> Tuple[int, int]:
            """获取单文件的新增/删除行数，失败时返回(0,0)"""
            head_exists = bool(get_latest_commit_hash())
            try:
                # 让未跟踪文件也能统计到新增行数
                subprocess.run(
                    ["git", "add", "-N", "--", file_path],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                cmd = (
                    ["git", "diff", "--numstat"]
                    + (["HEAD"] if head_exists else [])
                    + ["--", file_path]
                )
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
                subprocess.run(
                    ["git", "reset", "--", file_path],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
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
        print("🔄 正在更新代码上下文...")
        for file_path in modified_files:
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
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

        print("🔍 正在进行变更影响分析...")
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
                        impact_report.affected_files = list(
                            set(impact_report.affected_files + report.affected_files)
                        )

                        # 合并符号（基于文件路径和名称去重）
                        symbol_map = {}
                        for symbol in (
                            impact_report.affected_symbols + report.affected_symbols
                        ):
                            key = (symbol.file_path, symbol.name, symbol.line_start)
                            if key not in symbol_map:
                                symbol_map[key] = symbol
                        impact_report.affected_symbols = list(symbol_map.values())

                        impact_report.affected_tests = list(
                            set(impact_report.affected_tests + report.affected_tests)
                        )

                        # 合并接口变更（基于符号名和文件路径去重）
                        interface_map = {}
                        for change in (
                            impact_report.interface_changes + report.interface_changes
                        ):
                            key = (
                                change.file_path,
                                change.symbol_name,
                                change.change_type,
                            )
                            if key not in interface_map:
                                interface_map[key] = change
                        impact_report.interface_changes = list(interface_map.values())

                        impact_report.impacts.extend(report.impacts)

                        # 合并建议
                        impact_report.recommendations = list(
                            set(impact_report.recommendations + report.recommendations)
                        )

                        # 使用更高的风险等级
                        if (
                            report.risk_level.value == "high"
                            or impact_report.risk_level.value == "high"
                        ):
                            impact_report.risk_level = (
                                report.risk_level
                                if report.risk_level.value == "high"
                                else impact_report.risk_level
                            )
                        elif report.risk_level.value == "medium":
                            impact_report.risk_level = report.risk_level

            return impact_report
        except Exception as e:
            # 影响分析失败不应该影响主流程，仅记录日志
            print(f"⚠️ 影响范围分析失败: {e}")
            return None

    def _handle_impact_report(
        self, impact_report: Optional[Any], agent: Agent, final_ret: str
    ) -> str:
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
        if impact_report.risk_level.value == "high":
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

    def _handle_build_validation_disabled(
        self, modified_files: List[str], config: Any, agent: Agent, final_ret: str
    ) -> str:
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

        # 使用兜底验证器进行基础静态检查
        fallback_validator = FallbackBuildValidator(
            self.root_dir, timeout=get_build_validation_timeout()
        )
        static_check_result = fallback_validator.validate(modified_files)
        if not static_check_result.success:
            final_ret += f"\n⚠️ 基础静态检查失败:\n{static_check_result.error_message or static_check_result.output}\n"
            agent.set_addon_prompt(
                f"基础静态检查失败，请根据以下错误信息修复代码:\n{static_check_result.error_message or static_check_result.output}\n"
            )
        else:
            final_ret += (
                f"\n✅ 基础静态检查通过（耗时 {static_check_result.duration:.2f}秒）\n"
            )

        return final_ret

    def _handle_build_validation_failure(
        self,
        build_validation_result: Any,
        config: Any,
        modified_files: List[str],
        agent: Agent,
        final_ret: str,
    ) -> str:
        """处理构建验证失败的情况

        Returns:
            更新后的结果字符串
        """
        if not config.has_been_asked():
            # 首次失败，询问用户
            error_preview = _format_build_error(build_validation_result)
            print(f"\n⚠️ 构建验证失败:\n{error_preview}\n")
            print(
                "ℹ️ 提示：如果此项目需要在特殊环境（如容器）中构建，或使用独立构建脚本，"
                "可以选择禁用构建验证，后续将仅进行基础静态检查。"
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

                # 立即进行基础静态检查
                fallback_validator = FallbackBuildValidator(
                    self.root_dir, timeout=get_build_validation_timeout()
                )
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
            final_ret += (
                f"\n\n⚠️ 构建验证失败:\n{_format_build_error(build_validation_result)}\n"
            )
            # 如果构建失败，添加修复提示
            agent.set_addon_prompt(
                f"构建验证失败，请根据以下错误信息修复代码:\n{_format_build_error(build_validation_result)}\n"
                "请仔细检查错误信息，修复编译/构建错误后重新提交。"
            )

        return final_ret

    def _handle_build_validation(
        self, modified_files: List[str], agent: Agent, final_ret: str
    ) -> Tuple[Optional[Any], str]:
        """处理构建验证

        Returns:
            (build_validation_result, updated_final_ret)
        """
        if not is_enable_build_validation():
            return None, final_ret

        config = BuildValidationConfig(self.root_dir)

        # 检查是否已禁用构建验证
        if config.is_build_validation_disabled():
            final_ret = self._handle_build_validation_disabled(
                modified_files, config, agent, final_ret
            )
            return None, final_ret

        # 未禁用，进行构建验证
        build_validation_result = self._validate_build_after_edit(modified_files)
        if build_validation_result:
            if not build_validation_result.success:
                final_ret = self._handle_build_validation_failure(
                    build_validation_result, config, modified_files, agent, final_ret
                )
            else:
                build_system_info = (
                    f" ({build_validation_result.build_system.value})"
                    if build_validation_result.build_system
                    else ""
                )
                final_ret += f"\n\n✅ 构建验证通过{build_system_info}（耗时 {build_validation_result.duration:.2f}秒）\n"

        return build_validation_result, final_ret

    def _handle_static_analysis(
        self,
        modified_files: List[str],
        build_validation_result: Optional[Any],
        config: Any,
        agent: Agent,
        final_ret: str,
    ) -> str:
        """处理静态分析

        Returns:
            更新后的结果字符串
        """
        # 检查是否启用静态分析
        if not is_enable_static_analysis():
            print("ℹ️ 静态分析已禁用，跳过静态检查")
            return final_ret

        # 检查是否有可用的lint工具
        lint_tools_info = "\n".join(
            f"   - {file}: 使用 {'、'.join(get_lint_tools(file))}"
            for file in modified_files
            if get_lint_tools(file)
        )

        if not lint_tools_info:
            print("ℹ️ 未找到可用的静态检查工具，跳过静态检查")
            return final_ret

        # 如果构建验证失败且未禁用，不进行静态分析（避免重复错误）
        # 如果构建验证已禁用，则进行静态分析（因为只做了基础静态检查）
        should_skip_static = (
            build_validation_result
            and not build_validation_result.success
            and not config.is_build_validation_disabled()
        )

        if should_skip_static:
            print("ℹ️ 构建验证失败，跳过静态分析（避免重复错误）")
            return final_ret

        # 直接执行静态扫描
        lint_results = self._run_static_analysis(modified_files)
        if lint_results:
            # 有错误或警告，让大模型修复
            errors_summary = self._format_lint_results(lint_results)
            # 打印完整的检查结果
            print(f"⚠️ 静态扫描发现问题:\n{errors_summary}")
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

    def _ask_llm_about_large_deletion(
        self, detection_result: Dict[str, int], preview: str
    ) -> bool:
        """询问大模型大量代码删除是否合理

        参数:
            detection_result: 检测结果字典，包含 'insertions', 'deletions', 'net_deletions'
            preview: 补丁预览内容

        返回:
            bool: 如果大模型认为合理返回True，否则返回False
        """
        if not self.model:
            # 如果没有模型，默认认为合理
            return True

        insertions = detection_result["insertions"]
        deletions = detection_result["deletions"]
        net_deletions = detection_result["net_deletions"]

        prompt = f"""检测到大量代码删除，请判断是否合理：

统计信息：
- 新增行数: {insertions}
- 删除行数: {deletions}
- 净删除行数: {net_deletions}

补丁预览：
{preview}

请仔细分析以上代码变更，判断这些大量代码删除是否合理。可能的情况包括：
1. 重构代码，删除冗余或过时的代码
2. 简化实现，用更简洁的代码替换复杂的实现
3. 删除未使用的代码或功能
4. 错误地删除了重要代码

请使用以下协议回答（必须包含且仅包含以下标记之一）：
- 如果认为这些删除是合理的，回答: <!!!YES!!!>
- 如果认为这些删除不合理或存在风险，回答: <!!!NO!!!>

请严格按照协议格式回答，不要添加其他内容。
"""

        try:
            print("🤖 正在询问大模型判断大量代码删除是否合理...")
            response = self.model.chat_until_success(prompt)  # type: ignore

            # 使用确定的协议标记解析回答
            if "<!!!YES!!!>" in response:
                print("✅ 大模型确认：代码删除合理")
                return True
            elif "<!!!NO!!!>" in response:
                print("⚠️ 大模型确认：代码删除不合理")
                return False
            else:
                # 如果无法找到协议标记，默认认为不合理（保守策略）
                print(f"⚠️ 无法找到协议标记，默认认为不合理。回答内容: {response[:200]}")
                return False
        except Exception as e:
            # 如果询问失败，默认认为不合理（保守策略）
            print(f"⚠️ 询问大模型失败: {str(e)}，默认认为不合理")
            return False

    def _on_after_tool_call(
        self,
        agent: Agent,
        current_response=None,
        need_return=None,
        tool_prompt=None,
        **kwargs,
    ) -> None:
        """工具调用后回调函数。"""
        final_ret = ""
        diff = get_diff()

        if diff:
            start_hash = get_latest_commit_hash()
            PrettyOutput.print(diff, OutputType.CODE, lang="diff")  # 保留语法高亮
            modified_files = get_diff_file_list()

            # 更新上下文管理器
            self._update_context_for_modified_files(modified_files)

            # 进行影响范围分析
            impact_report = self._analyze_edit_impact(modified_files)

            per_file_preview = self._build_per_file_patch_preview(modified_files)

            # 所有模式下，在提交前检测大量代码删除并询问大模型
            detection_result = detect_large_code_deletion()
            if detection_result is not None:
                # 检测到大量代码删除，询问大模型是否合理
                is_reasonable = self._ask_llm_about_large_deletion(
                    detection_result, per_file_preview
                )
                if not is_reasonable:
                    # 大模型认为不合理，撤销修改
                    print("ℹ️ 已撤销修改（大模型认为代码删除不合理）")
                    revert_change()
                    final_ret += (
                        "\n\n修改被撤销（检测到大量代码删除且大模型判断不合理）\n"
                    )
                    final_ret += f"# 补丁预览（按文件）:\n{per_file_preview}"
                    PrettyOutput.print(
                        final_ret, OutputType.USER, lang="markdown"
                    )  # 保留语法高亮
                    self.session.prompt += final_ret
                    return

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
                    # 获取最新的提交信息（commits列表按时间倒序，第一个是最新的）
                    latest_commit_hash, latest_commit_message = commits[0]
                    commit_short_hash = (
                        latest_commit_hash[:7]
                        if len(latest_commit_hash) >= 7
                        else latest_commit_hash
                    )

                    final_ret += (
                        f"\n\n代码已修改完成\n"
                        f"✅ 已自动提交\n"
                        f"   Commit ID: {commit_short_hash} ({latest_commit_hash})\n"
                        f"   提交信息: {latest_commit_message}\n"
                        f"\n补丁内容（按文件）:\n{per_file_preview}\n"
                    )

                    # 添加影响范围分析报告
                    final_ret = self._handle_impact_report(
                        impact_report, self, final_ret
                    )

                    # 构建验证
                    config = BuildValidationConfig(self.root_dir)
                    build_validation_result, final_ret = self._handle_build_validation(
                        modified_files, self, final_ret
                    )

                    # 静态分析
                    final_ret = self._handle_static_analysis(
                        modified_files, build_validation_result, config, self, final_ret
                    )
                else:
                    # 如果没有获取到commits，尝试直接从end_hash获取commit信息
                    commit_info = ""
                    if end_hash:
                        try:
                            result = subprocess.run(
                                ["git", "log", "-1", "--pretty=format:%H|%s", end_hash],
                                capture_output=True,
                                text=True,
                                encoding="utf-8",
                                errors="replace",
                                check=False,
                            )
                            if (
                                result.returncode == 0
                                and result.stdout
                                and "|" in result.stdout
                            ):
                                commit_hash, commit_message = (
                                    result.stdout.strip().split("|", 1)
                                )
                                commit_short_hash = (
                                    commit_hash[:7]
                                    if len(commit_hash) >= 7
                                    else commit_hash
                                )
                                commit_info = (
                                    f"\n✅ 已自动提交\n"
                                    f"   Commit ID: {commit_short_hash} ({commit_hash})\n"
                                    f"   提交信息: {commit_message}\n"
                                )
                        except Exception:
                            pass

                    if commit_info:
                        final_ret += f"\n\n代码已修改完成{commit_info}\n"
                    else:
                        final_ret += "\n\n修改没有生效\n"
            else:
                final_ret += "\n修改被拒绝\n"
                final_ret += f"# 补丁预览（按文件）:\n{per_file_preview}"
        else:
            return
        # 用户确认最终结果
        if commited:
            self.session.prompt += final_ret
            return
        PrettyOutput.print(final_ret, OutputType.USER, lang="markdown")  # 保留语法高亮
        if not is_confirm_before_apply_patch() or user_confirm(
            "是否使用此回复？", default=True
        ):
            self.session.prompt += final_ret
            return
        # 用户未确认，允许输入自定义回复作为附加提示
        custom_reply = get_multiline_input("请输入自定义回复")
        if custom_reply.strip():  # 如果自定义回复为空，不设置附加提示
            self.set_addon_prompt(custom_reply)
        self.session.prompt += final_ret
        return

    def _run_static_analysis(
        self, modified_files: List[str]
    ) -> List[Tuple[str, str, str, int, str]]:
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
        print("🔍 静态检查中...")

        results = []
        # 记录每个文件的检查结果
        file_results = []  # [(file_path, tool_name, status, message), ...]

        # 按工具分组，相同工具可以批量执行
        grouped = group_commands_by_tool(commands)

        for tool_name, file_commands in grouped.items():
            for file_path, command in file_commands:
                file_name = os.path.basename(file_path)
                try:
                    # 检查文件是否存在
                    abs_file_path = (
                        os.path.join(self.root_dir, file_path)
                        if not os.path.isabs(file_path)
                        else file_path
                    )
                    if not os.path.exists(abs_file_path):
                        file_results.append(
                            (file_name, tool_name, "跳过", "文件不存在")
                        )
                        continue

                    # 打印执行的命令
                    print(f"ℹ️ 执行: {command}")

                    # 执行命令
                    result = subprocess.run(
                        command,
                        shell=True,
                        cwd=self.root_dir,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=600,  # 600秒超时
                    )

                    # 只记录有错误或警告的结果
                    if result.returncode != 0:
                        output = result.stdout + result.stderr
                        if output.strip():  # 有输出才记录
                            results.append(
                                (
                                    tool_name,
                                    file_path,
                                    command,
                                    result.returncode,
                                    output,
                                )
                            )
                            file_results.append(
                                (file_name, tool_name, "失败", "发现问题")
                            )
                            # 失败时打印检查结果
                            output_preview = (
                                output[:2000] if len(output) > 2000 else output
                            )
                            print(f"⚠️ 检查失败 ({file_name}):\n{output_preview}")
                            if len(output) > 2000:
                                print(f"⚠️ ... (输出已截断，共 {len(output)} 字符)")
                        else:
                            file_results.append((file_name, tool_name, "通过", ""))
                    else:
                        file_results.append((file_name, tool_name, "通过", ""))

                except subprocess.TimeoutExpired:
                    results.append(
                        (tool_name, file_path, command, -1, "执行超时（600秒）")
                    )
                    file_results.append(
                        (file_name, tool_name, "超时", "执行超时（600秒）")
                    )
                    print(f"⚠️ 检查超时 ({file_name}): 执行超时（600秒）")
                except FileNotFoundError:
                    # 工具未安装，跳过
                    file_results.append((file_name, tool_name, "跳过", "工具未安装"))
                    continue
                except Exception as e:
                    # 其他错误，记录但继续
                    print(f"⚠️ 执行lint命令失败: {command}, 错误: {e}")
                    file_results.append(
                        (file_name, tool_name, "失败", f"执行失败: {str(e)[:50]}")
                    )
                    continue

        # 一次性打印所有检查结果
        if file_results:
            total_files = len(file_results)
            passed_count = sum(
                1 for _, _, status, _ in file_results if status == "通过"
            )
            failed_count = sum(
                1 for _, _, status, _ in file_results if status == "失败"
            )
            timeout_count = sum(
                1 for _, _, status, _ in file_results if status == "超时"
            )
            sum(1 for _, _, status, _ in file_results if status == "跳过")

            # 收缩为一行的结果摘要
            summary = f"🔍 静态检查: {total_files}个文件"
            if failed_count > 0:
                summary += f", {failed_count}失败"
            if timeout_count > 0:
                summary += f", {timeout_count}超时"
            if passed_count == total_files:
                summary += " ✅全部通过"

            if failed_count > 0 or timeout_count > 0:
                print(f"⚠️ {summary}")
            else:
                print(f"✅ {summary}")
        else:
            print("✅ 静态检查完成")

        return results

    def _format_lint_results(
        self, results: List[Tuple[str, str, str, int, str]]
    ) -> str:
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

    def _validate_build_after_edit(
        self, modified_files: List[str]
    ) -> Optional[BuildResult]:
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
        print(f"🔨 正在进行编译检查 ({files_str})...")

        try:
            timeout = get_build_validation_timeout()
            validator = BuildValidator(self.root_dir, timeout=timeout)
            result = validator.validate(modified_files)
            return result
        except Exception as e:
            # 构建验证失败不应该影响主流程，仅记录日志
            print(f"⚠️ 构建验证执行失败: {e}")
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
        False,
        "-n",
        "--non-interactive",
        help="启用非交互模式：用户无法与命令交互，脚本执行超时限制为5分钟",
    ),
    rule_names: Optional[str] = typer.Option(
        None,
        "--rule-names",
        help="指定规则名称列表，用逗号分隔，从 rules.yaml 文件中读取对应的规则内容",
    ),
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
        print(
            "❌ 非交互模式已启用：必须使用 --requirement 传入任务内容，因多行输入不可用。"
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
        print(f"⚠️ 警告：当前目录 '{curr_dir_path}' 不是一个git仓库。")
        init_git = (
            True
            if non_interactive
            else user_confirm(
                f"是否要在 '{curr_dir_path}' 中初始化一个新的git仓库？", default=True
            )
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
                print("✅ 已成功初始化git仓库。")
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                print(f"❌ 初始化git仓库失败: {e}")
                sys.exit(1)
        else:
            print("ℹ️ 操作已取消。Jarvis需要在git仓库中运行。")
            sys.exit(0)

    curr_dir = os.getcwd()
    find_git_root_and_cd(curr_dir)
    # 在定位到 git 根目录后，按仓库维度加锁，避免跨仓库互斥
    try:
        repo_root = os.getcwd()
        lock_name = (
            f"code_agent_{hashlib.md5(repo_root.encode('utf-8')).hexdigest()}.lock"
        )
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
            rule_names=rule_names,
        )

        # 尝试恢复会话
        if restore_session:
            if agent.restore_session():
                print("✅ 已从 .jarvis/saved_session.json 恢复会话。")
            else:
                print("⚠️ 无法从 .jarvis/saved_session.json 恢复会话。")

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
        print(f"❌ 错误: {str(e)}")
        sys.exit(1)


def main() -> None:
    """Application entry point."""
    app()


if __name__ == "__main__":
    main()
