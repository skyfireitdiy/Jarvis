"""依赖关系分析器测试。"""

from __future__ import annotations

from pathlib import Path

from jarvis.jarvis_arch_analyzer.dependency import (
    CircularDependency,
    CouplingMetrics,
    DependencyAnalyzer,
    DependencyNode,
    DependencyReport,
)


def test_dependency_node() -> None:
    """测试依赖节点数据类。"""
    node = DependencyNode(
        module_name="test_module",
        file_path="/path/to/test.py",
        dependencies={"dep1", "dep2"},
        dependents={"dependent1"},
        level=1,
    )

    assert node.module_name == "test_module"
    assert len(node.dependencies) == 2
    assert len(node.dependents) == 1
    assert node.level == 1

    # 测试to_dict方法
    node_dict = node.to_dict()
    assert node_dict["module_name"] == "test_module"
    assert "dep1" in node_dict["dependencies"]
    assert "dependent1" in node_dict["dependents"]


def test_circular_dependency() -> None:
    """测试循环依赖数据类。"""
    cycle = CircularDependency(
        cycle_path=["module_a", "module_b", "module_c"], severity="warning"
    )

    assert len(cycle.cycle_path) == 3
    assert cycle.severity == "warning"

    # 测试to_dict方法
    cycle_dict = cycle.to_dict()
    assert "cycle_str" in cycle_dict
    assert "module_a -> module_b -> module_c -> module_a" in cycle_dict["cycle_str"]


def test_coupling_metrics() -> None:
    """测试耦合度指标数据类。"""
    metrics = CouplingMetrics(
        module_name="test_module",
        afferent_coupling=5,
        efferent_coupling=3,
        instability=0.375,
    )

    assert metrics.module_name == "test_module"
    assert metrics.afferent_coupling == 5
    assert metrics.efferent_coupling == 3
    assert metrics.instability == 0.375

    # 测试to_dict方法
    metrics_dict = metrics.to_dict()
    assert metrics_dict["afferent_coupling"] == 5
    assert metrics_dict["instability"] == 0.375


def test_dependency_report() -> None:
    """测试依赖报告数据类。"""
    report = DependencyReport(
        total_modules=10,
        circular_dependencies=[],
        coupling_metrics=[],
        max_depth=3,
        average_coupling=2.5,
    )

    assert report.total_modules == 10
    assert report.max_depth == 3
    assert report.average_coupling == 2.5

    # 测试to_dict方法
    report_dict = report.to_dict()
    assert report_dict["total_modules"] == 10
    assert "dependency_graph" in report_dict
    assert "circular_dependencies" in report_dict


def test_analyze_simple_project() -> None:
    """测试分析简单项目。"""
    # 创建测试目录结构
    test_dir = Path("/tmp/test_dependency_simple")
    test_dir.mkdir(exist_ok=True)

    try:
        # 创建模块A
        module_a = test_dir / "module_a.py"
        module_a.write_text(
            """# Module A
import os
from pathlib import Path

"""
        )

        # 创建模块B（依赖A）
        module_b = test_dir / "module_b.py"
        module_b.write_text(
            """# Module B
from module_a import something
import sys

"""
        )

        # 分析依赖
        analyzer = DependencyAnalyzer()
        report = analyzer.analyze_directory(test_dir)

        assert report.total_modules >= 2
        assert "module_a" in report.dependency_graph
        assert "module_b" in report.dependency_graph

        # module_b应该依赖module_a
        node_b = report.dependency_graph["module_b"]
        assert "module_a" in node_b.dependencies

        # module_a应该被module_b依赖
        node_a = report.dependency_graph["module_a"]
        assert "module_b" in node_a.dependents

    finally:
        # 清理
        import shutil

        shutil.rmtree(test_dir, ignore_errors=True)


