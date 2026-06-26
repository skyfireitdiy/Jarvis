"""
Joern污点分析器 - 基于Joern CPG的污点分析实现

Joern是一个开源（Apache 2.0许可）的代码分析平台，支持C/C++等多种语言。
通过生成代码属性图（CPG）进行污点传播分析。
"""

import subprocess
import tempfile
import os
from typing import List

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
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def analyze(self, source_code: str, file_path: str = "") -> List[TaintPath]:
        """
        分析源代码中的污点传播路径

        Args:
            source_code: 源代码内容
            file_path: 源代码文件路径

        Returns:
            List[TaintPath]: 检测到的污点传播路径列表
        """
        # 创建临时工作目录
        with tempfile.TemporaryDirectory() as tmpdir:
            # 写入源代码文件
            src_file = os.path.join(tmpdir, os.path.basename(file_path))
            with open(src_file, "w") as f:
                f.write(source_code)

            # 生成CPG
            cpg_file = os.path.join(tmpdir, "cpg.bin")
            try:
                subprocess.run(
                    [
                        self.joern_path,
                        "--script",
                        "create-cpg",
                        "--param",
                        f"inputPath={src_file}",
                        "--param",
                        f"outputPath={cpg_file}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=True,
                )
            except subprocess.CalledProcessError:
                return []
            except subprocess.TimeoutExpired:
                return []

            # 执行污点分析
            return self._run_taint_analysis(cpg_file, self.sources, self.sinks)

    def _run_taint_analysis(
        self, cpg_file: str, sources: List[TaintSource], sinks: List[TaintSink]
    ) -> List[TaintPath]:
        """
        执行污点分析

        Args:
            cpg_file: CPG文件路径
            sources: 污点源列表
            sinks: 污点汇列表

        Returns:
            List[TaintPath]: 检测到的污点传播路径列表
        """
        taint_paths = []

        # 为每个污点源和汇生成查询
        for source in sources:
            for sink in sinks:
                # 生成Joern查询脚本
                query_script = self._generate_taint_query(source, sink)

                # 执行查询
                try:
                    result = subprocess.run(
                        [
                            self.joern_path,
                            "--script",
                            "query",
                            "--param",
                            f"cpgFile={cpg_file}",
                            "--param",
                            f"query={query_script}",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )

                    if result.returncode == 0:
                        # 解析结果
                        paths = self._parse_joern_output(result.stdout, source, sink)
                        taint_paths.extend(paths)

                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    # 查询失败时继续下一个
                    continue

        return taint_paths

    def _generate_taint_query(self, source: TaintSource, sink: TaintSink) -> str:
        """
        生成Joern污点分析查询脚本

        Args:
            source: 污点源
            sink: 污点汇

        Returns:
            str: Joern查询脚本
        """
        # 构建源查询（匹配函数调用或参数）
        source_patterns = "|".join(source.patterns)
        source_query = f'cpg.call.name("{source_patterns}").argument'

        # 构建汇查询（匹配函数调用）
        sink_patterns = "|".join(sink.patterns)
        sink_query = f'cpg.call.name("{sink_patterns}").argument'

        # 生成reachableByFlows查询
        query = f"""def source = {source_query}
def sink = {sink_query}
sink.reachableByFlows(source).l"""

        return query

    def _parse_joern_output(
        self, output: str, source: TaintSource, sink: TaintSink
    ) -> List[TaintPath]:
        """
        解析Joern输出结果

        Args:
            output: Joern输出字符串
            source: 污点源
            sink: 污点汇

        Returns:
            List[TaintPath]: 解析出的污点路径列表
        """
        paths = []

        # Joern输出格式示例:
        # ┌─────────────────┬────────────────────────────┬──────────┬──────┬─────┐
        # │nodeType         │tracked                     │lineNumber│method│file │
        # ├─────────────────┼────────────────────────────┼──────────┼──────┼─────┤
        # │MethodParameterIn│main(int argc, char *argv[])│5         │main  │X42.c│
        # │Call             │strcmp(argv[1], "42")       │6         │main  │X42.c│
        # └─────────────────┴────────────────────────────┴──────────┴──────┴─────┘

        # 简单解析：查找包含lineNumber的行
        lines = output.split("\n")
        for line in lines:
            if "lineNumber" in line or "line" in line.lower():
                # 尝试提取行号
                import re

                line_match = re.search(r"lineNumber[=\s]+(\d+)", line)
                if line_match:
                    line_number = int(line_match.group(1))

                    # 创建污点路径
                    path = TaintPath(
                        source=source.name,
                        sink=sink.name,
                        path=[source.name, sink.name],
                        confidence=0.8,  # 基于Joern分析的置信度
                        severity=sink.severity,
                        description=f"污点从 {source.name} 传播到 {sink.name}",
                        line_number=line_number,
                    )
                    paths.append(path)

        return paths


# 注册到工厂
TaintAnalyzerFactory.register("joern", JoernAnalyzer)
