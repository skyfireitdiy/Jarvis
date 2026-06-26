"""
Joern污点分析器 - 基于Joern CPG的污点分析实现

Joern是一个开源（Apache 2.0许可）的代码分析平台，支持C/C++等多种语言。
通过生成代码属性图（CPG）进行污点传播分析。
"""

import subprocess
import tempfile
import os
import json
import shutil
from typing import List, Optional
from pathlib import Path

from .taint_analyzer import (
    TaintAnalyzer,
    TaintPath,
    TaintSource,
    TaintSink,
    TaintAnalyzerFactory,
)


class JoernAnalyzer(TaintAnalyzer):
    """Joern-based污点分析器"""
    
    def __init__(self, joern_path: Optional[str] = None):
        super().__init__()
        self.joern_path = joern_path or self._find_joern()
        self.cpg_path = None
        self.temp_dir = None
    
    def _find_joern(self) -> Optional[str]:
        """查找Joern安装路径"""
        # 检查环境变量
        joern_home = os.environ.get("JOERN_HOME")
        if joern_home:
            joern_exe = os.path.join(joern_home, "joern")
            if os.path.isfile(joern_exe):
                return joern_exe
        
        # 检查PATH
        joern_in_path = shutil.which("joern")
        if joern_in_path:
            return joern_in_path
        
        # 检查常见安装位置
        common_paths = [
            "/opt/joern/joern",
            "/usr/local/bin/joern",
            "~/joern/joern",
            "~/bin/joern",
        ]
        for path in common_paths:
            expanded_path = os.path.expanduser(path)
            if os.path.isfile(expanded_path):
                return expanded_path
        
        return None
    
    def is_available(self) -> bool:
        """检查Joern是否可用"""
        return self.joern_path is not None and os.path.isfile(self.joern_path)
    
    def get_name(self) -> str:
        """获取分析器名称"""
        return "Joern"
    
    def get_version(self) -> str:
        """获取Joern版本"""
        if not self.is_available():
            return "unknown"
        
        try:
            result = subprocess.run(
                [self.joern_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            # 解析版本信息
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                for line in lines:
                    if "version" in line.lower():
                        return line.split()[-1]
            return "unknown"
        except Exception:
            return "unknown"
    
    def _generate_cpg(self, source_code: str, file_path: str) -> Optional[str]:
        """
        生成代码属性图（CPG）
        
        Args:
            source_code: 源代码内容
            file_path: 文件路径（用于确定语言类型）
            
        Returns:
            CPG文件路径，失败返回None
        """
        if not self.is_available():
            return None
        
        # 创建临时目录
        self.temp_dir = tempfile.mkdtemp(prefix="joern_analyze_")
        
        # 写入源代码到临时文件
        source_file = os.path.join(self.temp_dir, "source.c")
        if file_path:
            # 使用原始文件扩展名
            ext = os.path.splitext(file_path)[1] or ".c"
            source_file = os.path.join(self.temp_dir, f"source{ext}")
        
        with open(source_file, "w", encoding="utf-8") as f:
            f.write(source_code)
        
        # 生成CPG
        cpg_file = os.path.join(self.temp_dir, "cpg.bin")
        
        try:
            # 使用joern-parse生成CPG
            result = subprocess.run(
                [self.joern_path, "--script", "importCode", "--params", f"inputFile={source_file}"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.temp_dir
            )
            
            if result.returncode == 0:
                self.cpg_path = cpg_file
                return cpg_file
            else:
                # 尝试使用joern命令行模式
                query = f"importCode("{source_file}")"
                result = subprocess.run(
                    [self.joern_path],
                    input=query,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode == 0:
                    self.cpg_path = "workspace"  # Joern默认workspace
                    return self.cpg_path
        
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass
        
        return None
    
    def _execute_query(self, query: str) -> Optional[str]:
        """
        执行Joern查询
        
        Args:
            query: Joern查询语句
            
        Returns:
            查询结果（JSON格式），失败返回None
        """
        if not self.is_available():
            return None
        
        try:
            result = subprocess.run(
                [self.joern_path],
                input=query,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                return result.stdout
        
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass
        
        return None
    
    def _build_taint_query(self) -> str:
        """
        构建污点分析查询
        
        根据配置的污点源和污点汇构建Joern查询语句
        """
        # 构建污点源列表
        source_patterns = []
        for source in self.sources:
            for pattern in source.patterns:
                source_patterns.append(pattern)
        
        # 构建污点汇列表
        sink_patterns = []
        for sink in self.sinks:
            for pattern in sink.patterns:
                sink_patterns.append(pattern)
        
        # 构建查询语句
        # 示例：查找从getenv到system的污点传播
        query_parts = []
        
        for source in source_patterns:
            for sink in sink_patterns:
                # 查找污点源调用
                source_query = f"cpg.call.name("{source}").l"
                # 查找污点汇调用
                sink_query = f"cpg.call.name("{sink}").l"
                # 查找从源到汇的路径
                path_query = f"cpg.call.name("{source}").reachableBy(cpg.call.name("{sink}")).l"
                
                query_parts.append(path_query)
        
        # 合并查询
        full_query = "\n".join(query_parts)
        return full_query
    
    def _parse_results(self, results: str, source_code: str) -> List[TaintPath]:
        """
        解析Joern查询结果
        
        Args:
            results: Joern查询输出
            source_code: 原始源代码
            
        Returns:
            污点路径列表
        """
        paths = []
        
        if not results:
            return paths
        
        # 解析结果（Joern输出格式可能变化，这里提供基本解析）
        lines = results.strip().split("\n")
        
        for line in lines:
            if "reachableBy" in line or "path" in line.lower():
                # 尝试提取路径信息
                # 这里需要根据实际Joern输出格式进行调整
                try:
                    # 简化解析：假设输出包含source和sink信息
                    path = TaintPath(
                        source="unknown",
                        sink="unknown",
                        path=[line],
                        confidence=0.7,
                        description=f"Joern检测到可能的污点传播路径",
                        code_snippet=line
                    )
                    paths.append(path)
                except Exception:
                    continue
        
        return paths
    
    def analyze(self, source_code: str, file_path: str = "") -> List[TaintPath]:
        """
        执行污点分析
        
        Args:
            source_code: 源代码内容
            file_path: 文件路径（可选）
            
        Returns:
            污点传播路径列表
        """
        if not self.is_available():
            return []
        
        # 生成CPG
        cpg = self._generate_cpg(source_code, file_path)
        if not cpg:
            return []
        
        # 构建污点查询
        query = self._build_taint_query()
        
        # 执行查询
        results = self._execute_query(query)
        
        # 解析结果
        paths = self._parse_results(results, source_code)
        
        return paths
    
    def analyze_file(self, file_path: str) -> List[TaintPath]:
        """
        分析文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            污点传播路径列表
        """
        if not os.path.isfile(file_path):
            return []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source_code = f.read()
            return self.analyze(source_code, file_path)
        except Exception:
            return []
    
    def cleanup(self):
        """清理临时文件"""
        if self.temp_dir and os.path.isdir(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except Exception:
                pass
            self.temp_dir = None
            self.cpg_path = None
    
    def __del__(self):
        """析构函数：清理临时文件"""
        self.cleanup()


# 注册到工厂
TaintAnalyzerFactory.register("joern", JoernAnalyzer)
