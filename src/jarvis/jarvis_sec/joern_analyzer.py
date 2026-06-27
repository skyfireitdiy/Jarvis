"""
Joern污点分析器 - 基于Joern CPG的污点分析实现

Joern是一个开源（Apache 2.0许可）的代码分析平台，支持C/C++等多种语言。
通过生成代码属性图（CPG）进行污点传播分析。
"""

import subprocess
import tempfile
import os
from typing import List, Optional, TYPE_CHECKING

from .taint_analyzer import (
    TaintAnalyzer,
    TaintPath,
    TaintSource,
    TaintSink,
    TaintAnalyzerFactory,
)

if TYPE_CHECKING:
    from jarvis.jarvis_sec.project_database import ProjectDatabase


class JoernAnalyzer(TaintAnalyzer):
    """
    基于Joern的污点分析器实现

    Joern是一个开源的代码分析平台，通过生成代码属性图（CPG）进行污点传播分析。
    支持C/C++等多种语言。
    """

    def __init__(
        self, joern_path: str = "joern", database: Optional["ProjectDatabase"] = None
    ):
        """
        初始化Joern分析器

        Args:
            joern_path: Joern CLI工具路径，默认为"joern"（假设在PATH中）
            database: 项目数据库实例（可选）
        """
        self.joern_path = joern_path
        self.database = database
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

    def is_available(self) -> bool:
        """
        检查分析器是否可用

        Returns:
            bool: True如果Joern已安装并可用
        """
        return self._check_joern_available()

    def get_name(self) -> str:
        """
        获取分析器名称

        Returns:
            str: 分析器名称
        """
        return "Joern"

    def get_version(self) -> str:
        """
        获取分析器版本

        Returns:
            str: 分析器版本号
        """
        try:
            result = subprocess.run(
                [self.joern_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                # 解析版本号
                import re

                match = re.search(r"(\d+\.\d+\.\d+)", result.stdout)
                if match:
                    return match.group(1)
            return "unknown"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return "unknown"

    def analyze_file(self, file_path: str) -> List[TaintPath]:
        """
        分析文件

        Args:
            file_path: 文件路径

        Returns:
            List[TaintPath]: 污点传播路径列表
        """
        try:
            with open(file_path, "r") as f:
                source_code = f.read()
            return self.analyze(source_code, file_path)
        except (IOError, OSError):
            return []

    def analyze(
        self,
        source_code: str,
        file_path: str = "",
        database: Optional["ProjectDatabase"] = None,
    ) -> List[TaintPath]:
        """
        分析源代码中的污点传播路径

        Args:
            source_code: 源代码内容
            file_path: 源代码文件路径
            database: 项目数据库实例（可选，覆盖初始化时的设置）

        Returns:
            List[TaintPath]: 检测到的污点传播路径列表
        """
        # 使用传入的database或初始化时的database
        db = database or self.database
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
            paths = self._run_taint_analysis(cpg_file, self.sources, self.sinks)

            # 如果提供了数据库，增强污点分析结果
            if db is not None and file_path:
                paths = self._enhance_with_database(paths, db, file_path)

            return paths

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

    def _enhance_with_database(
        self,
        paths: List[TaintPath],
        database: "ProjectDatabase",
        file_path: str,
    ) -> List[TaintPath]:
        """
        利用数据库增强污点分析结果

        Args:
            paths: 原始污点路径列表
            database: 项目数据库实例
            file_path: 当前文件路径

        Returns:
            List[TaintPath]: 增强后的污点路径列表
        """
        if not paths:
            return paths

        try:
            # 获取完整的调用图（方法不接受参数）
            call_graph = database.get_call_graph()

            # 获取当前文件的数据流节点
            data_flow_nodes = database.get_data_flow_by_file(file_path)

            # 增强每条污点路径
            enhanced_paths = []
            for path in paths:
                enhanced_path = path

                # 如果有调用图信息，尝试扩展污点路径
                if call_graph:
                    for call_info in call_graph:
                        # 检查污点路径是否经过该调用点
                        if self._path_involves_call(path, call_info):
                            # 扩展污点路径，添加跨函数信息
                            enhanced_path = self._extend_path_with_call(
                                enhanced_path, call_info, database
                            )

                # 如果有数据流节点，尝试扩展污点路径
                if data_flow_nodes:
                    for node in data_flow_nodes:
                        if self._path_involves_data_node(path, node):
                            enhanced_path = self._extend_path_with_data_node(
                                enhanced_path, node
                            )

                enhanced_paths.append(enhanced_path)

            return enhanced_paths

        except Exception:
            # 数据库查询失败时返回原始路径
            return paths

    def _path_involves_call(self, path: TaintPath, call_info: dict) -> bool:
        """检查污点路径是否涉及某个调用点"""
        # 简单实现：检查调用函数名是否在路径中
        caller_func = call_info.get("caller_function", "")
        callee_func = call_info.get("callee_function", "")
        return caller_func in path.path or callee_func in path.path

    def _extend_path_with_call(
        self, path: TaintPath, call_info: dict, database: "ProjectDatabase"
    ) -> TaintPath:
        """扩展污点路径，添加跨函数调用信息"""
        # 创建新的路径列表
        new_path = list(path.path)

        # 添加跨函数调用节点
        callee_file = call_info.get("callee_file", "")
        callee_func = call_info.get("callee_function", "")
        if callee_file and callee_func:
            cross_file_node = f"{callee_file}:{callee_func}"
            if cross_file_node not in new_path:
                new_path.append(cross_file_node)

        # 更新描述
        new_description = path.description
        if callee_file:
            new_description += f" (跨函数调用: {callee_func}@{callee_file})"

        return TaintPath(
            source=path.source,
            sink=path.sink,
            path=new_path,
            confidence=min(path.confidence + 0.1, 1.0),  # 提高置信度
            severity=path.severity,
            description=new_description,
            line_number=path.line_number,
        )

    def _path_involves_data_node(self, path: TaintPath, node: dict) -> bool:
        """检查污点路径是否涉及某个数据流节点"""
        var_name = node.get("var_name", "")
        return var_name in path.path

    def _extend_path_with_data_node(self, path: TaintPath, node: dict) -> TaintPath:
        """扩展污点路径，添加数据流节点信息"""
        new_path = list(path.path)

        # 添加数据流节点信息
        var_name = node.get("var_name", "")
        node_file = node.get("file_path", "")
        node_line = node.get("line", 0)
        node_type = node.get("node_type", "")

        if node_file and var_name:
            data_node = f"{node_file}:{var_name}@{node_type}"
            if data_node not in new_path:
                new_path.append(data_node)

        # 更新描述
        new_description = path.description
        if node_file and var_name:
            new_description += f" (数据流: {var_name}@{node_file}:{node_line})"

        return TaintPath(
            source=path.source,
            sink=path.sink,
            path=new_path,
            confidence=min(path.confidence + 0.15, 1.0),  # 提高置信度
            severity=path.severity,
            description=new_description,
            line_number=path.line_number,
        )


# 注册到工厂
TaintAnalyzerFactory.register("joern", JoernAnalyzer)
