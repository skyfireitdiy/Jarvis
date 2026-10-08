# -*- coding: utf-8 -*-
"""pipeline_runner（内置多 Agent 编排执行引擎）测试。

覆盖：
1. DAG 构建：线性兼容（depends_on 缺省=上一个 stage）、input 单字符串转列表、
   并行依赖、重复 stage 名、未定义 agent、环检测；
2. when 受限表达式解析：比较、逻辑、引用上游字段、非法表达式；
3. 并行调度：依赖就绪才执行、on_error 三种策略（abort/continue/skip_dependents）、
   retry 重试、门禁停住。

不依赖真实 gateway/agent：mock GatewayManagerTool 与 status_file。
"""

import json
from pathlib import Path

import pytest

from jarvis.jarvis_tools.gateway_manager import GatewayManagerTool
from jarvis.jarvis_tools.pipeline_runner import PipelineRunnerTool


@pytest.fixture
def tool():
    return PipelineRunnerTool()


# ---------------------------------------------------------------------------
# DAG 构建
# ---------------------------------------------------------------------------
class TestBuildDag:
    def test_linear_backward_compat(self, tool):
        """depends_on 缺省 = 上一个 stage（老线性编排零改动）。"""
        flow = [
            {"stage": "planner", "agent": "a1", "output": "plan.md"},
            {"stage": "generator", "agent": "a2", "input": "plan.md"},
            {"stage": "validator", "agent": "a3", "input": "plan.md"},
        ]
        agents = {"a1": {}, "a2": {}, "a3": {}}
        r = tool._build_dag(flow, agents)
        assert r["success"] is True
        nodes = r["nodes"]
        assert nodes[0]["depends_on"] == []
        assert nodes[1]["depends_on"] == ["planner"]
        assert nodes[2]["depends_on"] == ["generator"]

    def test_input_string_to_list(self, tool):
        """input 单字符串自动转单元素列表。"""
        flow = [{"stage": "s1", "agent": "a1", "input": ".df/plan.md"}]
        r = tool._build_dag(flow, {"a1": {}})
        assert r["nodes"][0]["input"] == [".df/plan.md"]

    def test_input_list_preserved(self, tool):
        """input 多输入列表保留。"""
        flow = [
            {"stage": "s1", "agent": "a1", "input": ["a.md", "b.md"]},
        ]
        r = tool._build_dag(flow, {"a1": {}})
        assert r["nodes"][0]["input"] == ["a.md", "b.md"]

    def test_parallel_dependencies(self, tool):
        """并行 DAG：多节点依赖同一上游。"""
        flow = [
            {"stage": "s1", "agent": "a1"},
            {"stage": "s2", "agent": "a2", "depends_on": ["s1"]},
            {"stage": "s3", "agent": "a3", "depends_on": ["s1"]},
            {"stage": "s4", "agent": "a4", "depends_on": ["s2", "s3"]},
        ]
        agents = {"a1": {}, "a2": {}, "a3": {}, "a4": {}}
        r = tool._build_dag(flow, agents)
        assert r["success"] is True
        nodes = {n["stage"]: n for n in r["nodes"]}
        assert nodes["s1"]["depends_on"] == []
        assert nodes["s2"]["depends_on"] == ["s1"]
        assert nodes["s3"]["depends_on"] == ["s1"]
        assert sorted(nodes["s4"]["depends_on"]) == ["s2", "s3"]

    def test_duplicate_stage_name(self, tool):
        flow = [
            {"stage": "s1", "agent": "a1"},
            {"stage": "s1", "agent": "a2"},
        ]
        r = tool._build_dag(flow, {"a1": {}, "a2": {}})
        assert r["success"] is False
        assert "重复" in r["error"]

    def test_undefined_agent(self, tool):
        flow = [{"stage": "s1", "agent": "ghost"}]
        r = tool._build_dag(flow, {"a1": {}})
        assert r["success"] is False
        assert "未定义" in r["error"]

    def test_dependency_not_exist(self, tool):
        flow = [
            {"stage": "s1", "agent": "a1"},
            {"stage": "s2", "agent": "a2", "depends_on": ["nope"]},
        ]
        r = tool._build_dag(flow, {"a1": {}, "a2": {}})
        assert r["success"] is False
        assert "不存在" in r["error"]

    def test_cycle_detected(self, tool):
        """环检测：Kahn 拓扑排序检测到环。"""
        # 直接构造已解析节点（绕过 depends_on 前向引用校验），验证 _topo_sort 环检测
        nodes = [
            {
                "stage": "y",
                "agent": "a1",
                "depends_on": ["x"],
                "input": [],
                "output": "",
                "gate": False,
                "when": None,
                "retry": 0,
                "on_error": "abort",
            },
            {
                "stage": "x",
                "agent": "a2",
                "depends_on": ["y"],
                "input": [],
                "output": "",
                "gate": False,
                "when": None,
                "retry": 0,
                "on_error": "abort",
            },
        ]
        assert tool._topo_sort(nodes) is None

    def test_topo_sort_order(self, tool):
        """拓扑排序：依赖在前。"""
        flow = [
            {"stage": "s1", "agent": "a1"},
            {"stage": "s2", "agent": "a2", "depends_on": ["s1"]},
            {"stage": "s3", "agent": "a3", "depends_on": ["s1"]},
        ]
        r = tool._build_dag(flow, {"a1": {}, "a2": {}, "a3": {}})
        order = tool._topo_sort(r["nodes"])
        assert order is not None
        assert order[0]["stage"] == "s1"
        assert set(order[1]["stage"]) == {"s2", "s3"} or {
            order[1]["stage"],
            order[2]["stage"],
        } == {"s2", "s3"}


