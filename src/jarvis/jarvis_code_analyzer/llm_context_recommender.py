"""智能上下文推荐器。

使用LLM进行语义理解，提供更准确的上下文推荐。
完全基于LLM实现，不依赖硬编码规则。
"""

import json
import os
import re
import yaml
from typing import List, Optional, Dict, Any, Set

from jarvis.jarvis_utils.output import OutputType, PrettyOutput

from .context_recommender import ContextRecommendation
from .context_manager import ContextManager
from .symbol_extractor import Symbol


class ContextRecommender:
    """智能上下文推荐器。
    
    使用LLM进行语义理解，根据编辑意图推荐相关的上下文信息。
    完全基于LLM实现，提供语义级别的推荐，而非简单的关键词匹配。
    """

    def __init__(self, context_manager: ContextManager, llm_model: Any):
        """初始化上下文推荐器
        
        Args:
            context_manager: 上下文管理器
            llm_model: LLM模型实例（必需）
            
        Raises:
            ValueError: 如果未提供LLM模型
        """
        self.context_manager = context_manager
        self.llm_model = llm_model
        
        if not llm_model:
            raise ValueError("LLM model is required for context recommendation")

    def recommend_context(
        self,
        user_input: str,
        target_files: Optional[List[str]] = None,
        target_symbols: Optional[List[str]] = None,
    ) -> ContextRecommendation:
        """根据编辑意图推荐上下文
        
        Args:
            user_input: 用户输入/任务描述
            target_files: 目标文件列表（如果已知）
            target_symbols: 目标符号列表（如果已知）
            
        Returns:
            ContextRecommendation: 推荐的上下文信息
        """
        # 1. 使用LLM提取意图和实体
        extracted_info = self._extract_intent_with_llm(user_input)
        
        # 2. 合并提取的信息
        if extracted_info.get("target_files"):
            target_files = (target_files or []) + extracted_info["target_files"]
        if extracted_info.get("target_symbols"):
            target_symbols = (target_symbols or []) + extracted_info["target_symbols"]
        
        # 3. 基于目标文件推荐（依赖关系、测试文件等）
        recommended_files: Set[str] = set()
        recommended_symbols: List[Symbol] = []
        related_tests: Set[str] = set()
        reasons: List[str] = []
        
        if target_files:
            for file_path in target_files:
                # 推荐依赖的文件
                deps = self.context_manager.dependency_graph.get_dependencies(file_path)
                recommended_files.update(deps)
                if deps:
                    reasons.append(f"文件 {os.path.basename(file_path)} 的依赖文件")

                # 推荐依赖该文件的文件
                dependents = self.context_manager.dependency_graph.get_dependents(file_path)
                recommended_files.update(dependents)
                if dependents:
                    reasons.append(f"依赖文件 {os.path.basename(file_path)} 的文件")

                # 查找相关测试文件
                tests = self._find_test_files(file_path)
                related_tests.update(tests)
                if tests:
                    reasons.append(f"文件 {os.path.basename(file_path)} 的测试文件")

        # 4. 基于目标符号推荐
        if target_symbols:
            for symbol_name in target_symbols:
                # 查找符号定义
                symbol_def = self.context_manager.find_definition(symbol_name)
                if symbol_def:
                    recommended_symbols.append(symbol_def)
                    reasons.append(f"符号 {symbol_name} 的定义")

                # 查找符号引用
                references = self.context_manager.find_references(symbol_name)
                for ref in references[:5]:  # 限制引用数量
                    if ref.file_path not in recommended_files:
                        recommended_files.add(ref.file_path)
                if references:
                    reasons.append(f"符号 {symbol_name} 的引用位置")

        # 5. 使用LLM进行语义搜索
        semantic_symbols = self._semantic_search_symbols(
            user_input, extracted_info.get("keywords", [])
        )
        semantic_files = self._semantic_search_files(
            user_input, extracted_info.get("keywords", [])
        )
        
        recommended_files.update(semantic_files)
        recommended_symbols.extend(semantic_symbols)
        if semantic_symbols or semantic_files:
            reasons.append("LLM语义搜索")

        # 6. 使用LLM对推荐结果进行相关性评分和排序
        scored_files = self._score_files_with_llm(
            user_input,
            list(recommended_files),
        )
        scored_symbols = self._score_symbols_with_llm(
            user_input,
            recommended_symbols,
        )
        
        # 7. 过滤和排序
        final_files = [f for f, _ in sorted(scored_files.items(), key=lambda x: x[1], reverse=True)[:10]]
        final_symbols = [s for s, _ in sorted(scored_symbols.items(), key=lambda x: x[1], reverse=True)[:10]]
        
        # 8. 更新推荐原因
        reason = "；".join(reasons[:3]) if reasons else "基于LLM语义分析"
        if len(reasons) > 3:
            reason += f" 等{len(reasons)}个原因"
        if extracted_info.get("intent") != "unknown":
            reason = f"基于LLM语义分析（意图：{extracted_info['intent']}）；{reason}"

        return ContextRecommendation(
            recommended_files=final_files,
            recommended_symbols=final_symbols,
            related_tests=list(related_tests),
            reason=reason,
        )

    def _extract_intent_with_llm(self, user_input: str) -> Dict[str, Any]:
        """使用LLM提取用户意图和实体
        
        Args:
            user_input: 用户输入
            
        Returns:
            包含提取信息的字典
        """
        prompt = f"""分析以下代码编辑任务，提取关键信息。请以YAML格式返回结果，并用<INTENT>标签包裹。

任务描述：
{user_input}

请提取以下信息：
1. intent: 编辑意图（add_feature, fix_bug, refactor, modify, optimize, test, document等）
2. target_files: 目标文件路径列表（从任务描述中推断，如果明确提到文件）
3. target_symbols: 目标符号名称列表（函数名、类名、变量名等）
4. keywords: 关键概念列表（与任务相关的技术概念、功能模块等）
5. description: 任务的核心描述（一句话总结）

只返回YAML格式，用<INTENT>标签包裹，不要包含其他文字。如果某项信息无法确定，使用空数组或空字符串。

示例格式：
<INTENT>
intent: fix_bug
target_files:
  - src/main.py
target_symbols:
  - process_data
  - validate_input
keywords:
  - data processing
  - validation
  - error handling
description: 修复数据处理函数中的验证逻辑错误
</INTENT>
"""

        try:
            response = self._call_llm(prompt)
            # 尝试解析YAML响应
            # 从<INTENT>标签中提取内容
            response = response.strip()
            # 提取<INTENT>标签内的内容
            # 支持两种格式：<INTENT>...content...</INTENT> 或 <INTENT>...content...<INTENT>
            yaml_match = re.search(r'<INTENT>\s*(.*?)\s*(?:</INTENT>|<INTENT>)', response, re.DOTALL)
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
            
            extracted = yaml.safe_load(yaml_content)
            if extracted is None:
                extracted = {}
            return extracted
        except Exception as e:
            # 解析失败，返回空结果
            PrettyOutput.print(f"LLM意图提取失败: {e}", OutputType.WARNING)
            return {
                "intent": "unknown",
                "target_files": [],
                "target_symbols": [],
                "keywords": [],
                "description": "",
            }

    def _semantic_search_symbols(
        self, user_input: str, keywords: List[str]
    ) -> List[Symbol]:
        """使用LLM进行语义搜索，查找相关符号
        
        Args:
            user_input: 用户输入
            keywords: 关键词列表
            
        Returns:
            相关符号列表
        """
        if not keywords:
            return []
        
        # 获取所有符号的摘要信息
        all_symbols = []
        for symbol_name, symbols in self.context_manager.symbol_table.symbols_by_name.items():
            for symbol in symbols[:1]:  # 每个名称只取第一个
                all_symbols.append({
                    "name": symbol.name,
                    "kind": symbol.kind,
                    "file": os.path.basename(symbol.file_path),
                    "signature": symbol.signature or "",
                })
        
        if not all_symbols:
            return []
        
        # 限制符号数量，避免prompt过长
        symbols_sample = all_symbols[:50]  # 最多50个符号
        
        prompt = f"""根据以下任务描述和关键词，从符号列表中选择最相关的符号。

任务描述：{user_input}
关键词：{', '.join(keywords)}

符号列表：
{yaml.dump(symbols_sample, allow_unicode=True, default_flow_style=False)}

请返回最相关的5-10个符号名称（YAML数组格式），按相关性排序，并用<SYMBOLS>标签包裹。
只返回符号名称数组，例如：
<SYMBOLS>
- symbol1
- symbol2
- symbol3
</SYMBOLS>
"""

        try:
            response = self._call_llm(prompt)
            # 从<SYMBOLS>标签中提取内容
            response = response.strip()
            yaml_match = re.search(r'<SYMBOLS>\s*(.*?)\s*(?:</SYMBOLS>|<SYMBOLS>)', response, re.DOTALL)
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
            
            symbol_names = yaml.safe_load(yaml_content)
            if not isinstance(symbol_names, list):
                return []
            
            # 查找对应的符号对象
            found_symbols = []
            for name in symbol_names:
                symbols = self.context_manager.symbol_table.find_symbol(name)
                if symbols:
                    found_symbols.extend(symbols[:1])  # 每个名称只取第一个
            
            return found_symbols
        except Exception:
            return []

    def _semantic_search_files(
        self, user_input: str, keywords: List[str]
    ) -> List[str]:
        """使用LLM进行语义搜索，查找相关文件
        
        Args:
            user_input: 用户输入
            keywords: 关键词列表
            
        Returns:
            相关文件路径列表
        """
        # 获取项目中的文件列表（简化版，只获取已分析的文件）
        known_files = list(self.context_manager.dependency_graph.dependencies.keys())
        known_files.extend(self.context_manager.dependency_graph.dependents.keys())
        
        if not known_files:
            return []
        
        # 限制文件数量
        files_sample = known_files[:30]  # 最多30个文件
        
        file_info = [
            {
                "path": os.path.relpath(f, self.context_manager.project_root),
                "basename": os.path.basename(f),
            }
            for f in files_sample
        ]
        
        prompt = f"""根据以下任务描述和关键词，从文件列表中选择最相关的文件。

任务描述：{user_input}
关键词：{', '.join(keywords)}

文件列表：
{yaml.dump(file_info, allow_unicode=True, default_flow_style=False)}

请返回最相关的5-10个文件路径（YAML数组格式），按相关性排序，并用<FILES>标签包裹。
只返回文件路径数组，例如：
<FILES>
- path/to/file1.py
- path/to/file2.py
</FILES>
"""

        try:
            response = self._call_llm(prompt)
            # 从<FILES>标签中提取内容
            response = response.strip()
            yaml_match = re.search(r'<FILES>\s*(.*?)\s*(?:</FILES>|<FILES>)', response, re.DOTALL)
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
            
            file_paths = yaml.safe_load(yaml_content)
            if not isinstance(file_paths, list):
                return []
            
            # 转换为绝对路径
            result = []
            for path in file_paths:
                abs_path = os.path.join(self.context_manager.project_root, path)
                if os.path.exists(abs_path):
                    result.append(abs_path)
            
            return result
        except Exception:
            return []

    def _score_files_with_llm(
        self, user_input: str, files: List[str]
    ) -> Dict[str, float]:
        """使用LLM对文件进行相关性评分
        
        Args:
            user_input: 用户输入
            files: 文件列表
            
        Returns:
            文件路径到相关性分数的字典
        """
        if not files:
            return {}
        
        # 限制文件数量，避免prompt过长
        files_to_score = files[:20]
        
        file_info = [
            {
                "path": os.path.relpath(f, self.context_manager.project_root),
                "basename": os.path.basename(f),
            }
            for f in files_to_score
        ]
        
        prompt = f"""根据以下任务描述，对文件列表中的每个文件进行相关性评分（0-10分）。

任务描述：{user_input}

文件列表：
{yaml.dump(file_info, allow_unicode=True, default_flow_style=False)}

请返回YAML对象，键为文件路径，值为相关性分数（0-10的浮点数），并用<FILE_SCORES>标签包裹。
只返回YAML对象，例如：
<FILE_SCORES>
path/to/file1.py: 8.5
path/to/file2.py: 7.0
path/to/file3.py: 5.5
</FILE_SCORES>
"""

        try:
            response = self._call_llm(prompt)
            # 从<FILE_SCORES>标签中提取内容
            response = response.strip()
            yaml_match = re.search(r'<FILE_SCORES>\s*(.*?)\s*(?:</FILE_SCORES>|<FILE_SCORES>)', response, re.DOTALL)
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
            
            scores = yaml.safe_load(yaml_content)
            if not isinstance(scores, dict):
                return {}
            
            # 转换为绝对路径的键
            result = {}
            for rel_path, score in scores.items():
                abs_path = os.path.join(self.context_manager.project_root, rel_path)
                if abs_path in files_to_score:
                    result[abs_path] = float(score)
            
            # 为未评分的文件设置默认分数
            for f in files_to_score:
                if f not in result:
                    result[f] = 5.0  # 默认中等相关性
            
            return result
        except Exception:
            # 评分失败，返回默认分数
            return {f: 5.0 for f in files_to_score}

    def _score_symbols_with_llm(
        self, user_input: str, symbols: List[Symbol]
    ) -> Dict[Symbol, float]:
        """使用LLM对符号进行相关性评分
        
        Args:
            user_input: 用户输入
            symbols: 符号列表
            
        Returns:
            符号到相关性分数的字典
        """
        if not symbols:
            return {}
        
        # 限制符号数量
        symbols_to_score = symbols[:20]
        
        symbol_info = [
            {
                "name": s.name,
                "kind": s.kind,
                "file": os.path.basename(s.file_path),
                "signature": s.signature or "",
            }
            for s in symbols_to_score
        ]
        
        prompt = f"""根据以下任务描述，对符号列表中的每个符号进行相关性评分（0-10分）。

任务描述：{user_input}

符号列表：
{yaml.dump(symbol_info, allow_unicode=True, default_flow_style=False)}

请返回YAML对象，键为符号名称，值为相关性分数（0-10的浮点数），并用<SYMBOL_SCORES>标签包裹。
只返回YAML对象，例如：
<SYMBOL_SCORES>
symbol1: 9.0
symbol2: 7.5
symbol3: 6.0
</SYMBOL_SCORES>
"""

        try:
            response = self._call_llm(prompt)
            # 从<SYMBOL_SCORES>标签中提取内容
            response = response.strip()
            yaml_match = re.search(r'<SYMBOL_SCORES>\s*(.*?)\s*(?:</SYMBOL_SCORES>|<SYMBOL_SCORES>)', response, re.DOTALL)
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
            
            scores = yaml.safe_load(yaml_content)
            if not isinstance(scores, dict):
                return {}
            
            # 创建符号到分数的映射
            result = {}
            for s in symbols_to_score:
                score = scores.get(s.name, 5.0)  # 默认中等相关性
                result[s] = float(score)
            
            return result
        except Exception:
            # 评分失败，返回默认分数
            return {s: 5.0 for s in symbols_to_score}

    def _find_test_files(self, file_path: str) -> List[str]:
        """查找与文件相关的测试文件
        
        Args:
            file_path: 源文件路径
            
        Returns:
            测试文件路径列表
        """
        test_files = []
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        project_root = self.context_manager.project_root

        # 常见的测试文件命名模式
        test_patterns = [
            f"test_{base_name}.py",
            f"{base_name}_test.py",
            f"test_{base_name}.js",
            f"{base_name}.test.js",
            f"test_{base_name}.ts",
            f"{base_name}.test.ts",
            f"{base_name}_test.rs",
            f"test_{base_name}.go",
        ]

        # 在项目根目录搜索测试文件
        for root, dirs, files in os.walk(project_root):
            # 跳过隐藏目录和常见忽略目录
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'target']]

            # 检查是否是测试目录
            if 'test' in root.lower() or 'tests' in root.lower():
                for pattern in test_patterns:
                    if pattern in files:
                        test_file = os.path.join(root, pattern)
                        if os.path.exists(test_file):
                            test_files.append(test_file)

        return test_files[:5]  # 限制数量

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
                return response
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
        lines = ["\n💡 智能上下文推荐:"]
        lines.append("─" * 60)

        if recommendation.reason:
            lines.append(f"📌 推荐原因: {recommendation.reason}")

        if recommendation.recommended_files:
            files_str = "\n   ".join(
                f"• {os.path.relpath(f, self.context_manager.project_root)}"
                for f in recommendation.recommended_files[:5]
            )
            more = len(recommendation.recommended_files) - 5
            if more > 0:
                files_str += f"\n   ... 还有{more}个文件"
            lines.append(f"📁 推荐文件 ({len(recommendation.recommended_files)}个):\n   {files_str}")

        if recommendation.recommended_symbols:
            symbols_str = "\n   ".join(
                f"• {s.kind} `{s.name}` ({os.path.relpath(s.file_path, self.context_manager.project_root)}:{s.line_start})"
                for s in recommendation.recommended_symbols[:5]
            )
            more = len(recommendation.recommended_symbols) - 5
            if more > 0:
                symbols_str += f"\n   ... 还有{more}个符号"
            lines.append(f"🔗 推荐符号 ({len(recommendation.recommended_symbols)}个):\n   {symbols_str}")

        if recommendation.related_tests:
            tests_str = "\n   ".join(
                f"• {os.path.relpath(f, self.context_manager.project_root)}"
                for f in recommendation.related_tests[:3]
            )
            more = len(recommendation.related_tests) - 3
            if more > 0:
                tests_str += f"\n   ... 还有{more}个测试文件"
            lines.append(f"🧪 相关测试 ({len(recommendation.related_tests)}个):\n   {tests_str}")

        lines.append("─" * 60)
        lines.append("")  # 空行

        return "\n".join(lines) if len(lines) > 2 else ""  # 如果没有推荐内容，返回空字符串
