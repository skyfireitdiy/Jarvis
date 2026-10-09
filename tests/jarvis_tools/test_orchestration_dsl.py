# -*- coding: utf-8 -*-
"""编排 Python DSL（orchestration_dsl）与统一加载器（orchestration_loader）测试。

覆盖：
1. DSL 构造：stage() 归一化/校验、Pipeline.add/agent/spec/default_on_error、
   to_dict 导出结构与 YAML 同构；
2. 等价性：DSL 产出的结构经 pipeline_runner._build_dag 构建的 DAG，
   与等价 YAML 结构经 _build_dag 的结果逐字段一致（关键不变量）；
3. 加载器：.yaml 与 .flow 返回同构结构、错误路径（不存在/不支持后缀/
   缺 pipeline 变量/语法错）抛清晰 ValueError。
"""
import textwrap
from typing import cast

import pytest

from jarvis.jarvis_tools.orchestration_dsl import Pipeline
from jarvis.jarvis_tools.orchestration_dsl import stage
from jarvis.jarvis_tools.orchestration_loader import load_orchestration
from jarvis.jarvis_tools.pipeline_runner import PipelineRunnerTool


@pytest.fixture
def tool():
    return PipelineRunnerTool()


# ---------------------------------------------------------------------------
# DSL 构造
# ---------------------------------------------------------------------------
class TestStage:
    def test_minimal(self):
        item = stage("plan", agent="planner")
        assert item == {"stage": "plan", "agent": "planner"}

    def test_full_fields(self):
        item = stage(
            "gen",
            agent="generator",
            depends_on=["plan"],
            input=["a.md", "b.md"],
            output="out.md",
            gate=True,
            when="plan.ok == true",
            retry=2,
            on_error="continue",
        )
        assert item["stage"] == "gen"
        assert item["agent"] == "generator"
        assert item["depends_on"] == ["plan"]
        assert item["input"] == ["a.md", "b.md"]
        assert item["output"] == "out.md"
        assert item["gate"] is True
        assert item["when"] == "plan.ok == true"
        assert item["retry"] == 2
        assert item["on_error"] == "continue"

    def test_missing_name(self):
        with pytest.raises(ValueError):
            stage("", agent="a")

    def test_missing_agent(self):
        with pytest.raises(ValueError):
            stage("s", agent="")


class TestPipeline:
    def test_to_dict_minimal(self):
        p = Pipeline()
        p.agent("a1")
        p.add(stage("s1", agent="a1"))
        data = p.to_dict()
        assert set(data.keys()) == {"agents", "flow"}
        assert data["agents"] == [{"name": "a1"}]
        assert data["flow"] == [{"stage": "s1", "agent": "a1"}]

    def test_to_dict_with_spec_and_default(self):
        p = Pipeline()
        p.spec("背景")
        p.default_on_error("continue")
        p.agent("a1", working_dir=".", task="做事")
        p.add(stage("s1", agent="a1"))
        data = p.to_dict()
        assert data["spec"] == "背景"
        assert data["default_on_error"] == "continue"
        assert data["agents"] == [{"name": "a1", "working_dir": ".", "task": "做事"}]

    def test_duplicate_stage(self):
        p = Pipeline()
        p.add(stage("s1", agent="a1"))
        with pytest.raises(ValueError):
            p.add(stage("s1", agent="a1"))

    def test_duplicate_agent(self):
        p = Pipeline()
        p.agent("a1")
        with pytest.raises(ValueError):
            p.agent("a1")

    def test_unknown_agent_field_ignored(self):
        p = Pipeline()
        p.agent("a1", unknown_field="x")
        assert p.to_dict()["agents"] == [{"name": "a1"}]

    def test_add_requires_dict(self):
        p = Pipeline()
        bad = cast("dict", "not-a-dict")
        with pytest.raises(TypeError):
            p.add(bad)