# ---------------------------------------------------------------------------
# when 受限表达式解析
# ---------------------------------------------------------------------------
class TestEvalWhen:
    def _results(self):
        return {
            "prev": {"result": {"status": "completed", "score": 5, "ok": True}},
        }

    def test_eq(self, tool):
        assert tool._eval_when('prev.status == "completed"', self._results())[0] is True
        assert tool._eval_when('prev.status == "failed"', self._results())[0] is False

    def test_ne(self, tool):
        assert tool._eval_when('prev.status != "failed"', self._results())[0] is True

    def test_numeric_compare(self, tool):
        assert tool._eval_when("prev.score >= 5", self._results())[0] is True
        assert tool._eval_when("prev.score > 5", self._results())[0] is False
        assert tool._eval_when("prev.score < 10", self._results())[0] is True

    def test_and_or(self, tool):
        assert (
            tool._eval_when(
                'prev.score >= 5 && prev.status != "failed"', self._results()
            )[0]
            is True
        )
        assert (
            tool._eval_when(
                'prev.score < 5 || prev.status == "completed"', self._results()
            )[0]
            is True
        )

    def test_not(self, tool):
        assert tool._eval_when("!false", self._results())[0] is True
        assert tool._eval_when("!true", self._results())[0] is False

    def test_boolean_field(self, tool):
        assert tool._eval_when("prev.ok", self._results())[0] is True

    def test_invalid_expr(self, tool):
        ok, err = tool._eval_when("prev.score >", self._results())
        assert ok is False
        assert err


