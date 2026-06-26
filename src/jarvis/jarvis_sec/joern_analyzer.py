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
