"""智能上下文推荐器。

使用LLM进行语义理解，提供更准确的上下文推荐。
完全基于LLM实现，不依赖硬编码规则。
"""


import os
import re
import yaml
from typing import List, Optional, Dict, Any, Set

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
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
                    platform_name = parent_model.platform_name()
                    model_name = parent_model.name()
                    model_group = getattr(parent_model, 'model_group', None)
                except Exception:
                    # 如果获取失败，使用默认配置
                    pass
            
            # 创建平台实例
            if platform_name:
                self.llm_model = registry.create_platform(platform_name)
                if self.llm_model is None:
                    # 如果创建失败，使用默认平台
                    self.llm_model = registry.get_normal_platform()
            else:
                self.llm_model = registry.get_normal_platform()
            
            # 设置模型名称（如果从父Agent获取到）
            if model_name and self.llm_model:
                try:
                    self.llm_model.set_model_name(model_name)
                except Exception:
                    pass
            
            # 设置模型组（如果从父Agent获取到）
            if model_group and self.llm_model:
                try:
                    self.llm_model.set_model_group(model_group)
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
        # 1. 使用LLM提取关键词（仅提取关键词）
        keywords = self._extract_keywords_with_llm(user_input)
        
        # 2. 初始化推荐结果
        recommended_symbols: List[Symbol] = []

        # 3. 基于关键词进行符号查找和文本查找，然后使用LLM挑选关联度高的条目（主要推荐方式）
        if keywords:
            # 3.1 使用关键词进行符号查找和文本查找，找到所有候选符号及其位置
            candidate_symbols = self._search_symbols_by_keywords(keywords)
            candidate_symbols_from_text = self._search_text_by_keywords(keywords)
            
            # 合并候选符号（去重）
            all_candidates = {}
            for symbol in candidate_symbols + candidate_symbols_from_text:
                # 使用 (file_path, name, line_start) 作为唯一键
                key = (symbol.file_path, symbol.name, symbol.line_start)
                if key not in all_candidates:
                    all_candidates[key] = symbol
            
            candidate_symbols_list = list(all_candidates.values())
            
            # 3.2 使用LLM从候选符号中挑选关联度高的条目
            if candidate_symbols_list:
                selected_symbols = self._select_relevant_symbols_with_llm(
                    user_input, keywords, candidate_symbols_list
                )
                recommended_symbols.extend(selected_symbols)

        # 4. 限制符号数量
        final_symbols = recommended_symbols[:10]

        return ContextRecommendation(
            recommended_symbols=final_symbols,
        )

    def _get_project_overview(self) -> str:
        """获取项目概况信息
        
        Returns:
            项目概况字符串
        """
        return get_project_overview(self.context_manager.project_root)

    def _extract_keywords_with_llm(self, user_input: str) -> List[str]:
        """使用LLM提取关键词（仅提取关键词）
        
        Args:
            user_input: 用户输入
            
        Returns:
            关键词列表
        """
        # 获取项目概况
        project_overview = self._get_project_overview()
        
        prompt = f"""分析以下代码编辑任务，提取关键词。关键词应该是与任务相关的核心概念、技术术语、功能模块等。

{project_overview}

任务描述：
{user_input}

请提取5-10个关键词，以YAML数组格式返回，并用<KEYWORDS>标签包裹。
只返回关键词数组，不要包含其他文字。

示例格式：
<KEYWORDS>
- data processing
- validation
- error handling
- API endpoint
- authentication
</KEYWORDS>
"""

        try:
            response = self._call_llm(prompt)
            # 从<KEYWORDS>标签中提取内容
            response = response.strip()
            yaml_match = re.search(r'<KEYWORDS>\s*(.*?)\s*</KEYWORDS>', response, re.DOTALL)
            if yaml_match:
                yaml_content = yaml_match.group(1).strip()
            else:
                # 如果没有找到标签，尝试清理markdown代码块
                if response.startswith("```yaml"):
                    response = response[7:]
                elif response.startswith("```"):
                    response = response[3:]
                if response.endswith("```"):
                    response = response[:-3]
                yaml_content = response.strip()
            
            keywords = yaml.safe_load(yaml_content)
            if not isinstance(keywords, list):
                return []
            
            # 过滤空字符串和过短的关键词
            keywords = [k.strip() for k in keywords if k and isinstance(k, str) and len(k.strip()) > 1]
            return keywords
        except Exception as e:
            # 解析失败，返回空列表
            PrettyOutput.print(f"LLM关键词提取失败: {e}", OutputType.WARNING)
            return []

    def _search_symbols_by_keywords(self, keywords: List[str]) -> List[Symbol]:
        """基于关键词在符号表中查找相关符号
        
        Args:
            keywords: 关键词列表
            
        Returns:
            候选符号列表
        """
        if not keywords:
            return []
        
        found_symbols: List[Symbol] = []
        keywords_lower = [k.lower() for k in keywords]
        found_symbol_keys = set()  # 用于去重，使用 (file_path, name, line_start) 作为键
        
        # 遍历所有符号，查找名称或签名中包含关键词的符号
        for symbol_name, symbols in self.context_manager.symbol_table.symbols_by_name.items():
            symbol_name_lower = symbol_name.lower()
            
            # 检查符号名称是否包含任何关键词
            name_matched = False
            for keyword in keywords_lower:
                if keyword in symbol_name_lower:
                    # 找到匹配的符号，添加所有同名符号（可能有重载）
                    for symbol in symbols:
                        key = (symbol.file_path, symbol.name, symbol.line_start)
                        if key not in found_symbol_keys:
                            found_symbols.append(symbol)
                            found_symbol_keys.add(key)
                    name_matched = True
                    break
            
            # 如果名称不匹配，检查符号签名是否包含关键词
            if not name_matched:
                for symbol in symbols:
                    if symbol.signature:
                        signature_lower = symbol.signature.lower()
                        for keyword in keywords_lower:
                            if keyword in signature_lower:
                                key = (symbol.file_path, symbol.name, symbol.line_start)
                                if key not in found_symbol_keys:
                                    found_symbols.append(symbol)
                                    found_symbol_keys.add(key)
                                break
        
        return found_symbols

    def _search_text_by_keywords(self, keywords: List[str]) -> List[Symbol]:
        """基于关键词在文件内容中进行文本查找，找到相关符号
        
        Args:
            keywords: 关键词列表
            
        Returns:
            候选符号列表（在包含关键词的文件中找到的符号）
        """
        if not keywords:
            return []
        
        found_symbols: List[Symbol] = []
        keywords_lower = [k.lower() for k in keywords]
        
        # 获取所有已分析的文件
        all_files = set()
        for symbol_name, symbols in self.context_manager.symbol_table.symbols_by_name.items():
            for symbol in symbols:
                all_files.add(symbol.file_path)
        
        # 在文件内容中搜索关键词
        for file_path in all_files:
            content = self.context_manager._get_file_content(file_path)
            if not content:
                continue
            
            content_lower = content.lower()
            
            # 检查文件内容是否包含任何关键词
            file_matches = False
            for keyword in keywords_lower:
                if keyword in content_lower:
                    file_matches = True
                    break
            
            if file_matches:
                # 获取该文件中的所有符号
                file_symbols = self.context_manager.symbol_table.get_file_symbols(file_path)
                found_symbols.extend(file_symbols)
        
        return found_symbols

    def _select_relevant_symbols_with_llm(
        self, user_input: str, keywords: List[str], candidate_symbols: List[Symbol]
    ) -> List[Symbol]:
        """使用LLM从候选符号中挑选关联度高的条目
        
        Args:
            user_input: 用户输入/任务描述
            keywords: 关键词列表
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
                "file": os.path.relpath(symbol.file_path, self.context_manager.project_root),
                "line": symbol.line_start,
                "signature": symbol.signature or "",
            }
            symbol_info_list.append(symbol_info)
        
        # 获取项目概况
        project_overview = self._get_project_overview()
        
        prompt = f"""根据以下任务描述和关键词，从候选符号列表中选择最相关的符号。

