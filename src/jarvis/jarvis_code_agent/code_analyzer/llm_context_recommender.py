"""智能上下文推荐器。

使用LLM进行语义理解，提供更准确的上下文推荐。
完全基于LLM实现，不依赖硬编码规则。
"""


import json5 as json
import os
import re
from typing import List, Optional, Any

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.config import get_normal_platform_name, get_normal_model_name
from jarvis.jarvis_code_agent.utils import get_project_overview

from .context_recommender import ContextRecommendation
from .context_manager import ContextManager
from .symbol_extractor import Symbol


class ContextRecommender:
    """智能上下文推荐器。
    
    使用LLM进行语义理解，根据编辑意图推荐相关的上下文信息。
    完全基于LLM实现，提供语义级别的推荐，而非简单的关键词匹配。
    """

    def __init__(self, context_manager: ContextManager, parent_model: Optional[Any] = None):
        """初始化上下文推荐器
        
        Args:
            context_manager: 上下文管理器
            parent_model: 父Agent的模型实例，用于获取模型配置（平台名称、模型名称、模型组等）
            
        Raises:
            ValueError: 如果无法创建LLM模型
        """
        self.context_manager = context_manager
        
        # 自己创建LLM模型实例，使用父Agent的配置
        try:
            registry = PlatformRegistry.get_global_platform_registry()
            
            # 从父Agent的model获取配置
            platform_name = None
            model_name = None
            model_group = None
            
            if parent_model:
                try:
                    # 优先获取 model_group，因为它包含了完整的配置信息
                    model_group = getattr(parent_model, 'model_group', None)
                    platform_name = parent_model.platform_name()
                    model_name = parent_model.name()
                except Exception:
                    # 如果获取失败，使用默认配置
                    pass
            
            # 优先根据 model_group 获取配置（确保配置一致性）
            # 如果 model_group 存在，强制使用它来解析，避免使用 parent_model 中可能不一致的值
            if model_group:
                try:
                    platform_name = get_normal_platform_name(model_group)
                    model_name = get_normal_model_name(model_group)
                except Exception:
                    # 如果从 model_group 解析失败，回退到从 parent_model 获取的值
                    pass
            
            # 创建平台实例
            if platform_name:
                self.llm_model = registry.create_platform(platform_name)
                if self.llm_model is None:
                    # 如果创建失败，使用默认平台
                    self.llm_model = registry.get_normal_platform()
            else:
                self.llm_model = registry.get_normal_platform()
            
            # 先设置模型组（如果从父Agent获取到），因为 model_group 可能会影响模型名称的解析
            if model_group and self.llm_model:
                try:
                    self.llm_model.set_model_group(model_group)
                except Exception:
                    pass
            
            # 然后设置模型名称（如果从父Agent或model_group获取到）
            if model_name and self.llm_model:
                try:
                    self.llm_model.set_model_name(model_name)
                except Exception:
                    pass
            
            # 设置抑制输出，因为这是后台任务
            if self.llm_model:
                self.llm_model.set_suppress_output(True)
            else:
                raise ValueError("无法创建LLM模型实例")
        except Exception as e:
            raise ValueError(f"无法创建LLM模型: {e}")

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
        PrettyOutput.print("🔍 开始智能上下文推荐分析...", OutputType.INFO)
        
        # 0. 检查并填充符号表（如果为空）
        self._ensure_symbol_table_loaded()
        
        # 1. 使用LLM生成相关符号名
        PrettyOutput.print("📝 正在使用LLM生成相关符号名...", OutputType.INFO)
        symbol_names = self._extract_symbol_names_with_llm(user_input)
        if symbol_names:
            PrettyOutput.print(f"✅ 生成 {len(symbol_names)} 个符号名: {', '.join(symbol_names[:5])}{'...' if len(symbol_names) > 5 else ''}", OutputType.SUCCESS)
        else:
            PrettyOutput.print("⚠️  未能生成符号名，将使用基础搜索策略", OutputType.WARNING)
        
        # 2. 初始化推荐结果
        recommended_symbols: List[Symbol] = []

        # 3. 基于符号名进行符号查找，然后使用LLM挑选关联度高的条目（主要推荐方式）
        if symbol_names:
            # 3.1 使用符号名进行精确查找，找到所有候选符号及其位置
            PrettyOutput.print("🔎 正在基于符号名搜索相关符号...", OutputType.INFO)
            candidate_symbols = self._search_symbols_by_names(symbol_names)
            
            PrettyOutput.print(f"📊 符号名匹配: {len(candidate_symbols)} 个候选", OutputType.INFO)
            
            candidate_symbols_list = candidate_symbols
            PrettyOutput.print(f"📦 共 {len(candidate_symbols_list)} 个候选符号", OutputType.INFO)
            
            # 3.2 使用LLM从候选符号中挑选关联度高的条目
            if candidate_symbols_list:
                PrettyOutput.print(f"🤖 正在使用LLM从 {len(candidate_symbols_list)} 个候选符号中筛选最相关的条目...", OutputType.INFO)
                selected_symbols = self._select_relevant_symbols_with_llm(
                    user_input, symbol_names, candidate_symbols_list
                )
                recommended_symbols.extend(selected_symbols)
                PrettyOutput.print(f"✅ LLM筛选完成，选中 {len(selected_symbols)} 个相关符号", OutputType.SUCCESS)
            else:
                PrettyOutput.print("⚠️  没有找到候选符号", OutputType.WARNING)
        else:
            PrettyOutput.print("⚠️  无符号名可用，跳过符号推荐", OutputType.WARNING)

        # 4. 限制符号数量
        final_symbols = recommended_symbols[:10]
        if len(recommended_symbols) > 10:
            PrettyOutput.print(f"📌 推荐结果已限制为前 10 个符号（共 {len(recommended_symbols)} 个）", OutputType.INFO)

        PrettyOutput.print(f"✨ 上下文推荐完成，共推荐 {len(final_symbols)} 个符号", OutputType.SUCCESS)

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
            PrettyOutput.print("📚 符号表为空，开始扫描项目文件构建符号表...", OutputType.INFO)
            self._build_symbol_table()
        else:
            symbol_count = sum(len(symbols) for symbols in self.context_manager.symbol_table.symbols_by_name.values())
            PrettyOutput.print(f"📚 符号表已就绪，包含 {symbol_count} 个符号", OutputType.INFO)

    def _build_symbol_table(self) -> None:
        """扫描项目文件并构建符号表
        
        遍历项目目录，提取所有支持语言的符号。
        """
        import os
        from .language_support import detect_language, get_symbol_extractor
        from .file_ignore import filter_walk_dirs
        
        project_root = self.context_manager.project_root
        files_scanned = 0
        symbols_added = 0
        files_with_symbols = 0
        
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
                
                # 读取文件内容
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    if not content:
                        continue
                    
                    # 提取符号
                    symbols = extractor.extract_symbols(file_path, content)
                    if symbols:
                        files_with_symbols += 1
                    for symbol in symbols:
                        self.context_manager.symbol_table.add_symbol(symbol)
                        symbols_added += 1
                    
                    files_scanned += 1
                except Exception:
                    # 跳过无法读取的文件
                    continue
        
        PrettyOutput.print(f"✅ 符号表构建完成: 扫描 {files_scanned} 个文件，提取 {symbols_added} 个符号（来自 {files_with_symbols} 个文件）", OutputType.SUCCESS)

    def _extract_symbol_names_with_llm(self, user_input: str) -> List[str]:
        """使用LLM生成相关符号名
        
        Args:
            user_input: 用户输入
            
        Returns:
            符号名列表
        """
        # 获取项目概况和符号表信息
        project_overview = self._get_project_overview()
        
        # 获取所有可用的符号名（用于参考）
        all_symbol_names = list(self.context_manager.symbol_table.symbols_by_name.keys())
        symbol_names_sample = sorted(all_symbol_names)[:50]  # 取前50个作为示例
        
        prompt = f"""分析以下代码编辑任务，生成可能相关的符号名（函数名、类名、变量名等）。

{project_overview}

任务描述：
{user_input}

项目中的部分符号名示例（仅供参考）：
{', '.join(symbol_names_sample[:30])}{'...' if len(symbol_names_sample) > 30 else ''}

请根据任务描述，生成5-15个可能相关的符号名。符号名应该是：
1. 与任务直接相关的函数、类、变量等的名称
2. 符合常见命名规范（如驼峰命名、下划线命名等）
3. 尽量具体，避免过于通用的名称

以 JSON5 数组格式返回，并用<SYMBOL_NAMES>标签包裹。
只返回符号名数组，不要包含其他文字。

JSON5 格式说明：
- 可以使用双引号 "..." 或单引号 '...' 包裹字符串
- 支持尾随逗号
- 数组格式示例：["item1", "item2", "item3"] 或 ['item1', 'item2', 'item3',]

示例格式：
<SYMBOL_NAMES>
["processData", "validateInput", "handleError", "createApiEndpoint", "authenticateUser"]
</SYMBOL_NAMES>
"""

        try:
            response = self._call_llm(prompt)
            # 从<SYMBOL_NAMES>标签中提取内容
            response = response.strip()
            json_match = re.search(r'<SYMBOL_NAMES>\s*(.*?)\s*</SYMBOL_NAMES>', response, re.DOTALL)
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
            
            symbol_names = json.loads(json_content)
            if not isinstance(symbol_names, list):
                PrettyOutput.print("⚠️  LLM返回的符号名格式不正确，期望 JSON5 数组格式", OutputType.WARNING)
                return []
            
            # 过滤空字符串和过短的符号名
            original_count = len(symbol_names)
            symbol_names = [name.strip() for name in symbol_names if name and isinstance(name, str) and len(name.strip()) > 0]
            if original_count != len(symbol_names):
                PrettyOutput.print(f"📋 过滤后保留 {len(symbol_names)} 个有效符号名（原始 {original_count} 个）", OutputType.INFO)
            return symbol_names
        except Exception as e:
            # 解析失败，返回空列表
            PrettyOutput.print(f"❌ LLM符号名生成失败: {e}", OutputType.WARNING)
            return []

    def _search_symbols_by_names(self, symbol_names: List[str]) -> List[Symbol]:
        """基于符号名在符号表中精确查找相关符号
        
        Args:
            symbol_names: 符号名列表
            
        Returns:
            候选符号列表
        """
        if not symbol_names:
            return []
        
        found_symbols: List[Symbol] = []
        found_symbol_keys = set()  # 用于去重，使用 (file_path, name, line_start) 作为键
        
        # 创建符号名映射（支持大小写不敏感匹配）
        symbol_names_lower = {name.lower(): name for name in symbol_names}
        
        # 遍历所有符号，精确匹配符号名
        for symbol_name, symbols in self.context_manager.symbol_table.symbols_by_name.items():
            symbol_name_lower = symbol_name.lower()
            
            # 精确匹配：检查符号名是否在目标列表中（大小写不敏感）
            if symbol_name_lower in symbol_names_lower:
                # 找到匹配的符号，添加所有同名符号（可能有重载）
                for symbol in symbols:
                    key = (symbol.file_path, symbol.name, symbol.line_start)
                    if key not in found_symbol_keys:
                        found_symbols.append(symbol)
                        found_symbol_keys.add(key)
        
        return found_symbols

    def _select_relevant_symbols_with_llm(
        self, user_input: str, symbol_names: List[str], candidate_symbols: List[Symbol]
    ) -> List[Symbol]:
        """使用LLM从候选符号中挑选关联度高的条目
        
        Args:
            user_input: 用户输入/任务描述
            symbol_names: 符号名列表
            candidate_symbols: 候选符号列表（包含位置信息）
            
        Returns:
            选中的符号列表
        """
        if not candidate_symbols:
            return []
        
        # 限制候选符号数量，避免prompt过长
        candidates_to_consider = candidate_symbols[:100]  # 最多100个候选
        if len(candidate_symbols) > 100:
            PrettyOutput.print(f"📌 候选符号数量较多（{len(candidate_symbols)} 个），限制为前 100 个进行LLM筛选", OutputType.INFO)
        
        # 构建带编号的符号信息列表（包含位置信息）
        symbol_info_list = []
        for idx, symbol in enumerate(candidates_to_consider, start=1):
            symbol_info = {
                "序号": idx,
                "name": symbol.name,
                "kind": symbol.kind,
                "file": os.path.relpath(symbol.file_path, self.context_manager.project_root),
                "line": symbol.line_start,
                "signature": symbol.signature or "",
            }
            symbol_info_list.append(symbol_info)
        
        # 获取项目概况
        project_overview = self._get_project_overview()
        
        prompt = f"""根据以下任务描述和生成的符号名，从候选符号列表中选择最相关的符号。

{project_overview}

任务描述：{user_input}
生成的符号名：{', '.join(symbol_names)}

候选符号列表（已编号，包含位置信息）：
{json.dumps(symbol_info_list, ensure_ascii=False, indent=2)}

请返回最相关的10-20个符号的序号（JSON5 数组格式），按相关性排序，并用<SELECTED_INDICES>标签包裹。

JSON5 格式说明：
- 数组格式示例：[1, 2, 3] 或 [1, 2, 3,]
- 支持尾随逗号

只返回序号数组，例如：
<SELECTED_INDICES>
[3, 7, 12, 15, 23]
</SELECTED_INDICES>
"""

        try:
            response = self._call_llm(prompt)
            # 从<SELECTED_INDICES>标签中提取内容
            response = response.strip()
            json_match = re.search(r'<SELECTED_INDICES>\s*(.*?)\s*</SELECTED_INDICES>', response, re.DOTALL)
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
            
            selected_indices = json.loads(json_content)
            if not isinstance(selected_indices, list):
                PrettyOutput.print("⚠️  LLM返回的符号序号格式不正确，期望 JSON5 数组格式", OutputType.WARNING)
                return []
            
            PrettyOutput.print(f"📋 LLM返回了 {len(selected_indices)} 个符号序号", OutputType.INFO)
            
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
            
            if invalid_indices:
                PrettyOutput.print(f"⚠️  发现 {len(invalid_indices)} 个无效序号: {invalid_indices[:5]}{'...' if len(invalid_indices) > 5 else ''}", OutputType.WARNING)
            
            if selected_symbols:
                # 统计选中的符号类型分布
                kind_count = {}
                for symbol in selected_symbols:
                    kind_count[symbol.kind] = kind_count.get(symbol.kind, 0) + 1
                kind_summary = ", ".join([f"{kind}: {count}" for kind, count in sorted(kind_count.items())])
                PrettyOutput.print(f"📊 选中符号类型分布: {kind_summary}", OutputType.INFO)
            
            return selected_symbols
        except Exception as e:
            # 解析失败，返回空列表
            PrettyOutput.print(f"❌ LLM符号筛选失败: {e}", OutputType.WARNING)
            return []

    def _call_llm(self, prompt: str) -> str:
        """调用LLM生成响应
        
        Args:
            prompt: 提示词
            
        Returns:
            LLM生成的响应文本
        """
        if not self.llm_model:
            raise ValueError("LLM model not available")
        
        try:
            # 使用chat_until_success方法（BasePlatform的标准接口）
            if hasattr(self.llm_model, 'chat_until_success'):
                response = self.llm_model.chat_until_success(prompt)
                response_str = str(response)
                if response_str:
                    response_length = len(response_str)
                    PrettyOutput.print(f"💬 LLM响应长度: {response_length} 字符", OutputType.INFO)
                return response_str
            else:
                # 如果不支持chat_until_success，抛出异常
                raise ValueError("LLM model does not support chat_until_success interface")
        except Exception as e:
            PrettyOutput.print(f"❌ LLM调用失败: {e}", OutputType.WARNING)
            raise

    def format_recommendation(self, recommendation: ContextRecommendation) -> str:
        """格式化推荐结果为可读文本
        
        Args:
            recommendation: 推荐结果
            
        Returns:
            格式化的文本
        """
        if not recommendation.recommended_symbols:
            return ""
        
        lines = ["\n💡 智能上下文推荐:"]
        lines.append("─" * 60)

        # 输出：符号在文件中的位置
        symbols_str = "\n   ".join(
            f"• 符号 `{s.name}` ({s.kind}) 位于文件 {os.path.relpath(s.file_path, self.context_manager.project_root)} 第 {s.line_start} 行"
            for s in recommendation.recommended_symbols
        )
        lines.append(f"🔗 推荐符号位置 ({len(recommendation.recommended_symbols)}个):\n   {symbols_str}")

        lines.append("─" * 60)
        lines.append("")  # 空行

        return "\n".join(lines)