# ---------------------------------------------------------------------------
# 关键不变量：DSL 结构与等价 YAML 经 _build_dag 结果逐字段一致
# ---------------------------------------------------------------------------
class TestDslEquivalentToYaml:
    def test_build_dag_equivalence(self, tool):
        # YAML 等价结构
        yaml_orch = {
            "agents": [
                {"name": "planner", "working_dir": ".", "task": "规划"},
                {"name": "generator", "working_dir": ".", "task": "生成"},
            ],
            "flow": [
                {"stage": "plan", "agent": "planner", "output": "plan.md"},
                {"stage": "gen", "agent": "generator", "input": "plan.md"},
            ],
            "default_on_error": "abort",
        }

        # DSL 等价结构
        p = Pipeline()
        p.default_on_error("abort")
        p.agent("planner", working_dir=".", task="规划")
        p.agent("generator", working_dir=".", task="生成")
        p.add(stage("plan", agent="planner", output="plan.md"))
        p.add(stage("gen", agent="generator", input="plan.md"))
        dsl_orch = p.to_dict()

        agents_by_name = {a["name"]: a for a in yaml_orch["agents"]}
        r_yaml = tool._build_dag(
            yaml_orch["flow"], agents_by_name, yaml_orch["default_on_error"]
        )
        r_dsl = tool._build_dag(
            dsl_orch["flow"], agents_by_name, dsl_orch["default_on_error"]
        )

        assert r_yaml.get("success") is True
        assert r_dsl.get("success") is True
        assert r_dsl["nodes"] == r_yaml["nodes"]


# ---------------------------------------------------------------------------
# 加载器
# ---------------------------------------------------------------------------
class TestLoader:
    def _write(self, tmp_path, name, content):
        f = tmp_path / name
        f.write_text(textwrap.dedent(content), encoding="utf-8")
        return f

    def test_load_yaml(self, tmp_path):
        f = self._write(
            tmp_path,
            "orch.yaml",
            """
            agents:
              - name: a1
            flow:
              - stage: s1
                agent: a1
            """,
        )
        data = load_orchestration(f)
        assert data["agents"] == [{"name": "a1"}]
        assert data["flow"] == [{"stage": "s1", "agent": "a1"}]

    def test_load_flow(self, tmp_path):
        f = self._write(
            tmp_path,
            "orch.flow",
            """
            from jarvis.jarvis_tools.orchestration_dsl import Pipeline, stage
            pipeline = Pipeline()
            pipeline.agent("a1")
            pipeline.add(stage("s1", agent="a1"))
            """,
        )
        data = load_orchestration(f)
        assert set(data.keys()) == {"agents", "flow"}
        assert data["agents"] == [{"name": "a1"}]
        assert data["flow"] == [{"stage": "s1", "agent": "a1"}]

    def test_yaml_and_flow_isomorphic(self, tmp_path):
        yaml_f = self._write(
            tmp_path,
            "a.yaml",
            """
            agents:
              - name: a1
            flow:
              - stage: s1
                agent: a1
            """,
        )
        flow_f = self._write(
            tmp_path,
            "a.flow",
            """
            from jarvis.jarvis_tools.orchestration_dsl import Pipeline, stage
            pipeline = Pipeline()
            pipeline.agent("a1")
            pipeline.add(stage("s1", agent="a1"))
            """,
        )
        assert load_orchestration(yaml_f) == load_orchestration(flow_f)

    def test_missing_file(self, tmp_path):
        with pytest.raises(ValueError):
            load_orchestration(tmp_path / "nope.yaml")

    def test_unsupported_suffix(self, tmp_path):
        f = self._write(tmp_path, "x.txt", "hello")
        with pytest.raises(ValueError):
            load_orchestration(f)

    def test_flow_missing_pipeline_var(self, tmp_path):
        f = self._write(
            tmp_path,
            "bad.flow",
            """
            x = 1
            """,
        )
        with pytest.raises(ValueError):
            load_orchestration(f)

    def test_flow_syntax_error(self, tmp_path):
        f = self._write(tmp_path, "syn.flow", "def (:\n")
        with pytest.raises(ValueError):
            load_orchestration(f)
