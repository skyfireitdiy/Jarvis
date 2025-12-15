# -*- coding: utf-8 -*-
"""LLM 模块规划 Agent 的提示词构建逻辑。"""

import json
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Dict
from typing import List

from jarvis.jarvis_c2rust.llm_module_agent_utils import resolve_created_dir
from jarvis.jarvis_utils.jsonnet_compat import loads as json_loads
from jarvis.jarvis_utils.tag import ot


class PromptBuilder:
    """提示词构建器。"""

    def __init__(
        self,
        project_root: Path,
        loader: Any,  # GraphLoader
        crate_name_func: Callable[[], str],
        has_original_main_func: Callable[[], bool],
        append_additional_notes_func: Callable[[str], str],
    ):
        self.project_root = project_root
        self.loader = loader
        self.crate_name_func = crate_name_func
        self.has_original_main_func = has_original_main_func
        self.append_additional_notes = append_additional_notes_func

    def build_roots_context_from_order(self) -> List[Dict[str, Any]]:
        """
        基于 translation_order.jsonl 生成用于规划的上下文：
        - 以每个 step 的 roots 标签为分组键（通常每步一个 root 标签）
        - 函数列表来自每步的 items 中的符号 'name' 字段，按 root 聚合去重
        - 跳过无 roots 标签的 residual 步骤（仅保留明确 root 的上下文）
        - 若最终未收集到任何 root 组，则回退为单组 'project'，包含所有 items 的函数名集合
        """
        order_path = (
            self.project_root / ".jarvis" / "c2rust" / "translation_order.jsonl"
        )
        if not order_path.exists():
            raise FileNotFoundError(f"未找到 translation_order.jsonl: {order_path}")

        def _deduplicate_names(names: List[str]) -> List[str]:
            """去重并排序函数名列表"""
            try:
                return sorted(list(dict.fromkeys(names)))
            except (TypeError, ValueError):
                return sorted(list(set(names)))

        def _extract_names_from_items(items: List[Any]) -> List[str]:
            """从 items 中提取函数名"""
            names: List[str] = []
            for it in items:
                if isinstance(it, dict):
                    nm = it.get("name") or ""
                    if isinstance(nm, str) and nm.strip():
                        names.append(str(nm).strip())
            return names

        groups: Dict[str, List[str]] = {}
        all_names_fallback: List[str] = []  # 用于回退场景

        try:
            with order_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json_loads(line)
                    except Exception:
                        continue

                    roots = obj.get("roots") or []
                    items = obj.get("items") or []
                    if not isinstance(items, list) or not items:
                        continue

                    # 提取所有函数名（用于回退场景）
                    item_names = _extract_names_from_items(items)
                    all_names_fallback.extend(item_names)

                    # 提取 root 标签
                    root_labels = [
                        str(r).strip()
                        for r in roots
                        if isinstance(r, str) and str(r).strip()
                    ]
                    if not root_labels:
                        continue

                    # 去重 step_names
                    step_names = _deduplicate_names(item_names)
                    if not step_names:
                        continue

                    # 按 root 聚合
                    for r in root_labels:
                        groups.setdefault(r, []).extend(step_names)
        except (OSError, IOError) as e:
            raise RuntimeError(f"读取 translation_order.jsonl 时发生错误: {e}") from e

        contexts: List[Dict[str, Any]] = []
        for root_label, names in groups.items():
            names = _deduplicate_names(names)
            contexts.append({"root_function": root_label, "functions": sorted(names)})

        # 回退：如果没有任何 root 组，使用所有 items 作为单组 'project'
        if not contexts:
            all_names = _deduplicate_names(all_names_fallback)
            if all_names:
                contexts.append(
                    {"root_function": "project", "functions": sorted(all_names)}
                )

        return contexts

    def build_user_prompt(self, roots_context: List[Dict[str, Any]]) -> str:
        """
        主对话阶段：传入上下文，不给出输出要求，仅用于让模型获取信息并触发进入总结阶段。
        请模型仅输出 {ot('!!!COMPLETE!!!')} 以进入总结（summary）阶段。不要输出其他任何内容，任务总结将会在后面的交互中被询问。
        """
        crate_name = self.crate_name_func()
        has_main = self.has_original_main_func()
        created_dir = resolve_created_dir(self.project_root)
        context_json = json.dumps(
            {
                "meta": {
                    "crate_name": crate_name,
                    "main_present": has_main,
                    "crate_dir": str(created_dir),
                },
                "roots": roots_context,
            },
            ensure_ascii=False,
            indent=2,
        )
        prompt = f"""
下面提供了项目的调用图上下文（JSON），请先通读理解，不要输出任何规划或JSON内容：
<context>
{context_json}
</context>

如果已准备好进入总结阶段以生成完整输出，请仅输出：{ot("!!!COMPLETE!!!")}，不要输出其他任何内容。任务总结将会在后面的交互中被询问。
""".strip()
        return self.append_additional_notes(prompt)

    def build_system_prompt(self) -> str:
        """
        系统提示：描述如何基于依赖关系进行 crate 规划的原则（不涉及对话流程或输出方式）
        """
        crate_name = self.crate_name_func()
        prompt = (
            "你是资深 Rust 架构师。任务：根据给定的函数级调用关系（仅包含 root_function 及其可达的函数名列表），为目标项目规划合理的 Rust crate 结构。\n"
            "\n"
            "规划原则：\n"
            "- 根导向：以每个 root_function 为边界组织顶层模块，形成清晰的入口与责任范围。\n"
            "- 内聚优先：按调用内聚性拆分子模块，使强相关函数位于同一子模块，减少跨模块耦合。\n"
            "- 去环与分层：尽量消除循环依赖；遵循由上到下的调用方向，保持稳定依赖方向与层次清晰。\n"
            "- 共享抽取：被多个 root 使用的通用能力抽取到 common/ 或 shared/ 模块，避免重复与交叉依赖。\n"
            "- 边界隔离：将平台/IO/外设等边界能力独立到 adapter/ 或 ffi/ 等模块（如存在）。\n"
            "- 命名规范：目录/文件采用小写下划线；模块名简洁可读，避免特殊字符与过长名称。\n"
            "- 可演进性：模块粒度适中，保留扩展点，便于后续重构与逐步替换遗留代码。\n"
            "- 模块组织：每个目录的 mod.rs 声明其子目录与 .rs 子模块；顶层 lib.rs 汇聚导出主要模块与公共能力。\n"
            "- 入口策略（务必遵循，bin 仅做入口，功能尽量在 lib 中实现）：\n"
            "  * 若原始项目包含 main 函数：不要生成 src/main.rs；使用 src/bin/"
            + crate_name
            + ".rs 作为唯一可执行入口，并在其中仅保留最小入口逻辑（调用库层）；共享代码放在 src/lib.rs；\n"
            "  * 若原始项目不包含 main 函数：不要生成任何二进制入口（不创建 src/main.rs 或 src/bin/），仅生成 src/lib.rs；\n"
            "  * 多可执行仅在确有多个清晰入口时才使用 src/bin/<name>.rs；每个 bin 文件仅做入口，尽量调用库；\n"
            "  * 二进制命名：<name> 使用小写下划线，体现入口意图，避免与模块/文件重名。\n"
        )
        return self.append_additional_notes(prompt)

    def build_summary_prompt(self, roots_context: List[Dict[str, Any]]) -> str:
        """
        总结阶段：只输出目录结构的 JSON。
        要求：
        - 仅输出一个 <PROJECT> 块
        - <PROJECT> 与 </PROJECT> 之间必须是可解析的 JSON 数组
        - 目录以对象表示，键为 '目录名/'，值为子项数组；文件为字符串
        - 块外不得有任何字符（包括空行、注释、Markdown、解释文字、schema等）
        - 不要输出 crate 名称或其他多余字段
        """
        has_main = self.has_original_main_func()
        crate_name = self.crate_name_func()
        guidance_common = """
输出规范：
- 只输出一个 <PROJECT> 块
- 块外不得有任何字符（包括空行、注释、Markdown 等）
- 块内必须是 JSON 数组：
  - 目录项使用对象表示，键为 '<name>/'，值为子项数组
  - 文件为字符串项（例如 "lib.rs"）
- 不要创建与入口无关的占位文件
- 支持jsonnet语法（如尾随逗号、注释、||| 或 ``` 分隔符多行字符串等）
""".strip()
        if has_main:
            entry_rule = f"""
入口约定（基于原始项目存在 main）：
- 必须包含 src/lib.rs；
- 不要包含 src/main.rs；
- 必须包含 src/bin/{crate_name}.rs，作为唯一可执行入口（仅做入口，调用库逻辑）；
- 如无明确多个入口，不要创建额外 bin 文件。
正确示例（JSON格式）：
<PROJECT>
[
  "Cargo.toml",
  {{
    "src/": [
      "lib.rs",
      {{
        "bin/": [
          "{crate_name}.rs"
        ]
      }}
    ]
  }}
]
</PROJECT>
""".strip()
        else:
            entry_rule = """
入口约定（基于原始项目不存在 main）：
- 必须包含 src/lib.rs；
- 不要包含 src/main.rs；
- 不要包含 src/bin/ 目录。
正确示例（JSON格式）：
<PROJECT>
[
  "Cargo.toml",
  {
    "src/": [
      "lib.rs"
    ]
  }
]
</PROJECT>
""".strip()
        guidance = f"{guidance_common}\n{entry_rule}"
        prompt = f"""
请基于之前对话中已提供的<context>信息，生成总结输出（项目目录结构的 JSON）。严格遵循以下要求：

{guidance}

你的输出必须仅包含以下单个块（用项目的真实目录结构替换块内内容）：
<PROJECT>
[...]
</PROJECT>
""".strip()
        return self.append_additional_notes(prompt)

    def build_retry_summary_prompt(
        self, base_summary_prompt: str, error_reason: str
    ) -> str:
        """
        在原始 summary_prompt 基础上，附加错误反馈，要求严格重试。
        """
        feedback = (
            "\n\n[格式校验失败，必须重试]\n"
            f"- 失败原因：{error_reason}\n"
            '- 请严格遵循上述"输出规范"与"入口约定"，重新输出；\n'
            "- 仅输出一个 <PROJECT> 块，块内为可解析的 JSON 数组；块外不得有任何字符。\n"
        )
        return base_summary_prompt + feedback
