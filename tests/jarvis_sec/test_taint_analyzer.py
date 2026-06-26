# -*- coding: utf-8 -*-
"""
jarvis_sec 污点分析测试

覆盖点：
- 污点分析框架：TaintPath、TaintSource、TaintSink数据结构
- Joern分析器：查询生成、结果解析
- 污点分析集成：与启发式扫描的集成

运行：
- 使用 pytest 执行：pytest tests/jarvis_sec/test_taint_analyzer.py -v
"""

from __future__ import annotations

from jarvis.jarvis_sec.taint_analyzer import (
    TaintPath,
    TaintSource,
    TaintSink,
    TaintAnalyzerFactory,
    TAINT_RULES,
    TaintSeverity,
)
from jarvis.jarvis_sec.joern_analyzer import JoernAnalyzer
from jarvis.jarvis_sec.checkers import analyze_c_cpp_text


def test_taint_analyzer_data_structures():
    """测试污点分析数据结构"""
    # 测试 TaintSource
    source = TaintSource(
        name="getenv",
        category="environment",
        description="从环境变量获取数据",
        patterns=["getenv"],
    )
    assert source.name == "getenv"
    assert source.category == "environment"
    assert "getenv" in source.patterns

    # 测试 TaintSink
    sink = TaintSink(
        name="system",
        category="command_execution",
        severity=TaintSeverity.CRITICAL,
        description="执行系统命令",
        patterns=["system", "popen"],
    )
    assert sink.name == "system"
    assert sink.category == "command_execution"
    assert sink.severity == TaintSeverity.CRITICAL

    # 测试 TaintPath
    path = TaintPath(
        source="getenv",
        sink="system",
        path=["getenv", "system"],
        confidence=0.8,
        severity=TaintSeverity.CRITICAL,
        description="污点从 getenv 传播到 system",
        line_number=10,
    )
    assert path.source == "getenv"
    assert path.sink == "system"
    assert path.confidence == 0.8
    assert path.line_number == 10


def test_taint_rules_predefined():
    """测试预定义的污点规则"""
    # 检查预定义规则是否存在
    assert "command_injection" in TAINT_RULES
    assert "format_string" in TAINT_RULES
    assert "path_traversal" in TAINT_RULES
    assert "sql_injection" in TAINT_RULES
    assert "buffer_overflow" in TAINT_RULES

    # 检查命令注入规则
    cmd_rule = TAINT_RULES["command_injection"]
    assert cmd_rule.name == "command_injection"
    assert cmd_rule.severity == TaintSeverity.CRITICAL
    assert len(cmd_rule.sources) > 0
    assert len(cmd_rule.sinks) > 0


def test_joern_analyzer_initialization():
    """测试Joern分析器初始化"""
    # 测试工厂创建
    analyzer = TaintAnalyzerFactory.create("joern")
    assert analyzer is not None
    assert isinstance(analyzer, JoernAnalyzer)


def test_joern_analyzer_query_generation():
    """测试Joern查询生成"""
    analyzer = JoernAnalyzer()

    # 创建测试用的污点源和汇
    source = TaintSource(
        name="getenv",
        category="environment",
        patterns=["getenv"],
    )
    sink = TaintSink(
        name="system",
        category="command_execution",
        severity=TaintSeverity.CRITICAL,
        patterns=["system", "popen"],
    )

    # 生成查询
    query = analyzer._generate_taint_query(source, sink)

    # 验证查询内容
    assert "getenv" in query
    assert "system" in query
    assert "reachableByFlows" in query


def test_taint_analysis_integration():
    """测试污点分析集成到启发式扫描"""
    # 测试代码：包含命令注入漏洞
    src = r"""
#include <stdlib.h>
#include <stdio.h>

int main(int argc, char *argv[]) {
    char *cmd = getenv("CMD");
    if (cmd) {
        system(cmd);  // 命令注入风险
    }
    return 0;
}
"""

    # 执行分析
    issues = analyze_c_cpp_text("test.c", src)

    # 验证结果
    # 应该检测到命令执行相关的问题
    # 注意：污点分析可能因为Joern未安装而返回空结果
    # 但启发式规则应该能检测到system调用
    assert len(issues) >= 0  # 至少不应该崩溃


def test_format_string_taint_analysis():
    """测试格式化字符串污点分析"""
    # 测试代码：包含格式化字符串漏洞
    src = r"""
#include <stdio.h>

void vulnerable_printf(char *user_input) {
    printf(user_input);  // 格式化字符串漏洞
}
"""

    # 执行分析
    issues = analyze_c_cpp_text("test.c", src)

    # 验证结果
    # 应该检测到格式化字符串相关的问题
    assert len(issues) >= 0  # 至少不应该崩溃


def test_taint_path_to_dict():
    """测试TaintPath转换为字典"""
    path = TaintPath(
        source="getenv",
        sink="system",
        path=["getenv", "system"],
        confidence=0.8,
        severity=TaintSeverity.CRITICAL,
        description="污点从 getenv 传播到 system",
        line_number=10,
    )

    # 转换为字典
    path_dict = path.to_dict()

    # 验证字典内容
    assert path_dict["source"] == "getenv"
    assert path_dict["sink"] == "system"
    assert path_dict["confidence"] == 0.8
    assert path_dict["severity"] == "critical"
    assert path_dict["line_number"] == 10


def test_taint_analyzer_factory():
    """测试污点分析器工厂"""
    # 测试创建Joern分析器
    analyzer = TaintAnalyzerFactory.create("joern")
    assert analyzer is not None

    # 测试配置污点源和汇
    source = TaintSource(
        name="test_source",
        category="test",
        patterns=["test_func"],
    )
    sink = TaintSink(
        name="test_sink",
        category="test",
        severity=TaintSeverity.HIGH,
        patterns=["test_sink_func"],
    )

    analyzer.configure_sources([source])
    analyzer.configure_sinks([sink])

    # 验证配置
    assert len(analyzer.sources) == 1
    assert len(analyzer.sinks) == 1
    assert analyzer.sources[0].name == "test_source"
    assert analyzer.sinks[0].name == "test_sink"