def test_detect_circular_dependency() -> None:
    """测试循环依赖检测。"""
    # 创建测试目录结构
    test_dir = Path("/tmp/test_dependency_circular")
    test_dir.mkdir(exist_ok=True)

    try:
        # 创建模块A（依赖B）
        module_a = test_dir / "module_a.py"
        module_a.write_text(
            """# Module A
from module_b import something_b

"""
        )

        # 创建模块B（依赖A）
        module_b = test_dir / "module_b.py"
        module_b.write_text(
            """# Module B
from module_a import something_a

"""
        )

        # 分析依赖
        analyzer = DependencyAnalyzer()
        report = analyzer.analyze_directory(test_dir)

        # 应该检测到循环依赖
        assert len(report.circular_dependencies) >= 1

        # 检查循环路径
        found_cycle = False
        for cycle in report.circular_dependencies:
            if "module_a" in cycle.cycle_path and "module_b" in cycle.cycle_path:
                found_cycle = True
                break

        assert found_cycle, "应该检测到module_a和module_b之间的循环依赖"

    finally:
        # 清理
        import shutil

        shutil.rmtree(test_dir, ignore_errors=True)


def test_calculate_coupling_metrics() -> None:
    """测试耦合度计算。"""
    # 创建测试目录结构
    test_dir = Path("/tmp/test_dependency_coupling")
    test_dir.mkdir(exist_ok=True)

    try:
        # 创建基础模块（被依赖）
        base = test_dir / "base.py"
        base.write_text("# Base module\n")

        # 创建中间模块（依赖base，被derived依赖）
        middle = test_dir / "middle.py"
        middle.write_text(
            """# Middle module
from base import Base

"""
        )

        # 创建派生模块（依赖middle）
        derived = test_dir / "derived.py"
        derived.write_text(
            """# Derived module
from middle import Middle

"""
        )

        # 分析依赖
        analyzer = DependencyAnalyzer()
        report = analyzer.analyze_directory(test_dir)

        # 检查耦合度指标
        assert len(report.coupling_metrics) >= 3

        # 找到base模块的指标
        base_metrics = None
        for m in report.coupling_metrics:
            if m.module_name == "base":
                base_metrics = m
                break

        assert base_metrics is not None
        # base模块应该有较高的入度耦合（被依赖）
        assert base_metrics.afferent_coupling >= 1

        # 找到derived模块的指标
        derived_metrics = None
        for m in report.coupling_metrics:
            if m.module_name == "derived":
                derived_metrics = m
                break

        assert derived_metrics is not None
        # derived模块应该有较高的出度耦合（依赖他人）
        assert derived_metrics.efferent_coupling >= 1

    finally:
        # 清理
        import shutil

        shutil.rmtree(test_dir, ignore_errors=True)


def test_exclusion_patterns() -> None:
    """测试排除模式。"""
    # 创建测试目录结构
    test_dir = Path("/tmp/test_dependency_exclude")
    test_dir.mkdir(exist_ok=True)

    try:
        # 创建普通模块
        normal = test_dir / "normal.py"
        normal.write_text("# Normal module\n")

        # 创建测试模块（应该被排除）
        test_module = test_dir / "test_normal.py"
        test_module.write_text(
            """# Test module
from normal import something

"""
        )

        # 分析依赖（使用默认排除模式）
        analyzer = DependencyAnalyzer()
        report = analyzer.analyze_directory(test_dir)

        # test_normal应该被排除
        assert "test_normal" not in report.dependency_graph
        assert "normal" in report.dependency_graph

    finally:
        # 清理
        import shutil

        shutil.rmtree(test_dir, ignore_errors=True)


def test_dependency_levels() -> None:
    """测试依赖层级计算。"""
    # 创建测试目录结构
    test_dir = Path("/tmp/test_dependency_levels")
    test_dir.mkdir(exist_ok=True)

    try:
        # 创建顶层模块
        top = test_dir / "top.py"
        top.write_text("# Top level module\n")

        # 创建中间模块（依赖top）
        mid = test_dir / "mid.py"
        mid.write_text(
            """# Middle module
from top import Top

"""
        )

        # 创建底层模块（依赖mid）
        bottom = test_dir / "bottom.py"
        bottom.write_text(
            """# Bottom module
from mid import Mid

"""
        )

        # 分析依赖
        analyzer = DependencyAnalyzer()
        report = analyzer.analyze_directory(test_dir)

        # 检查最大深度
        assert report.max_depth >= 2

        # top模块应该在较低层级
        top_node = report.dependency_graph.get("top")
        if top_node:
            assert top_node.level == 0

        # bottom模块应该在较高层级
        bottom_node = report.dependency_graph.get("bottom")
        if bottom_node:
            assert bottom_node.level >= 1

    finally:
        # 清理
        import shutil

        shutil.rmtree(test_dir, ignore_errors=True)
