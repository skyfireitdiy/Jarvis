"""
Joern污点分析器 - 基于Joern CPG的污点分析实现

Joern是一个开源（Apache 2.0许可）的代码分析平台，支持C/C++等多种语言。
通过生成代码属性图（CPG）进行污点传播分析。
"""

import subprocess
import tempfile
import os
import shutil
from typing import List, Optional

from .taint_analyzer import (
    TaintAnalyzer,
    TaintPath,
    TaintSource,
    TaintSink,
    TaintAnalyzerFactory,
)


class JoernAnalyzer(TaintAnalyzer):
    """
    基于Joern的污点分析器实现
    
    Joern是一个开源的代码分析平台，通过生成代码属性图（CPG）进行污点传播分析。
    支持C/C++等多种语言。
    """
    
    def __init__(self, joern_path: str = "joern"):
        """
        初始化Joern分析器
        
        Args:
            joern_path: Joern CLI工具路径，默认为"joern"（假设在PATH中）
        """
        self.joern_path = joern_path
        self._check_joern_available()
    
    def _check_joern_available(self) -> bool:
        """
        检查Joern是否可用
        
        Returns:
            bool: Joern是否可用
        """
        try:
            result = subprocess.run(
                [self.joern_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
