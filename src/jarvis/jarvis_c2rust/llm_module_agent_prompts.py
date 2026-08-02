# -*- coding: utf-8 -*-
"""LLM 模块规划 Agent 的提示词构建逻辑。"""

from jarvis.jarvis_utils.exception_utils import save_exception
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
                    except Exception as e:
                        save_exception(
                            e,
                            module="jarvis_c2rust.llm_module_agent_prompts",
                            function="_extract_names_from_items",
                        )
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
下供项目调用图之上下（JSON），先通读之，勿出规划或JSON之文：
<context>
{context_json}
</context>

若已备毕欲入总结之阶以成全出，唯出：{ot("!!!COMPLETE!!!")}，勿杂他辞。事之总结，待后询。
""".strip()
        return self.append_additional_notes(prompt)

    def build_system_prompt(self) -> str:
        """
        系统提示：描述如何基于依赖关系进行 crate 规划的原则（不涉及对话流程或输出方式）
        """
        crate_name = self.crate_name_func()
        prompt = (
            "汝为资深 Rust 架构师。任务：据所予函数级调用关系（唯含 root_function 及其可达函数名之表），为彼项目规合宜之 Rust crate 结构。\n"
            "\n"
            "规划之则：\n"
            "- 根导：以各 root_function 为界组顶层模块，成清晰之入口与责任之域。\n"
            "- 内聚先：按调用内聚性分子模块，使强相关函数同处一子模块，减跨模块耦。\n"
            "- 去环分层：力消循环依赖；循自上而下之调用向，保依赖向稳而层次明。\n"
            "- 共享抽取：为多 root 所用之共性，抽入 common/ 或 shared/ 模块，免重复与交叉依赖。\n"
            "- 界隔：平台/IO/外设等界能，独立入 adapter/ 或 ffi/ 等模块（若有）。\n"
            "- 命名规：目录/文件用小写下划线；模块名简而可读，避特殊字符与过繁之名。\n"
            "- 可演进：模块粒度适中，留扩展点，便后重构与渐代遗留之码。\n"
            "- 模块组织：每目录之 mod.rs 宣其子目录与 .rs 子模块；顶层 lib.rs 汇出主模块与公共之能。\n"
            "- 入口策（务遵，bin 唯作入口，功能尽于 lib 中成）：\n"
            "  * 若原项目含 main 函数：勿生 src/main.rs；用 src/bin/"
            + crate_name
            + ".rs 为唯一可执入口，其中唯留至简入口逻辑（调库层）；共享码置 src/lib.rs；\n"
            "  * 若原项目不含 main 函数：勿生任何二进制入口（不建 src/main.rs 或 src/bin/），唯生 src/lib.rs；\n"
            "  * 多可执，唯果有数清晰入口方用 src/bin/<name>.rs；每 bin 文件唯作入口，尽量调库；\n"
            "  * 二进制命名：<name> 用小写下划线，彰入口之意，避与模块/文件同名。\n"
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
输出之规：
- 唯出 <PROJECT> 一区
- 区外不得有任何字符（含空行、注释、Markdown 等）
- 区内必为 JSON 数组：
  - 目录项用对象表之，键为 '<name>/'，值为子项数组
  - 文件为字符串项（例如 "lib.rs"）
- 勿建与入口无关之占位文件
""".strip()
        if has_main:
            entry_rule = f"""
入口之约（因原项目有 main）：
- 必含 src/lib.rs；
- 勿含 src/main.rs；
- 必含 src/bin/{crate_name}.rs，为唯一可执入口（唯作入口，调库逻辑）；
- 如无明分之多入口，勿建额外 bin 文件。
正例（JSON格式）：
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
入口之约（因原项目无 main）：
- 必含 src/lib.rs；
- 勿含 src/main.rs；
- 勿含 src/bin/ 目录。
正例（JSON格式）：
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
据前对话已供之<context>，成总结之出（项目目录结构之 JSON）。严遵下求：

{guidance}

汝之出，唯含以下单区（以项目实目录结构代区内）：
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
            "\n\n[格式校验败，必重试]\n"
            f"- 败因：{error_reason}\n"
            '- 严遵上述"输出之规"与"入口之约"，重出；\n'
            "- 唯出 <PROJECT> 一区，区内为可解析之 JSON 数组；区外不得有任何字符。\n"
        )
        return base_summary_prompt + feedback