# ---------------------------------------------------------------------------
# 并行调度（mock _run_stage）
# ---------------------------------------------------------------------------
class TestSchedule:
    def _nodes(self):
        return [
            {
                "stage": "s1",
                "agent": "a1",
                "depends_on": [],
                "input": [],
                "output": "",
                "gate": False,
                "when": None,
                "retry": 0,
                "on_error": "abort",
            },
            {
                "stage": "s2",
                "agent": "a2",
                "depends_on": ["s1"],
                "input": [],
                "output": "",
                "gate": False,
                "when": None,
                "retry": 0,
                "on_error": "abort",
            },
        ]

    def _base_kwargs(self, tool, nodes):
        return dict(
            nodes=nodes,
            agent_map={n["stage"]: f"id_{n['stage']}" for n in nodes},
            agents_by_name={"a1": {}, "a2": {}},
            work_dir=Path("."),
            artifact_dir=Path(".df"),
            spec_summary="",
            approve=False,
            max_workers=4,
        )

    def test_all_completed(self, tool, monkeypatch):
        calls = []

        def fake_run_stage(node, agent_id, agents_by_name, work_dir, artifact_dir, spec_summary, approve):
            calls.append(node["stage"])
            return {
                "stage": node["stage"],
                "status": "completed",
                "output": "",
                "result": {},
                "error": "",
                "gate_blocked": False,
                "approval_path": "",
            }

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        nodes = self._nodes()
        r = tool._schedule(**self._base_kwargs(tool, nodes))
        assert r["success"] is True
        assert calls[0] == "s1"  # s1 先执行
        assert set(calls) == {"s1", "s2"}

    def test_abort_on_failure(self, tool, monkeypatch):
        """on_error=abort：任一失败立即中止。"""

        def fake_run_stage(node, *args, **kwargs):
            if node["stage"] == "s1":
                return {
                    "stage": "s1",
                    "status": "failed",
                    "output": "",
                    "result": {},
                    "error": "boom",
                    "gate_blocked": False,
                    "approval_path": "",
                }
            return {
                "stage": node["stage"],
                "status": "completed",
                "output": "",
                "result": {},
                "error": "",
                "gate_blocked": False,
                "approval_path": "",
            }

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        nodes = self._nodes()
        r = tool._schedule(**self._base_kwargs(tool, nodes))
        assert r["success"] is False
        assert "s1" in r["stderr"]

    def test_continue_on_failure(self, tool, monkeypatch):
        """on_error=continue：失败但不中止，依赖它的节点被跳过。"""
        nodes = self._nodes()
        nodes[0]["on_error"] = "continue"
        nodes[1]["on_error"] = "continue"

        def fake_run_stage(node, *args, **kwargs):
            if node["stage"] == "s1":
                return {
                    "stage": "s1",
                    "status": "failed",
                    "output": "",
                    "result": {},
                    "error": "boom",
                    "gate_blocked": False,
                    "approval_path": "",
                }
            raise AssertionError("s2 不应执行（依赖失败）")

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        r = tool._schedule(**self._base_kwargs(tool, nodes))
        assert r["success"] is False
        assert "s1" in r["stderr"]

    def test_skip_dependents(self, tool, monkeypatch):
        """on_error=skip_dependents：失败后依赖节点被跳过。"""
        nodes = self._nodes()
        nodes[0]["on_error"] = "skip_dependents"
        nodes[1]["on_error"] = "skip_dependents"

        def fake_run_stage(node, *args, **kwargs):
            if node["stage"] == "s1":
                return {
                    "stage": "s1",
                    "status": "failed",
                    "output": "",
                    "result": {},
                    "error": "boom",
                    "gate_blocked": False,
                    "approval_path": "",
                }
            raise AssertionError("s2 不应执行（依赖失败）")

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        r = tool._schedule(**self._base_kwargs(tool, nodes))
        assert r["success"] is False

    def test_retry(self, tool, monkeypatch):
        """retry：失败后重试，重试成功则完成。"""
        nodes = self._nodes()
        nodes[0]["retry"] = 2
        attempt = {"n": 0}

        def fake_run_stage(node, *args, **kwargs):
            if node["stage"] == "s1":
                attempt["n"] += 1
                if attempt["n"] < 2:
                    return {
                        "stage": "s1",
                        "status": "failed",
                        "output": "",
                        "result": {},
                        "error": "transient",
                        "gate_blocked": False,
                        "approval_path": "",
                    }
            return {
                "stage": node["stage"],
                "status": "completed",
                "output": "",
                "result": {},
                "error": "",
                "gate_blocked": False,
                "approval_path": "",
            }

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        r = tool._schedule(**self._base_kwargs(tool, nodes))
        assert r["success"] is True
        assert attempt["n"] == 2

    def test_gate_blocks(self, tool, monkeypatch):
        """门禁：approve=false 时停住并返回审批路径。"""
        nodes = self._nodes()
        nodes[1]["gate"] = True

        def fake_run_stage(node, *args, **kwargs):
            if node["stage"] == "s1":
                return {
                    "stage": "s1",
                    "status": "completed",
                    "output": "",
                    "result": {},
                    "error": "",
                    "gate_blocked": False,
                    "approval_path": "",
                }
            return {
                "stage": "s2",
                "status": "completed",
                "output": "report.md",
                "result": {},
                "error": "",
                "gate_blocked": True,
                "approval_path": "report.md",
            }

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        r = tool._schedule(**self._base_kwargs(tool, nodes))
        assert r["success"] is True
        assert "人工审批" in r["stdout"]

    def test_when_skip(self, tool, monkeypatch):
        """when 条件不满足时跳过节点。"""
        nodes = self._nodes()
        nodes[1]["when"] = 'prev.score < 0'  # 无 prev 结果，视为不满足
        executed = []

        def fake_run_stage(node, *args, **kwargs):
            executed.append(node["stage"])
            return {
                "stage": node["stage"],
                "status": "completed",
                "output": "",
                "result": {},
                "error": "",
                "gate_blocked": False,
                "approval_path": "",
            }

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        r = tool._schedule(**self._base_kwargs(tool, nodes))
        assert r["success"] is True
        assert executed == ["s1"]  # s2 因 when 不满足被跳过


