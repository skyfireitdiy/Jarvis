"""CodeAgent 影响分析模块"""

from typing import Any
from typing import Dict

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
from typing import List
from typing import Optional
from typing import Tuple

from jarvis.jarvis_code_agent.code_analyzer import ContextManager
from jarvis.jarvis_code_agent.code_analyzer import ImpactAnalyzer
from jarvis.jarvis_code_agent.code_analyzer import parse_git_diff_to_edits
from jarvis.jarvis_code_agent.code_analyzer.impact_analyzer import Edit
from jarvis.jarvis_utils.config import get_default_encoding, is_enable_impact_analysis


class ImpactManager:
    """影响分析管理器"""

    def __init__(self, root_dir: str, context_manager: ContextManager):
        self.root_dir = root_dir
        self.context_manager = context_manager

    def update_context_for_modified_files(self, modified_files: List[str]) -> None:
        """更新上下文管理器：当文件被修改后，更新符号表和依赖图"""
        if not modified_files:
            return
        PrettyOutput.auto_print("🔄 正在更新代码上下文...")
        for file_path in modified_files:
            import os

            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding=get_default_encoding(), errors="replace") as f:
                        content = f.read()
                    self.context_manager.update_context_for_file(file_path, content)
                except Exception:
                    # 如果读取文件失败，跳过更新
                    pass

    def analyze_edit_impact(self, modified_files: List[str]) -> Optional[Any]:
        """进行影响范围分析（如果启用）

        Returns:
            ImpactReport: 影响分析报告，如果未启用或失败则返回None
        """
        if not is_enable_impact_analysis():
            return None

        PrettyOutput.auto_print("🔍 正在进行变更影响分析...")
        try:
            impact_analyzer = ImpactAnalyzer(self.context_manager)
            all_edits = []
            import os

            for file_path in modified_files:
                if os.path.exists(file_path):
                    edits = parse_git_diff_to_edits(file_path, self.root_dir)
                    all_edits.extend(edits)

            if not all_edits:
                return None

            # 按文件分组编辑
            edits_by_file: Dict[str, List[Edit]] = {}
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
                        symbol_map: Dict[Tuple[str, str, str], Any] = {}
                        for symbol in (
                            impact_report.affected_symbols + report.affected_symbols
                        ):
                            key = (
                                symbol.file_path,
                                symbol.name,
                                str(symbol.line_start),
                            )
                            if key not in symbol_map:
                                symbol_map[key] = symbol
                        impact_report.affected_symbols = list(symbol_map.values())

                        impact_report.affected_tests = list(
                            set(impact_report.affected_tests + report.affected_tests)
                        )

                        # 合并接口变更（基于符号名和文件路径去重）
                        interface_map: Dict[Tuple[str, str, str], Any] = {}
                        for change in (
                            impact_report.interface_changes + report.interface_changes
                        ):
                            key = (
                                change.file_path,
                                change.symbol_name,
                                str(change.change_type),
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
            PrettyOutput.auto_print(f"⚠️ 影响范围分析失败: {e}")
            return None

    def handle_impact_report(
        self, impact_report: Optional[Any], agent: Any, final_ret: str
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
