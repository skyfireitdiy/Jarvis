# -*- coding: utf-8 -*-
"""
符号映射模块
"""

import re
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Dict
from typing import List

from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_c2rust.models import FnRecord
from jarvis.jarvis_c2rust.transpiler_modules import ModuleManager


class SymbolMapper:
    """符号映射管理器"""

    def __init__(
        self,
        symbol_map: Any,  # _SymbolMapJsonl
        progress: Dict[str, Any],
        config_manager: Any,  # ConfigManager
        git_manager: Any,  # GitManager
    ) -> None:
        self.symbol_map = symbol_map
        self.progress = progress
        self.config_manager = config_manager
        self.git_manager = git_manager

    def should_skip(self, rec: FnRecord) -> bool:
        """判断是否应该跳过该函数"""
        # 已转译的跳过（按源位置与名称唯一性判断，避免同名不同位置的误判）
        if self.symbol_map.has_rec(rec):
            return True
        return False

    def mark_converted(self, rec: FnRecord, module: str, rust_sig: str) -> None:
        """记录映射：C 符号 -> Rust 符号与模块路径（JSONL，每行一条，支持重载/同名）"""
        rust_symbol = ""
        # 从签名中提取函数名（支持生命周期参数和泛型参数）
        # 支持生命周期参数和泛型参数：fn name<'a, T>(...)
        m = re.search(r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:<[^>]+>)?\s*\(", rust_sig)
        if m:
            rust_symbol = m.group(1)
        # 写入 JSONL 映射（带源位置，用于区分同名符号）
        self.symbol_map.add(rec, module, rust_symbol or (rec.name or f"fn_{rec.id}"))

        # 获取当前 commit id 并记录
        current_commit = self.git_manager.get_crate_commit_hash()

        # 更新进度：已转换集合
        converted = self.progress.get("converted") or []
        if rec.id not in converted:
            converted.append(rec.id)
        self.progress["converted"] = converted
        self.progress["current"] = None

        # 记录每个已转换函数的 commit id
        converted_commits = self.progress.get("converted_commits") or {}
        if current_commit:
            converted_commits[str(rec.id)] = current_commit
            self.progress["converted_commits"] = converted_commits
            PrettyOutput.auto_print(
                f"🔍 [c2rust-transpiler][progress] 已记录函数 {rec.id} 的 commit: {current_commit}"
            )

        self.config_manager.save_progress()

    def resolve_pending_todos_for_symbol(
        self,
        symbol: str,
        callee_module: str,
        callee_rust_fn: str,
        callee_rust_sig: str,
        crate_dir: Path,
        get_code_agent_func: Callable[[], Any],
        compose_prompt_func: Callable[[str], str],
        check_and_handle_test_deletion_func: Callable[[str, Any], bool],
    ) -> None:
        """
        当某个 C 符号对应的函数已转换为 Rust 后：
        - 扫描整个 crate（优先 src/ 目录）中所有 .rs 文件，查找占位：todo!("符号名") 或 unimplemented!("符号名")
        - 对每个命中的文件，创建 CodeAgent 将占位替换为对已转换函数的真实调用（可使用 crate::... 完全限定路径或 use 引入）
        - 最小化修改，避免无关重构

        说明：不再使用 todos.json，本方法直接搜索源码中的 todo!("xxxx") / unimplemented!("xxxx")。
        """
        if not symbol:
            return

        # 计算被调函数的crate路径前缀，便于在提示中提供调用路径建议
        module_manager = ModuleManager(crate_dir)
        callee_path = module_manager.module_file_to_crate_path(callee_module)

        # 扫描 src 下的 .rs 文件，查找 todo!("symbol") 或 unimplemented!("symbol") 占位
        matches: List[str] = []
        src_root = (crate_dir / "src").resolve()
        if src_root.exists():
            for p in sorted(src_root.rglob("*.rs")):
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                pat_todo = re.compile(
                    r'todo\s*!\s*\(\s*["\']' + re.escape(symbol) + r'["\']\s*\)'
                )
                pat_unimpl = re.compile(
                    r'unimplemented\s*!\s*\(\s*["\']'
                    + re.escape(symbol)
                    + r'["\']\s*\)'
                )
                if pat_todo.search(text) or pat_unimpl.search(text):
                    try:
                        # 记录绝对路径，避免依赖当前工作目录
                        abs_path = str(p.resolve())
                    except Exception:
                        abs_path = str(p)
                    matches.append(abs_path)

        if not matches:
            PrettyOutput.auto_print(
                f'🔍 [c2rust-transpiler][todo] 未在 src/ 中找到 todo!("{symbol}") 或 unimplemented!("{symbol}") 的出现'
            )
            return

        # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
        PrettyOutput.auto_print(
            f'🔍 [c2rust-transpiler][todo] 发现 {len(matches)} 个包含 todo!("{symbol}") 或 unimplemented!("{symbol}") 的文件'
        )
        for target_file in matches:
            prompt = "\n".join(
                [
                    f"请在文件 {target_file} 中，定位所有以下占位并替换为对已转换函数的真实调用：",
                    f'- todo!("{symbol}")',
                    f'- unimplemented!("{symbol}")',
                    "要求：",
                    f"- 已转换的目标函数名：{callee_rust_fn}",
                    f"- 其所在模块（crate路径提示）：{callee_path}",
                    f"- 函数签名提示：{callee_rust_sig}",
                    f"- 当前 crate 根目录路径：{crate_dir.resolve()}",
                    "- 优先使用完全限定路径（如 crate::...::函数(...)）；如需在文件顶部添加 use，仅允许精确导入，不允许通配（例如 use ...::*）；",
                    "- 保持最小改动，不要进行与本次修复无关的重构或格式化；",
                    "- 如果参数列表暂不明确，可使用合理占位变量，确保编译通过。",
                    "",
                    f"仅修改 {target_file} 中与上述占位相关的代码，其他位置不要改动。",
                    "请仅输出补丁，不要输出解释或多余文本。",
                ]
            )
            # 记录运行前的 commit
            before_commit = self.git_manager.get_crate_commit_hash()
            agent = get_code_agent_func()
            agent.run(
                compose_prompt_func(prompt),
                prefix=f"[c2rust-transpiler][todo-fix:{symbol}]",
                suffix="",
            )

            # 检测并处理测试代码删除
            if check_and_handle_test_deletion_func(before_commit, agent):
                # 如果回退了，需要重新运行 agent
                PrettyOutput.auto_print(
                    f"⚠️ [c2rust-transpiler][todo-fix] 检测到测试代码删除问题，已回退，重新运行 agent (symbol={symbol})"
                )
                before_commit = self.git_manager.get_crate_commit_hash()
                agent.run(
                    compose_prompt_func(prompt),
                    prefix=f"[c2rust-transpiler][todo-fix:{symbol}][retry]",
                    suffix="",
                )
                # 再次检测
                if check_and_handle_test_deletion_func(before_commit, agent):
                    PrettyOutput.auto_print(
                        f"❌ [c2rust-transpiler][todo-fix] 再次检测到测试代码删除问题，已回退 (symbol={symbol})"
                    )