# ---------------------------------------------------------------------------
# _run_stage（mock send_to_agent 与 status_file）
# ---------------------------------------------------------------------------
class TestRunStage:
    def test_success_with_output(self, tool, monkeypatch, tmp_path):
        """成功且产物落盘。"""
        work_dir = tmp_path
        artifact_dir = work_dir / ".df"
        artifact_dir.mkdir()
        (work_dir / "plan.md").write_text("plan", encoding="utf-8")

        node = {
            "stage": "s1",
            "agent": "a1",
            "depends_on": [],
            "input": [],
            "output": "plan.md",
            "gate": False,
            "when": None,
            "retry": 0,
            "on_error": "abort",
        }
        agents_by_name = {"a1": {"task": "规划"}}

        class FakeGW:
            def _send_to_agent(self, agent_id, message, wait=False, status_file: str = ""):
                # 模拟阶段 Agent 写 status_file
                Path(status_file).write_text(
                    json.dumps({"status": "completed", "output": "plan.md"}),
                    encoding="utf-8",
                )
                return {"success": True, "stdout": "", "stderr": ""}

        monkeypatch.setattr(GatewayManagerTool, "_send_to_agent", FakeGW()._send_to_agent)
        r = tool._run_stage(
            node, "id_s1", agents_by_name, work_dir, artifact_dir, "", False
        )
        assert r["status"] == "completed"
        assert r["output"] == "plan.md"

    def test_output_missing(self, tool, monkeypatch, tmp_path):
        """声明产物未落盘 → failed。"""
        work_dir = tmp_path
        artifact_dir = work_dir / ".df"
        artifact_dir.mkdir()

        node = {
            "stage": "s1",
            "agent": "a1",
            "depends_on": [],
            "input": [],
            "output": "missing.md",
            "gate": False,
            "when": None,
            "retry": 0,
            "on_error": "abort",
        }
        agents_by_name = {"a1": {"task": "规划"}}

        class FakeGW:
            def _send_to_agent(self, agent_id, message, wait=False, status_file: str = ""):
                Path(status_file).write_text(
                    json.dumps({"status": "completed", "output": "missing.md"}),
                    encoding="utf-8",
                )
                return {"success": True, "stdout": "", "stderr": ""}

        monkeypatch.setattr(GatewayManagerTool, "_send_to_agent", FakeGW()._send_to_agent)
        r = tool._run_stage(
            node, "id_s1", agents_by_name, work_dir, artifact_dir, "", False
        )
        assert r["status"] == "failed"
        assert "未落盘" in r["error"]

    def test_send_failure(self, tool, monkeypatch, tmp_path):
        """send_to_agent 失败 → failed。"""
        work_dir = tmp_path
        artifact_dir = work_dir / ".df"
        artifact_dir.mkdir()

        node = {
            "stage": "s1",
            "agent": "a1",
            "depends_on": [],
            "input": [],
            "output": "",
            "gate": False,
            "when": None,
            "retry": 0,
            "on_error": "abort",
        }
        agents_by_name = {"a1": {"task": "规划"}}

        class FakeGW:
            def _send_to_agent(self, agent_id, message, wait=False, status_file=None):
                return {"success": False, "stdout": "", "stderr": "gateway down"}

        monkeypatch.setattr(GatewayManagerTool, "_send_to_agent", FakeGW()._send_to_agent)
        r = tool._run_stage(
            node, "id_s1", agents_by_name, work_dir, artifact_dir, "", False
        )
        assert r["status"] == "failed"
        assert "gateway down" in r["error"]
