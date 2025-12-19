"""智能上下文推荐器。

使用LLM进行语义理解，提供更准确的上下文推荐。
完全基于LLM实现，不依赖硬编码规则。
"""

import json
import os
import re
from typing import Any
from typing import List
from typing import Optional

from rich.console import Console

from jarvis.jarvis_code_agent.utils import get_project_overview
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_utils.config import get_cheap_model_name
from jarvis.jarvis_utils.config import get_cheap_platform_name
from jarvis.jarvis_utils.globals import get_global_model_group
from jarvis.jarvis_utils.jsonnet_compat import loads as json_loads

from .context_manager import ContextManager
from .context_recommender import ContextRecommendation
from .symbol_extractor import Symbol


class ContextRecommender:
    """智能上下文推荐器。

    使用LLM进行语义理解，根据编辑意图推荐相关的上下文信息。
    完全基于LLM实现，提供语义级别的推荐，而非简单的关键词匹配。
    """

    def __init__(
        self, context_manager: ContextManager, parent_model: Optional[Any] = None
    ):
        """初始化上下文推荐器

        Args:
            context_manager: 上下文管理器
            parent_model: 父Agent的模型实例（已废弃，保留参数兼容性）

        Note:
            LLM 模型实例不会在初始化时创建，而是在每次调用时重新创建，
            以避免上下文窗口累积导致的问题。
            模型配置从全局模型组获取，不再从parent_model继承。
        """
        self.context_manager = context_manager

        # 保存配置信息，用于后续创建 LLM 实例
        self._platform_name = None
        self._model_name = None
        # 使用全局模型组（不再从 parent_model 继承）
        self._model_group = get_global_model_group()

        # 根据 model_group 获取配置
        # 使用cheap平台，筛选操作可以降低成本
        if self._model_group:
            try:
                self._platform_name = get_cheap_platform_name(self._model_group)
                self._model_name = get_cheap_model_name(self._model_group)
            except Exception:
                # 如果从 model_group 解析失败，使用默认配置
                pass

    def recommend_context(
        self,
        user_input: str,
    ) -> ContextRecommendation:
        """根据编辑意图推荐上下文

        Args:
            user_input: 用户输入/任务描述

        Returns:
            ContextRecommendation: 推荐的上下文信息
        """

        # 0. 检查并填充符号表（如果为空）
        self._ensure_symbol_table_loaded()

        # 检查符号表是否为空（构建完成后仍然为空）
        symbol_count = sum(
            len(symbols)
            for symbols in self.context_manager.symbol_table.symbols_by_name.values()
        )
        if symbol_count == 0:
            return ContextRecommendation(recommended_symbols=[])

        # 1. 使用LLM生成相关关键词
        keywords = self._extract_keywords_with_llm(user_input)

        # 2. 初始化推荐结果
        recommended_symbols: List[Symbol] = []

        # 3. 基于关键词进行符号查找，然后使用LLM挑选关联度高的条目（主要推荐方式）
        if keywords:
            # 3.1 使用关键词进行模糊查找，找到所有候选符号及其位置
            candidate_symbols = self._search_symbols_by_keywords(keywords)

            candidate_symbols_list = candidate_symbols

            # 3.2 使用LLM从候选符号中挑选关联度高的条目
            if candidate_symbols_list:
                selected_symbols = self._select_relevant_symbols_with_llm(
                    user_input, keywords, candidate_symbols_list
                )
                recommended_symbols.extend(selected_symbols)

        # 4. 对推荐符号去重（基于符号名称）
        seen = set()
        unique_symbols = []
        for symbol in recommended_symbols:
            key = (symbol.name,)
            if key not in seen:
                seen.add(key)
                unique_symbols.append(symbol)

        # 5. 限制符号数量
        final_symbols = unique_symbols[:10]
        return ContextRecommendation(
            recommended_symbols=final_symbols,
        )

    def _get_project_overview(self) -> str:
        """获取项目概况信息

        Returns:
            项目概况字符串
        """
        return get_project_overview(self.context_manager.project_root)

    def _ensure_symbol_table_loaded(self) -> None:
        """确保符号表已加载（如果为空则扫描项目文件）

        在推荐上下文之前，需要确保符号表已经被填充。
        如果符号表为空，则扫描项目文件并填充符号表。
        """
        # 检查符号表是否为空
        if not self.context_manager.symbol_table.symbols_by_name:
            self._build_symbol_table()

    def _build_symbol_table(self) -> None:
        """扫描项目文件并构建符号表

        遍历项目目录，提取所有支持语言的符号。
        """
        import os

        from .file_ignore import filter_walk_dirs
        from .language_support import detect_language
        from .language_support import get_symbol_extractor

        console = Console()
        project_root = self.context_manager.project_root
        files_scanned = 0
        symbols_added = 0
        files_with_symbols = 0
        files_skipped = 0

        # 用于清除行的最大宽度（终端通常80-120字符，使用100作为安全值）
        max_line_width = 100

        # 快速统计总文件数（用于进度显示）
        console.print("📊 正在统计项目文件...", end="")
        total_files = 0
        for root, dirs, files in os.walk(project_root):
            dirs[:] = filter_walk_dirs(dirs)
            for file in files:
                file_path = os.path.join(root, file)
                language = detect_language(file_path)
                if language and get_symbol_extractor(language):
                    total_files += 1
        console.print(" 完成")  # 统计完成，换行

        # 进度反馈间隔（每处理这么多文件输出一次，最多每10个文件输出一次）
        # progress_interval = max(1, min(total_files // 20, 10)) if total_files > 0 else 10

        if total_files > 0:
            console.print(f"📁 发现 {total_files} 个代码文件，开始扫描...")
        else:
            console.print("⚠️  未发现可扫描的代码文件", style="yellow")
            return

        # 辅助函数：生成固定宽度的进度字符串（避免残留字符）
        def format_progress_msg(
            current_file: str, scanned: int, total: int, symbols: int, skipped: int
        ) -> str:
            progress_pct = (scanned * 100) // total if total > 0 else 0
            base_msg = f"⏳ 扫描进度: {scanned}/{total} ({progress_pct}%)"
            if symbols > 0:
                base_msg += f"，已提取 {symbols} 个符号"
            if skipped > 0:
                base_msg += f"，跳过 {skipped}"
            base_msg += f" | {current_file}"
            # 填充空格到固定宽度，清除旧内容
            if len(base_msg) < max_line_width:
                base_msg += " " * (max_line_width - len(base_msg))
            return base_msg

        # 遍历项目目录
        for root, dirs, files in os.walk(project_root):
            # 过滤需要忽略的目录
            dirs[:] = filter_walk_dirs(dirs)

            for file in files:
                file_path = os.path.join(root, file)

                # 检测语言
                language = detect_language(file_path)
                if not language:
                    continue

                # 获取符号提取器
                extractor = get_symbol_extractor(language)
                if not extractor:
                    continue

                # 获取相对路径用于显示（限制长度）
                try:
                    rel_path = os.path.relpath(file_path, project_root)
                    # 如果路径太长，只显示文件名
                    if len(rel_path) > 40:
                        rel_path = "..." + rel_path[-37:]
                except Exception:
                    rel_path = file

                # 读取文件内容（跳过超大文件，避免内存问题）
                try:
                    # 检查文件大小（超过 1MB 的文件跳过）
                    file_size = os.path.getsize(file_path)
                    if file_size > 1024 * 1024:  # 1MB
                        files_skipped += 1
                        # 实时更新进度（不换行，文件名在最后）
                        msg = format_progress_msg(
                            rel_path,
                            files_scanned,
                            total_files,
                            symbols_added,
                            files_skipped,
                        )
                        console.print(msg, end="\r")
                        continue

                    # 显示当前正在扫描的文件
                    msg = format_progress_msg(
                        rel_path,
                        files_scanned,
                        total_files,
                        symbols_added,
                        files_skipped,
                    )
                    console.print(msg, end="\r")

                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    if not content:
                        continue

                    # 提取符号
                    symbols = extractor.extract_symbols(file_path, content)
                    if symbols:
                        files_with_symbols += 1
                    for symbol in symbols:
                        # 不立即保存缓存，批量添加以提高性能
                        self.context_manager.symbol_table.add_symbol(
                            symbol, save_to_cache=False
                        )
                        symbols_added += 1

                    # 更新文件修改时间
                    try:
                        self.context_manager.symbol_table._file_mtimes[file_path] = (
                            os.path.getmtime(file_path)
                        )
                    except Exception:
                        pass

                    files_scanned += 1

                    # 实时更新进度（不换行，文件名在最后）
                    msg = format_progress_msg(
                        rel_path,
                        files_scanned,
                        total_files,
                        symbols_added,
                        files_skipped,
                    )
                    console.print(msg, end="\r")
                except Exception:
                    # 跳过无法读取的文件
                    files_skipped += 1
                    # 实时更新进度（不换行，文件名在最后）
                    msg = format_progress_msg(
                        rel_path,
                        files_scanned,
                        total_files,
                        symbols_added,
                        files_skipped,
                    )
                    console.print(msg, end="\r")
                    continue

        # 完成时显示100%进度，然后换行并显示最终结果
        if total_files > 0:
            # 清除进度行
            console.print(" " * max_line_width, end="\r")
        console.print()  # 换行

        # 批量保存缓存（扫描完成后一次性保存，提高性能）
        try:
            console.print("💾 正在保存符号表缓存...", end="\r")
            self.context_manager.symbol_table.save_cache()
            console.print("💾 符号表缓存已保存")
        except Exception as e:
            console.print(f"⚠️  保存符号表缓存失败: {e}", style="yellow")

        skip_msg = f"，跳过 {files_skipped} 个文件" if files_skipped > 0 else ""
        console.print(
            f"✅ 符号表构建完成: 扫描 {files_scanned} 个文件{skip_msg}，提取 {symbols_added} 个符号（来自 {files_with_symbols} 个文件）",
            style="green",
        )

    def _extract_keywords_with_llm(self, user_input: str) -> List[str]:
        """使用LLM生成相关关键词

        Args:
            user_input: 用户输入

        Returns:
            关键词列表（用于模糊匹配符号名）
        """
        # 获取项目概况和符号表信息
        project_overview = self._get_project_overview()

        # 获取所有可用的符号名（用于参考）
        all_symbol_names = list(
            self.context_manager.symbol_table.symbols_by_name.keys()
        )
        symbol_names_sample = sorted(all_symbol_names)[:50]  # 取前50个作为示例

        prompt = f"""分析代码编辑任务，生成5-15个搜索关键词，用于在代码库中查找相关符号。

{project_overview}

任务描述：{user_input}

现有符号名示例：{", ".join(symbol_names_sample[:30])}{"..." if len(symbol_names_sample) > 30 else ""}

要求：
1. 关键词应该是符号名中可能包含的单词或词根（如 "user", "login", "validate", "config"）
2. 不需要完整的符号名，只需要关键词片段
3. 关键词应与任务直接相关
4. 可以是单词、缩写或常见的命名片段

以Jsonnet数组格式返回，用<KEYWORDS>标签包裹。示例：
<KEYWORDS>
["user", "login", "auth", "validate", "session"]
</KEYWORDS>
"""

        try:
            response = self._call_llm(prompt)
            # 从<KEYWORDS>标签中提取内容
            response = response.strip()
            json_match = re.search(
                r"<KEYWORDS>\s*(.*?)\s*</KEYWORDS>", response, re.DOTALL
            )
            if json_match:
                json_content = json_match.group(1).strip()
            else:
                # 如果没有找到标签，尝试清理markdown代码块
                if response.startswith("```json"):
                    response = response[7:]
                elif response.startswith("```"):
                    response = response[3:]
                if response.endswith("```"):
                    response = response[:-3]
                json_content = response.strip()

            keywords = json_loads(json_content)
            if not isinstance(keywords, list):
                return []

            # 过滤空字符串和过短的关键词（至少2个字符）
            keywords = [
                kw.strip().lower()
                for kw in keywords
                if kw and isinstance(kw, str) and len(kw.strip()) >= 2
            ]
            return keywords
        except Exception:
            # 解析失败，返回空列表
            return []

    def _search_symbols_by_keywords(self, keywords: List[str]) -> List[Symbol]:
        """基于关键词在符号表中模糊查找相关符号

        Args:
            keywords: 关键词列表（用于模糊匹配符号名）

        Returns:
            候选符号列表
        """
        if not keywords:
            return []

        found_symbols: List[Symbol] = []
        found_symbol_keys: set[tuple[str, str, int]] = set()  # 用于去重

        # 将关键词转为小写用于匹配
        keywords_lower = [kw.lower() for kw in keywords]

        # 遍历所有符号，模糊匹配符号名
        for (
            symbol_name,
            symbols,
        ) in self.context_manager.symbol_table.symbols_by_name.items():
            symbol_name_lower = symbol_name.lower()

            # 模糊匹配：检查任一关键词是否是符号名的子串（大小写不敏感）
            if any(kw in symbol_name_lower for kw in keywords_lower):
                # 找到匹配的符号，添加所有同名符号（可能有重载）
                for symbol in symbols:
                    key = (symbol.file_path, symbol.name, symbol.line_start)
                    if key not in found_symbol_keys:
                        found_symbols.append(symbol)
                        found_symbol_keys.add(key)

        return found_symbols

    def _select_relevant_symbols_with_llm(
        self, user_input: str, keywords: List[str], candidate_symbols: List[Symbol]
    ) -> List[Symbol]:
        """使用LLM从候选符号中挑选关联度高的条目

        Args:
            user_input: 用户输入/任务描述
            keywords: 搜索关键词列表
            candidate_symbols: 候选符号列表（包含位置信息）

        Returns:
            选中的符号列表
        """
        if not candidate_symbols:
            return []

        # 限制候选符号数量，避免prompt过长
        candidates_to_consider = candidate_symbols[:100]  # 最多100个候选

        # 构建带编号的符号信息列表（包含位置信息）
        symbol_info_list = []
        for idx, symbol in enumerate(candidates_to_consider, start=1):
            symbol_info = {
                "序号": idx,
                "name": symbol.name,
                "kind": symbol.kind,
                "file": os.path.relpath(
                    symbol.file_path, self.context_manager.project_root
                ),
                "line": symbol.line_start,
                "signature": symbol.signature or "",
            }
            symbol_info_list.append(symbol_info)

        # 获取项目概况
        project_overview = self._get_project_overview()

        prompt = f"""根据任务描述和搜索关键词，从候选符号列表中选择最相关的10-20个符号。

{project_overview}

任务描述：{user_input}
搜索关键词：{", ".join(keywords)}
候选符号列表（已编号）：{json.dumps(symbol_info_list, ensure_ascii=False, indent=2)}

返回最相关符号的序号（Jsonnet数组），按相关性排序，用<SELECTED_INDICES>标签包裹。示例：
<SELECTED_INDICES>
[3, 7, 12, 15, 23]
</SELECTED_INDICES>
"""

        try:
            response = self._call_llm(prompt)
            # 从<SELECTED_INDICES>标签中提取内容
            response = response.strip()
            json_match = re.search(
                r"<SELECTED_INDICES>\s*(.*?)\s*</SELECTED_INDICES>", response, re.DOTALL
            )
            if json_match:
                json_content = json_match.group(1).strip()
            else:
                # 如果没有找到标签，尝试清理markdown代码块
                if response.startswith("```json"):
                    response = response[7:]
                elif response.startswith("```"):
                    response = response[3:]
                if response.endswith("```"):
                    response = response[:-3]
                json_content = response.strip()

            selected_indices = json_loads(json_content)
            if not isinstance(selected_indices, list):
                return []

            # 根据序号查找对应的符号对象
            selected_symbols = []
            invalid_indices = []
            for idx in selected_indices:
                # 序号从1开始，转换为列表索引（从0开始）
                if isinstance(idx, int) and 1 <= idx <= len(candidates_to_consider):
                    symbol = candidates_to_consider[idx - 1]
                    selected_symbols.append(symbol)
                else:
                    invalid_indices.append(idx)

            return selected_symbols
        except Exception:
            # 解析失败，返回空列表
            return []

    def _create_llm_model(self) -> BasePlatform:
        """创建新的 LLM 模型实例

        每次调用都创建新的实例，避免上下文窗口累积。

        Returns:
            LLM 模型实例

        Raises:
            ValueError: 如果无法创建LLM模型
        """
        try:
            registry = PlatformRegistry.get_global_platform_registry()

            # 创建平台实例（筛选操作始终使用cheap平台以降低成本）
            # 如果没有指定平台，直接使用 get_cheap_platform
            # 如果指定了平台，也直接使用 get_cheap_platform（因为筛选操作应该使用cheap平台）
            # 这样可以避免先调用 create_platform 再回退导致的重复错误信息
            llm_model = registry.get_cheap_platform(self._model_group)

            if not llm_model:
                raise ValueError("无法创建LLM模型实例")

            # 先设置模型组（如果从父Agent获取到），因为 model_group 可能会影响模型名称的解析
            if self._model_group:
                try:
                    llm_model.set_model_group(self._model_group)
                except Exception:
                    pass

            # 然后设置模型名称（如果从父Agent或model_group获取到）
            if self._model_name:
                try:
                    llm_model.set_model_name(self._model_name)
                except Exception:
                    pass

            # 设置抑制输出，因为这是后台任务
            llm_model.set_suppress_output(True)

            return llm_model
        except Exception as e:
            raise ValueError(f"无法创建LLM模型: {e}")

    def _call_llm(self, prompt: str) -> str:
        """调用LLM生成响应

        每次调用都创建新的 LLM 实例，避免上下文窗口累积。

        Args:
            prompt: 提示词

        Returns:
            LLM生成的响应文本
        """
        # 每次调用都创建新的 LLM 实例，避免上下文窗口累积
        llm_model = self._create_llm_model()

        try:
            # 使用chat_until_success方法（BasePlatform的标准接口）
            if hasattr(llm_model, "chat_until_success"):
                response = llm_model.chat_until_success(prompt)
                response_str = str(response)
                return response_str
            else:
                # 如果不支持chat_until_success，抛出异常
                raise ValueError(
                    "LLM model does not support chat_until_success interface"
                )
        except Exception:
            raise

    def format_recommendation(self, recommendation: ContextRecommendation) -> str:
        """格式化推荐结果为可读文本

        Args:
            recommendation: 推荐结果

        Returns:
            格式化的文本
        """
        return ""