{project_overview}

任务描述：{user_input}
关键词：{', '.join(keywords)}

候选符号列表（已编号，包含位置信息）：
{yaml.dump(symbol_info_list, allow_unicode=True, default_flow_style=False)}

请返回最相关的10-20个符号的序号（YAML数组格式），按相关性排序，并用<SELECTED_INDICES>标签包裹。

只返回序号数组，例如：
<SELECTED_INDICES>
- 3
- 7
- 12
- 15
- 23
</SELECTED_INDICES>
"""

        try:
            response = self._call_llm(prompt)
            # 从<SELECTED_INDICES>标签中提取内容
            response = response.strip()
            yaml_match = re.search(r'<SELECTED_INDICES>\s*(.*?)\s*</SELECTED_INDICES>', response, re.DOTALL)
            if yaml_match:
                yaml_content = yaml_match.group(1).strip()
            else:
                # 如果没有找到标签，尝试清理markdown代码块
                if response.startswith("```yaml"):
                    response = response[7:]
                elif response.startswith("```"):
                    response = response[3:]
                if response.endswith("```"):
                    response = response[:-3]
                yaml_content = response.strip()
            
            selected_indices = yaml.safe_load(yaml_content)
            if not isinstance(selected_indices, list):
                return []
            
            # 根据序号查找对应的符号对象
            selected_symbols = []
            for idx in selected_indices:
                # 序号从1开始，转换为列表索引（从0开始）
                if isinstance(idx, int) and 1 <= idx <= len(candidates_to_consider):
                    symbol = candidates_to_consider[idx - 1]
                    selected_symbols.append(symbol)
            
            return selected_symbols
        except Exception as e:
            # 解析失败，返回空列表
            PrettyOutput.print(f"LLM符号筛选失败: {e}", OutputType.WARNING)
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
                return str(response)
            else:
                # 如果不支持chat_until_success，抛出异常
                raise ValueError("LLM model does not support chat_until_success interface")
        except Exception as e:
            PrettyOutput.print(f"LLM调用失败: {e}", OutputType.WARNING)
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
