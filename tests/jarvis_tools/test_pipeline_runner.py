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

    def test_default_on_error(self, tool):
        """on_error 缺省回退到编排文件顶层 default_on_error。"""
        flow = [
            {"stage": "s1", "agent": "a1"},
            {"stage": "s2", "agent": "a2", "on_error": "continue"},
        ]
        r = tool._build_dag(
            flow, {"a1": {}, "a2": {}}, default_on_error="skip_dependents"
        )
        nodes = {n["stage"]: n for n in r["nodes"]}
        assert nodes["s1"]["on_error"] == "skip_dependents"  # 回退到全局默认
        assert nodes["s2"]["on_error"] == "continue"  # 阶段级覆盖

    def test_default_on_error_invalid_falls_back_abort(self, tool):
        """非法 default_on_error 回退为 abort。"""
        flow = [{"stage": "s1", "agent": "a1"}]
        r = tool._build_dag(flow, {"a1": {}}, default_on_error="bogus")
        assert r["nodes"][0]["on_error"] == "abort"

    def test_duplicate_output_rejected(self, tool):
        """多个阶段声明相同产物路径 → 报错。"""
        flow = [
            {"stage": "s1", "agent": "a1", "output": ".df/x.md"},
            {"stage": "s2", "agent": "a2", "output": ".df/x.md"},
        ]
        r = tool._build_dag(flow, {"a1": {}, "a2": {}})
        assert r["success"] is False
        assert "唯一" in r["error"] or "相同" in r["error"]

    def test_unique_output_ok(self, tool):
        """不同产物路径正常通过。"""
        flow = [
            {"stage": "s1", "agent": "a1", "output": ".df/a.md"},
            {"stage": "s2", "agent": "a2", "output": ".df/b.md"},
        ]
        r = tool._build_dag(flow, {"a1": {}, "a2": {}})
        assert r["success"] is True


# ---------------------------------------------------------------------------
# loop 折叠进 DAG
# ---------------------------------------------------------------------------
class TestBuildDagLoop:
    def test_loop_folds_body_stages(self, tool):
        """body 内 stage 折叠进 loop 节点，顶层不再单独出现。"""
        flow = [
            {"stage": "setup", "agent": "a1", "output": ".df/setup.md"},
            {"stage": "write", "agent": "a2", "depends_on": ["setup"]},
            {"stage": "check", "agent": "a3", "depends_on": ["write"]},
            {
                "loop": "refine",
                "body": ["write", "check"],
                "until": 'contains(file("check.md"), "OK")',
                "max_iterations": 3,
            },
        ]
        agents = {"a1": {}, "a2": {}, "a3": {}}
        r = tool._build_dag(flow, agents)
        assert r["success"] is True
        stages = {n["stage"] for n in r["nodes"]}
        assert stages == {"setup", "refine"}
        loop_node = next(n for n in r["nodes"] if n["stage"] == "refine")
        assert loop_node["kind"] == "loop"
        assert loop_node["depends_on"] == ["setup"]
        assert loop_node["until"] == 'contains(file("check.md"), "OK")'
        assert loop_node["max_iterations"] == 3
        assert [b["stage"] for b in loop_node["body_stages"]] == ["write", "check"]

    def test_loop_body_internal_dep_kept(self, tool):
        """body 内 stage 之间的依赖保留在 body_stages 内。"""
        flow = [
            {"stage": "write", "agent": "a1"},
            {"stage": "check", "agent": "a2", "depends_on": ["write"]},
            {"loop": "L", "body": ["write", "check"], "until": "x", "max_iterations": 2},
        ]
        r = tool._build_dag(flow, {"a1": {}, "a2": {}})
        loop_node = next(n for n in r["nodes"] if n["stage"] == "L")
        body = {b["stage"]: b for b in loop_node["body_stages"]}
        assert body["write"]["depends_on"] == []
        assert body["check"]["depends_on"] == ["write"]

    def test_downstream_rewritten_to_loop(self, tool):
        """顶层 stage 依赖 body 内 stage → 改写为依赖 loop 节点。"""
        flow = [
            {"stage": "write", "agent": "a1"},
            {"stage": "check", "agent": "a2", "depends_on": ["write"]},
            {"loop": "L", "body": ["write", "check"], "until": "x", "max_iterations": 2},
            {"stage": "publish", "agent": "a3", "depends_on": ["check"]},
        ]
        r = tool._build_dag(flow, {"a1": {}, "a2": {}, "a3": {}})
        assert r["success"] is True
        pub = next(n for n in r["nodes"] if n["stage"] == "publish")
        assert pub["depends_on"] == ["L"]

    def test_body_unknown_stage(self, tool):
        flow = [{"loop": "L", "body": ["ghost"], "until": "x", "max_iterations": 2}]
        r = tool._build_dag(flow, {})
        assert r["success"] is False
        assert "不存在" in r["error"]

    def test_body_stage_depends_outside_rejected(self, tool):
        """body 内 stage 依赖 body 外 stage → loop 节点继承该外部依赖。"""
        flow = [
            {"stage": "setup", "agent": "a1"},
            {"stage": "write", "agent": "a2", "depends_on": ["setup"]},
            {"loop": "L", "body": ["write"], "until": "x", "max_iterations": 2},
        ]
        r = tool._build_dag(flow, {"a1": {}, "a2": {}})
        assert r["success"] is True
        loop_node = next(n for n in r["nodes"] if n["stage"] == "L")
        assert loop_node["depends_on"] == ["setup"]

    def test_body_stage_depends_other_loop_rejected(self, tool):
        """body 内 stage 依赖另一个 loop 的 stage → 报错。"""
        flow = [
            {"stage": "s1", "agent": "a1"},
            {"loop": "L1", "body": ["s1"], "until": "x", "max_iterations": 2},
            {"stage": "s2", "agent": "a2", "depends_on": ["s1"]},
            {"loop": "L2", "body": ["s2"], "until": "y", "max_iterations": 2},
        ]
        r = tool._build_dag(flow, {"a1": {}, "a2": {}})
        assert r["success"] is False
        assert "其它 loop" in r["error"]

    def test_loop_name_conflicts_with_stage(self, tool):
        flow = [
            {"stage": "s1", "agent": "a1"},
            {"loop": "s1", "body": ["s1"], "until": "x", "max_iterations": 2},
        ]
        r = tool._build_dag(flow, {"a1": {}})
        assert r["success"] is False
        assert "冲突" in r["error"] or "重复" in r["error"]
    def test_duplicate_loop_name(self, tool):
        flow = [
            {"stage": "s1", "agent": "a1"},
            {"loop": "L", "body": ["s1"], "until": "x", "max_iterations": 2},
            {"loop": "L", "body": ["s1"], "until": "y", "max_iterations": 2},
        ]
        r = tool._build_dag(flow, {"a1": {}})
        assert r["success"] is False
        assert "重复" in r["error"]

    def test_loop_missing_until(self, tool):
        flow = [
            {"stage": "s1", "agent": "a1"},
            {"loop": "L", "body": ["s1"], "max_iterations": 2},
        ]
        r = tool._build_dag(flow, {"a1": {}})
        assert r["success"] is False
        assert "until" in r["error"]

    def test_loop_bad_max_iterations(self, tool):
        flow = [
            {"stage": "s1", "agent": "a1"},
            {"loop": "L", "body": ["s1"], "until": "x", "max_iterations": 0},
        ]
        r = tool._build_dag(flow, {"a1": {}})
        assert r["success"] is False
        assert "max_iterations" in r["error"]

    def test_no_loop_output_unchanged(self, tool):
        """无 loop 时节点字段与改动前一致（无 kind 等额外字段）。"""
        flow = [
            {"stage": "s1", "agent": "a1", "output": ".df/a.md"},
            {"stage": "s2", "agent": "a2", "depends_on": ["s1"]},
        ]
        r = tool._build_dag(flow, {"a1": {}, "a2": {}})
        assert r["success"] is True
        for n in r["nodes"]:
            assert set(n.keys()) == {
                "stage",
                "agent",
                "depends_on",
                "input",
                "output",
                "gate",
                "when",
                "retry",
                "on_error",
            }


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

        def fake_run_stage(
            node,
            agent_id,
            agents_by_name,
            work_dir,
            artifact_dir,
            spec_summary,
            approve,
        ):
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
        nodes[1]["when"] = "prev.score < 0"  # 无 prev 结果，视为不满足
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
# loop 执行与 until 求值
# ---------------------------------------------------------------------------
class TestLoop:
    def _loop_node(self, body, until, max_iterations=5, on_error="abort"):
        return {
            "stage": "L",
            "kind": "loop",
            "agent": None,
            "depends_on": [],
            "input": [],
            "output": "",
            "gate": False,
            "when": None,
            "retry": 0,
            "on_error": on_error,
            "until": until,
            "max_iterations": max_iterations,
            "body_stages": body,
        }

    def _body(self, name, output=""):
        return {
            "stage": name,
            "agent": "a1",
            "depends_on": [],
            "input": [],
            "output": output,
            "gate": False,
            "when": None,
            "retry": 0,
            "on_error": "abort",
        }

    def _kwargs(self, node):
        return dict(
            node=node,
            agent_map={"b1": "id_b1", "b2": "id_b2"},
            agents_by_name={"a1": {}},
            work_dir=Path("."),
            artifact_dir=Path(".df"),
            spec_summary="",
            approve=False,
            pipeline_id="p1",
        )

    def test_until_satisfied_first_iteration(self, tool, monkeypatch):
        """第一轮 until 满足 → 只跑一轮。"""
        runs = []

        def fake_run_stage(node, *args, **kwargs):
            runs.append(node["stage"])
            return {
                "stage": node["stage"],
                "status": "completed",
                "output": "",
                "result": {"ok": True},
                "error": "",
                "gate_blocked": False,
                "approval_path": "",
            }

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        node = self._loop_node([self._body("b1")], "b1.ok == true", max_iterations=3)
        r = tool._run_loop(**self._kwargs(node))
        assert r["status"] == "completed"
        assert r["result"]["iterations"] == 1
        assert r["result"]["until_satisfied"] is True
        assert runs == ["b1"]

    def test_until_satisfied_after_iterations(self, tool, monkeypatch):
        """until 第 3 轮才满足 → 跑 3 轮。"""
        counter = {"n": 0}

        def fake_run_stage(node, *args, **kwargs):
            counter["n"] += 1
            return {
                "stage": node["stage"],
                "status": "completed",
                "output": "",
                "result": {"count": counter["n"]},
                "error": "",
                "gate_blocked": False,
                "approval_path": "",
            }

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        node = self._loop_node([self._body("b1")], "b1.count >= 3", max_iterations=5)
        r = tool._run_loop(**self._kwargs(node))
        assert r["status"] == "completed"
        assert r["result"]["iterations"] == 3
        assert r["result"]["until_satisfied"] is True

    def test_max_iterations_reached(self, tool, monkeypatch):
        """until 永不满足 → 跑满上限，标记未满足。"""

        def fake_run_stage(node, *args, **kwargs):
            return {
                "stage": node["stage"],
                "status": "completed",
                "output": "",
                "result": {"ok": False},
                "error": "",
                "gate_blocked": False,
                "approval_path": "",
            }

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        node = self._loop_node([self._body("b1")], "b1.ok == true", max_iterations=3)
        r = tool._run_loop(**self._kwargs(node))
        assert r["status"] == "completed"
        assert r["result"]["iterations"] == 3
        assert r["result"]["until_satisfied"] is False

    def test_body_stage_failure(self, tool, monkeypatch):
        """body 内阶段失败 → loop 失败。"""

        def fake_run_stage(node, *args, **kwargs):
            return {
                "stage": node["stage"],
                "status": "failed",
                "output": "",
                "result": {},
                "error": "boom",
                "gate_blocked": False,
                "approval_path": "",
            }

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        node = self._loop_node([self._body("b1")], "b1.ok == true", max_iterations=3)
        r = tool._run_loop(**self._kwargs(node))
        assert r["status"] == "failed"
        assert "boom" in r["error"]

    def test_body_internal_order(self, tool, monkeypatch):
        """body 内依赖顺序：b1 先于 b2。"""
        order = []

        def fake_run_stage(node, *args, **kwargs):
            order.append(node["stage"])
            return {
                "stage": node["stage"],
                "status": "completed",
                "output": "",
                "result": {"ok": True},
                "error": "",
                "gate_blocked": False,
                "approval_path": "",
            }

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        b1 = self._body("b1")
        b2 = self._body("b2")
        b2["depends_on"] = ["b1"]
        node = self._loop_node([b2, b1], "b1.ok == true", max_iterations=1)
        tool._run_loop(**self._kwargs(node))
        assert order == ["b1", "b2"]

    def test_schedule_dispatches_loop(self, tool, monkeypatch):
        """_schedule 对 loop 节点调用 _run_loop 而非 _run_stage。"""
        called = {"loop": 0, "stage": 0}

        def fake_run_loop(*args, **kwargs):
            called["loop"] += 1
            return {
                "stage": "L",
                "status": "completed",
                "output": "",
                "result": {},
                "error": "",
                "gate_blocked": False,
                "approval_path": "",
            }

        def fake_run_stage(*args, **kwargs):
            called["stage"] += 1
            return {
                "stage": "s1",
                "status": "completed",
                "output": "",
                "result": {},
                "error": "",
                "gate_blocked": False,
                "approval_path": "",
            }

        monkeypatch.setattr(tool, "_run_loop", fake_run_loop)
        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        nodes = [self._loop_node([self._body("b1")], "b1.ok == true")]
        r = tool._schedule(
            nodes=nodes,
            agent_map={"b1": "id_b1"},
            agents_by_name={"a1": {}},
            work_dir=Path("."),
            artifact_dir=Path(".df"),
            spec_summary="",
            approve=False,
            max_workers=2,
        )
        assert r["success"] is True
        assert called["loop"] == 1
        assert called["stage"] == 0


class TestEvalUntil:
    def test_file_contains_true(self, tool, tmp_path):
        (tmp_path / "report.md").write_text("all tests PASS", encoding="utf-8")
        ok, err = tool._eval_until('contains(file("report.md"), "PASS")', {}, tmp_path)
        assert ok is True
        assert err == ""

    def test_file_contains_false(self, tool, tmp_path):
        (tmp_path / "report.md").write_text("FAIL", encoding="utf-8")
        ok, _ = tool._eval_until('contains(file("report.md"), "PASS")', {}, tmp_path)
        assert ok is False

    def test_file_missing_empty(self, tool, tmp_path):
        ok, _ = tool._eval_until('contains(file("nope.md"), "PASS")', {}, tmp_path)
        assert ok is False

    def test_file_path_traversal_blocked(self, tool, tmp_path):
        """越界路径（../）读取失败，返回空串。"""
        secret = tmp_path.parent / "secret_until.txt"
        secret.write_text("PASS", encoding="utf-8")
        ok, _ = tool._eval_until(
            'contains(file("../secret_until.txt"), "PASS")', {}, tmp_path
        )
        assert ok is False

    def test_until_stage_ref(self, tool, tmp_path):
        results = {"b1": {"result": {"pass_rate": 0.95}}}
        ok, _ = tool._eval_until("b1.pass_rate >= 0.9", results, tmp_path)
        assert ok is True

    def test_contains_with_stage_ref(self, tool, tmp_path):
        results = {"b1": {"result": {"verdict": "OK"}}}
        ok, _ = tool._eval_until('contains(b1.verdict, "OK")', results, tmp_path)
        assert ok is True

    def test_file_size_capped(self, tool, tmp_path):
        """超大文件读取被截断，仍返回内容（不抛异常）。"""
        (tmp_path / "big.md").write_text("x" * (1024 * 1024 + 100), encoding="utf-8")
        ok, err = tool._eval_until('contains(file("big.md"), "x")', {}, tmp_path)
        assert ok is True
        assert err == ""


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
            def _send_to_agent(
                self, agent_id, message, wait=False, status_file: str = ""
            ):
                # 模拟阶段 Agent 写 status_file
                Path(status_file).write_text(
                    json.dumps({"status": "completed", "output": "plan.md"}),
                    encoding="utf-8",
                )
                return {"success": True, "stdout": "", "stderr": ""}

        monkeypatch.setattr(
            GatewayManagerTool, "_send_to_agent", FakeGW()._send_to_agent
        )
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
            def _send_to_agent(
                self, agent_id, message, wait=False, status_file: str = ""
            ):
                Path(status_file).write_text(
                    json.dumps({"status": "completed", "output": "missing.md"}),
                    encoding="utf-8",
                )
                return {"success": True, "stdout": "", "stderr": ""}

        monkeypatch.setattr(
            GatewayManagerTool, "_send_to_agent", FakeGW()._send_to_agent
        )
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

        monkeypatch.setattr(
            GatewayManagerTool, "_send_to_agent", FakeGW()._send_to_agent
        )
        r = tool._run_stage(
            node, "id_s1", agents_by_name, work_dir, artifact_dir, "", False
        )
        assert r["status"] == "failed"
        assert "gateway down" in r["error"]


# ---------------------------------------------------------------------------
# 产物 JSON 引用（when 可读产物内容）
# ---------------------------------------------------------------------------
class TestArtifactJson:
    def _node(self, output):
        return {
            "stage": "s1",
            "agent": "a1",
            "depends_on": [],
            "input": [],
            "output": output,
            "gate": False,
            "when": None,
            "retry": 0,
            "on_error": "abort",
        }

    def test_read_artifact_json_dict(self, tool, tmp_path):
        """顶层为 dict 的 JSON 产物被读取。"""
        p = tmp_path / "report.json"
        p.write_text(json.dumps({"pass_rate": 0.9, "ok": True}), encoding="utf-8")
        assert tool._read_artifact_json(p) == {"pass_rate": 0.9, "ok": True}

    def test_read_artifact_json_non_json_ext(self, tool, tmp_path):
        """非 .json 后缀不读取。"""
        p = tmp_path / "report.md"
        p.write_text(json.dumps({"a": 1}), encoding="utf-8")
        assert tool._read_artifact_json(p) == {}

    def test_read_artifact_json_non_dict(self, tool, tmp_path):
        """顶层非 dict 返回空。"""
        p = tmp_path / "list.json"
        p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        assert tool._read_artifact_json(p) == {}

    def test_read_artifact_json_invalid(self, tool, tmp_path):
        """非法 JSON 返回空且不抛异常。"""
        p = tmp_path / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        assert tool._read_artifact_json(p) == {}

    def test_read_artifact_json_missing(self, tool, tmp_path):
        """文件不存在返回空。"""
        assert tool._read_artifact_json(tmp_path / "nope.json") == {}

    def test_run_stage_merges_artifact_json(self, tool, monkeypatch, tmp_path):
        """产物 JSON 字段合并进 result，供下游 when 引用。"""
        work_dir = tmp_path
        artifact_dir = work_dir / ".df"
        artifact_dir.mkdir()
        (work_dir / "report.json").write_text(
            json.dumps({"pass_rate": 0.9, "verdict": "pass"}), encoding="utf-8"
        )

        class FakeGW:
            def _send_to_agent(
                self, agent_id, message, wait=False, status_file: str = ""
            ):
                Path(status_file).write_text(
                    json.dumps({"status": "completed"}), encoding="utf-8"
                )
                return {"success": True, "stdout": "", "stderr": ""}

        monkeypatch.setattr(
            GatewayManagerTool, "_send_to_agent", FakeGW()._send_to_agent
        )
        r = tool._run_stage(
            self._node("report.json"),
            "id_s1",
            {"a1": {"task": "审计"}},
            work_dir,
            artifact_dir,
            "",
            False,
        )
        assert r["status"] == "completed"
        assert r["result"]["pass_rate"] == 0.9
        assert r["result"]["verdict"] == "pass"
        assert r["result"]["status"] == "completed"

    def test_run_stage_status_file_wins(self, tool, monkeypatch, tmp_path):
        """status_file 字段优先于产物 JSON 同名字段。"""
        work_dir = tmp_path
        artifact_dir = work_dir / ".df"
        artifact_dir.mkdir()
        (work_dir / "report.json").write_text(
            json.dumps({"status": "artifact-status"}), encoding="utf-8"
        )

        class FakeGW:
            def _send_to_agent(
                self, agent_id, message, wait=False, status_file: str = ""
            ):
                Path(status_file).write_text(
                    json.dumps({"status": "completed"}), encoding="utf-8"
                )
                return {"success": True, "stdout": "", "stderr": ""}

        monkeypatch.setattr(
            GatewayManagerTool, "_send_to_agent", FakeGW()._send_to_agent
        )
        r = tool._run_stage(
            self._node("report.json"),
            "id_s1",
            {"a1": {"task": "审计"}},
            work_dir,
            artifact_dir,
            "",
            False,
        )
        assert r["result"]["status"] == "completed"

    def test_run_stage_non_json_output_not_merged(self, tool, monkeypatch, tmp_path):
        """非 JSON 产物不合并，result 仅含 status_file 内容。"""
        work_dir = tmp_path
        artifact_dir = work_dir / ".df"
        artifact_dir.mkdir()
        (work_dir / "plan.md").write_text("hello", encoding="utf-8")

        class FakeGW:
            def _send_to_agent(
                self, agent_id, message, wait=False, status_file: str = ""
            ):
                Path(status_file).write_text(
                    json.dumps({"status": "completed"}), encoding="utf-8"
                )
                return {"success": True, "stdout": "", "stderr": ""}

        monkeypatch.setattr(
            GatewayManagerTool, "_send_to_agent", FakeGW()._send_to_agent
        )
        r = tool._run_stage(
            self._node("plan.md"),
            "id_s1",
            {"a1": {"task": "规划"}},
            work_dir,
            artifact_dir,
            "",
            False,
        )
        assert r["status"] == "completed"
        assert r["result"] == {"status": "completed"}


# ---------------------------------------------------------------------------
# 常驻 Agent 创建失败重试
# ---------------------------------------------------------------------------
class TestCreateAgentRetry:
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
            }
        ]

    def test_retry_then_success(self, tool, monkeypatch):
        """前两次失败、第三次成功 → 返回 agent_id。"""
        calls = {"n": 0}

        class FakeGW:
            def _create_agent(self, agent_type, working_dir, name):
                calls["n"] += 1
                if calls["n"] < 3:
                    return {"success": False, "stdout": "", "stderr": "busy"}
                return {
                    "success": True,
                    "stdout": json.dumps({"agent_id": "id_x"}),
                    "stderr": "",
                }

        monkeypatch.setattr("time.sleep", lambda *a, **k: None)
        agent_id, err = tool._create_agent_with_retry(FakeGW(), "s1", ".")
        assert agent_id == "id_x"
        assert err == ""
        assert calls["n"] == 3

    def test_all_attempts_fail(self, tool, monkeypatch):
        """全部失败 → 返回空 id 与最后一次错误。"""
        calls = {"n": 0}

        class FakeGW:
            def _create_agent(self, agent_type, working_dir, name):
                calls["n"] += 1
                return {"success": False, "stdout": "", "stderr": f"err{calls['n']}"}

        monkeypatch.setattr("time.sleep", lambda *a, **k: None)
        agent_id, err = tool._create_agent_with_retry(FakeGW(), "s1", ".")
        assert agent_id == ""
        assert err == "err3"
        assert calls["n"] == 3

    def test_success_without_agent_id_retries(self, tool, monkeypatch):
        """创建成功但无 agent_id → 视为失败并重试。"""
        calls = {"n": 0}

        class FakeGW:
            def _create_agent(self, agent_type, working_dir, name):
                calls["n"] += 1
                if calls["n"] < 2:
                    return {"success": True, "stdout": "{}", "stderr": ""}
                return {
                    "success": True,
                    "stdout": json.dumps({"agent_id": "id_y"}),
                    "stderr": "",
                }

        monkeypatch.setattr("time.sleep", lambda *a, **k: None)
        agent_id, err = tool._create_agent_with_retry(FakeGW(), "s1", ".")
        assert agent_id == "id_y"
        assert calls["n"] == 2

    def test_create_stage_agents_uses_retry(self, tool, monkeypatch, tmp_path):
        """_create_stage_agents 走重试逻辑，成功建 map。"""
        calls = {"n": 0}

        class FakeGW:
            def _create_agent(self, agent_type, working_dir, name):
                calls["n"] += 1
                if calls["n"] < 2:
                    return {"success": False, "stdout": "", "stderr": "busy"}
                return {
                    "success": True,
                    "stdout": json.dumps({"agent_id": f"id_{name}"}),
                    "stderr": "",
                }

        monkeypatch.setattr(
            "jarvis.jarvis_tools.pipeline_runner.GatewayManagerTool",
            lambda: FakeGW(),
        )
        monkeypatch.setattr("time.sleep", lambda *a, **k: None)
        r = tool._create_stage_agents(self._nodes(), {"a1": {}}, tmp_path)
        assert r["success"] is True
        assert r["agent_map"]["s1"] == "id_df_s1"

    def test_create_stage_agents_fail_after_retry(self, tool, monkeypatch, tmp_path):
        """重试耗尽 → 返回失败并附错误。"""

        class FakeGW:
            def _create_agent(self, agent_type, working_dir, name):
                return {"success": False, "stdout": "", "stderr": "down"}

        monkeypatch.setattr(
            "jarvis.jarvis_tools.pipeline_runner.GatewayManagerTool",
            lambda: FakeGW(),
        )
        monkeypatch.setattr("time.sleep", lambda *a, **k: None)
        r = tool._create_stage_agents(self._nodes(), {"a1": {}}, tmp_path)
        assert r["success"] is False
        assert "down" in r["error"]

    def test_wait_agent_ready_polls_until_ready(self, tool):
        """_wait_agent_ready 轮询 /status 直到网关代理成功（非 502）。"""
        calls = {"n": 0}

        class FakeGW:
            def _request_gateway(self, method, path, error_prefix):
                calls["n"] += 1
                if calls["n"] < 3:
                    return {"success": False, "error": "HTTP 502"}
                return {"success": True, "data": {}}

        ok, err = tool._wait_agent_ready(
            FakeGW(), "agent_1", timeout=10, poll_interval=0
        )
        assert ok is True
        assert err == ""
        assert calls["n"] == 3

    def test_wait_agent_ready_timeout(self, tool):
        """_wait_agent_ready 持续 502 时超时返回失败。"""

        class FakeGW:
            def _request_gateway(self, method, path, error_prefix):
                return {"success": False, "error": "HTTP 502"}

        ok, err = tool._wait_agent_ready(
            FakeGW(), "agent_1", timeout=0.2, poll_interval=0
        )
        assert ok is False
        assert "超时" in err

    def test_wait_agent_ready_skips_without_request_gateway(self, tool):
        """无 _request_gateway 的测试桩直接视为就绪。"""

        class FakeGW:
            def _create_agent(self, agent_type, working_dir, name):
                return {"success": True, "stdout": json.dumps({"agent_id": "x"})}

        ok, err = tool._wait_agent_ready(FakeGW(), "agent_1")
        assert ok is True
        assert err == ""


# ---------------------------------------------------------------------------
# 失败/中止时清理常驻 Agent（task-22 编排可靠性）
# ---------------------------------------------------------------------------
class TestCleanupAgents:
    def test_cleanup_deletes_all_agents(self, tool, monkeypatch):
        """_cleanup_agents 删除 agent_map 中所有 Agent。"""
        deleted = []

        class FakeGW:
            def _delete_agent(self, agent_id):
                deleted.extend(agent_id if isinstance(agent_id, list) else [agent_id])
                return {"success": True, "stdout": "", "stderr": ""}

        monkeypatch.setattr(
            "jarvis.jarvis_tools.pipeline_runner.GatewayManagerTool",
            lambda: FakeGW(),
        )
        tool._cleanup_agents({"s1": "id_a", "s2": "id_b"})
        assert set(deleted) == {"id_a", "id_b"}

    def test_cleanup_skips_when_disabled(self, tool, monkeypatch):
        """配置关闭清理时不做删除。"""
        from jarvis.jarvis_utils.config import GLOBAL_CONFIG_DATA

        deleted = []

        class FakeGW:
            def _delete_agent(self, agent_id):
                deleted.append(agent_id)
                return {"success": True, "stdout": "", "stderr": ""}

        monkeypatch.setattr(
            "jarvis.jarvis_tools.pipeline_runner.GatewayManagerTool",
            lambda: FakeGW(),
        )
        key = "pipeline_cleanup_on_failure"
        original = GLOBAL_CONFIG_DATA.get(key)
        try:
            GLOBAL_CONFIG_DATA[key] = False
            tool._cleanup_agents({"s1": "id_a"})
        finally:
            if original is None:
                GLOBAL_CONFIG_DATA.pop(key, None)
            else:
                GLOBAL_CONFIG_DATA[key] = original
        assert deleted == []

    def test_cleanup_skips_without_delete_agent(self, tool, monkeypatch):
        """测试桩无 _delete_agent 时直接跳过，不报错。"""

        class FakeGW:
            def _create_agent(self, agent_type, working_dir, name):
                return {"success": True, "stdout": "{}"}

        monkeypatch.setattr(
            "jarvis.jarvis_tools.pipeline_runner.GatewayManagerTool",
            lambda: FakeGW(),
        )
        # 不应抛异常
        tool._cleanup_agents({"s1": "id_a"})

    def test_cleanup_empty_map(self, tool, monkeypatch):
        """空 agent_map 不调用删除。"""
        called = {"n": 0}

        class FakeGW:
            def _delete_agent(self, agent_id):
                called["n"] += 1
                return {"success": True}

        monkeypatch.setattr(
            "jarvis.jarvis_tools.pipeline_runner.GatewayManagerTool",
            lambda: FakeGW(),
        )
        tool._cleanup_agents({})
        assert called["n"] == 0

    def test_abort_calls_cleanup(self, tool, monkeypatch):
        """on_error=abort 中止时调用 _cleanup_agents。"""
        cleaned = {"n": 0}

        def fake_run_stage(node, *args, **kwargs):
            return {
                "stage": node["stage"],
                "status": "failed" if node["stage"] == "s1" else "completed",
                "output": "",
                "result": {},
                "error": "boom",
                "gate_blocked": False,
                "approval_path": "",
            }

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        monkeypatch.setattr(
            tool,
            "_cleanup_agents",
            lambda agent_map: cleaned.__setitem__("n", cleaned["n"] + 1),
        )
        # 使用 TestSchedule 的节点
        r = tool._schedule(**TestSchedule()._base_kwargs(tool, TestSchedule()._nodes()))
        assert r["success"] is False
        assert cleaned["n"] == 1

    def test_failure_calls_cleanup(self, tool, monkeypatch):
        """流水线存在失败阶段时调用 _cleanup_agents。"""
        cleaned = {"n": 0}

        def fake_run_stage(node, *args, **kwargs):
            return {
                "stage": node["stage"],
                "status": "failed",
                "output": "",
                "result": {},
                "error": "boom",
                "gate_blocked": False,
                "approval_path": "",
            }

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        monkeypatch.setattr(
            tool,
            "_cleanup_agents",
            lambda agent_map: cleaned.__setitem__("n", cleaned["n"] + 1),
        )
        nodes = TestSchedule()._nodes()
        nodes[0]["on_error"] = "continue"
        nodes[1]["on_error"] = "continue"
        r = tool._schedule(**TestSchedule()._base_kwargs(tool, nodes))
        assert r["success"] is False
        assert cleaned["n"] == 1


# ---------------------------------------------------------------------------
# dry-run 预演（方案1：只校验编排计划，不创建 Agent）
# ---------------------------------------------------------------------------
class TestDryRun:
    def _write(self, tmp_path, flow_yaml):
        orch = tmp_path / "p.yaml"
        orch.write_text(flow_yaml, encoding="utf-8")
        return orch

    def test_dry_run_no_agent_created(self, tool, monkeypatch, tmp_path):
        """dry-run 不创建 Agent、不派发任务。"""
        orch = self._write(
            tmp_path,
            """
agents:
  - name: a1
    working_dir: .
    task: t
flow:
  - stage: s1
    agent: a1
    output: .df/x.md
""",
        )

        def boom(*a, **k):
            raise AssertionError("dry-run 不应创建 Agent")

        monkeypatch.setattr(GatewayManagerTool, "_create_agent", boom)
        monkeypatch.setattr(GatewayManagerTool, "_send_to_agent", boom)
        r = tool.execute(
            {
                "orchestration_file": str(orch),
                "working_dir": str(tmp_path),
                "dry_run": True,
            }
        )
        assert r["success"] is True
        assert "dry-run" in r["stdout"]
        assert "s1" in r["stdout"]

    def test_dry_run_shows_parallel_batches(self, tool, tmp_path):
        """dry-run 正确标出并行批次与串行批次。"""
        orch = self._write(
            tmp_path,
            """
agents:
  - name: a1
    working_dir: .
    task: t
  - name: a2
    working_dir: .
    task: t
  - name: a3
    working_dir: .
    task: t
flow:
  - stage: plan
    agent: a1
    output: .df/plan.md
  - stage: gen_a
    agent: a2
    depends_on: [plan]
    output: .df/a.txt
  - stage: gen_b
    agent: a3
    depends_on: [plan]
    output: .df/b.txt
""",
        )
        r = tool.execute(
            {
                "orchestration_file": str(orch),
                "working_dir": str(tmp_path),
                "dry_run": True,
            }
        )
        assert r["success"] is True
        assert "批次 1 [串行]" in r["stdout"]
        assert "批次 2 [并行]" in r["stdout"]

    def test_dry_run_invalid_flow_reports_error(self, tool, tmp_path):
        """dry-run 对非法编排（重复 stage）报错。"""
        orch = self._write(
            tmp_path,
            """
agents:
  - name: a1
    working_dir: .
    task: t
flow:
  - stage: s1
    agent: a1
  - stage: s1
    agent: a1
""",
        )
        r = tool.execute(
            {
                "orchestration_file": str(orch),
                "working_dir": str(tmp_path),
                "dry_run": True,
            }
        )
        assert r["success"] is False
        assert "重复" in r["stderr"]

    def test_dry_run_shows_gate_and_when(self, tool, tmp_path):
        """dry-run 展示门禁与 when 信息。"""
        orch = self._write(
            tmp_path,
            """
agents:
  - name: a1
    working_dir: .
    task: t
  - name: a2
    working_dir: .
    task: t
flow:
  - stage: verify
    agent: a1
    output: .df/report.json
  - stage: audit
    agent: a2
    depends_on: [verify]
    when: "verify.pass_rate >= 0.9"
    output: .df/approval.md
    gate: true
""",
        )
        r = tool.execute(
            {
                "orchestration_file": str(orch),
                "working_dir": str(tmp_path),
                "dry_run": True,
            }
        )
        assert r["success"] is True
        assert "门禁阶段: audit" in r["stdout"]
        assert "when=verify.pass_rate >= 0.9" in r["stdout"]

    def test_dry_run_inline_spec_without_spec_file(self, tool, tmp_path):
        """读取编排文件顶层 spec 字段作为各阶段背景（普通编排无需独立规格文件）。"""
        orch = tmp_path / "p.yaml"
        orch.write_text(
            """
spec: |
  这是内嵌在编排文件里的流水线背景说明。
agents:
  - name: a1
    working_dir: .
    task: t
flow:
  - stage: s1
    agent: a1
    output: .df/x.md
""",
            encoding="utf-8",
        )
        r = tool.execute(
            {
                "orchestration_file": str(orch),
                "working_dir": str(tmp_path),
                "dry_run": True,
            }
        )
        assert r["success"] is True
        assert "dry-run" in r["stdout"]
        assert "s1" in r["stdout"]

    def test_dry_run_no_spec_at_all(self, tool, tmp_path):
        """编排文件既无 spec 字段也不传独立规格文件：仍可运行，各阶段用自身 task 描述即可。"""
        orch = tmp_path / "p.yaml"
        orch.write_text(
            """
agents:
  - name: a1
    working_dir: .
    task: t
flow:
  - stage: s1
    agent: a1
    output: .df/x.md
""",
            encoding="utf-8",
        )
        r = tool.execute(
            {
                "orchestration_file": str(orch),
                "working_dir": str(tmp_path),
                "dry_run": True,
            }
        )
        assert r["success"] is True
        assert "s1" in r["stdout"]

    def test_plan_batches_order(self, tool):
        """_plan_batches：依赖层级分批正确。"""
        nodes = [
            {
                "stage": "a",
                "depends_on": [],
                "agent": "x",
                "input": [],
                "output": "",
                "gate": False,
                "when": None,
                "retry": 0,
                "on_error": "abort",
            },
            {
                "stage": "b",
                "depends_on": ["a"],
                "agent": "x",
                "input": [],
                "output": "",
                "gate": False,
                "when": None,
                "retry": 0,
                "on_error": "abort",
            },
            {
                "stage": "c",
                "depends_on": ["a"],
                "agent": "x",
                "input": [],
                "output": "",
                "gate": False,
                "when": None,
                "retry": 0,
                "on_error": "abort",
            },
            {
                "stage": "d",
                "depends_on": ["b", "c"],
                "agent": "x",
                "input": [],
                "output": "",
                "gate": False,
                "when": None,
                "retry": 0,
                "on_error": "abort",
            },
        ]
        batches = tool._plan_batches(nodes)
        assert [n["stage"] for n in batches[0]] == ["a"]
        assert sorted(n["stage"] for n in batches[1]) == ["b", "c"]
        assert [n["stage"] for n in batches[2]] == ["d"]


# ---------------------------------------------------------------------------
# 跨节点校验（有 flow 的编排不支持跨节点）
# ---------------------------------------------------------------------------
class TestCrossNodeValidation:
    def _write(self, tmp_path, agents_yaml):
        orch = tmp_path / "p.yaml"
        orch.write_text(
            "agents:\n" + agents_yaml + "flow:\n  - stage: s1\n    agent: a1\n    output: .df/x.md\n",
            encoding="utf-8",
        )
        return orch

    def test_node_id_rejected(self, tool, tmp_path):
        """agent 定义带 node_id 时明确报错，而非静默忽略。"""
        orch = self._write(
            tmp_path,
            "  - name: a1\n    working_dir: .\n    task: t\n    node_id: worker-1\n",
        )
        r = tool.execute(
            {
                "orchestration_file": str(orch),
                "working_dir": str(tmp_path),
                "dry_run": True,
            }
        )
        assert r["success"] is False
        assert "不支持跨节点" in r["stderr"]

    def test_proxy_node_rejected(self, tool, tmp_path):
        """agent 定义带 proxy_node 时明确报错。"""
        orch = self._write(
            tmp_path,
            "  - name: a1\n    working_dir: .\n    task: t\n    proxy_node: proxy-1\n",
        )
        r = tool.execute(
            {
                "orchestration_file": str(orch),
                "working_dir": str(tmp_path),
                "dry_run": True,
            }
        )
        assert r["success"] is False
        assert "不支持跨节点" in r["stderr"]

    def test_without_node_fields_ok(self, tool, tmp_path):
        """不带 node_id/proxy_node 的编排正常执行（dry-run）。"""
        orch = self._write(tmp_path, "  - name: a1\n    working_dir: .\n    task: t\n")
        r = tool.execute(
            {
                "orchestration_file": str(orch),
                "working_dir": str(tmp_path),
                "dry_run": True,
            }
        )
        assert r["success"] is True
        assert "s1" in r["stdout"]
        """_plan_batches：依赖层级分批正确。"""
        nodes = [
            {
                "stage": "a",
                "depends_on": [],
                "agent": "x",
                "input": [],
                "output": "",
                "gate": False,
                "when": None,
                "retry": 0,
                "on_error": "abort",
            },
            {
                "stage": "b",
                "depends_on": ["a"],
                "agent": "x",
                "input": [],
                "output": "",
                "gate": False,
                "when": None,
                "retry": 0,
                "on_error": "abort",
            },
            {
                "stage": "c",
                "depends_on": ["a"],
                "agent": "x",
                "input": [],
                "output": "",
                "gate": False,
                "when": None,
                "retry": 0,
                "on_error": "abort",
            },
            {
                "stage": "d",
                "depends_on": ["b", "c"],
                "agent": "x",
                "input": [],
                "output": "",
                "gate": False,
                "when": None,
                "retry": 0,
                "on_error": "abort",
            },
        ]
        batches = tool._plan_batches(nodes)
        assert [n["stage"] for n in batches[0]] == ["a"]
        assert sorted(n["stage"] for n in batches[1]) == ["b", "c"]
        assert [n["stage"] for n in batches[2]] == ["d"]


# ---------------------------------------------------------------------------
# 进度事件埋点（_schedule 状态迁移 → 事件总线）
# ---------------------------------------------------------------------------
class TestPipelineEventEmit:
    """验证 _schedule 在各状态迁移点向事件总线写入正确的 stage_update /
    pipeline_done 事件，且埋点为纯副作用（不影响返回值/状态机语义）。
    """

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

    def _base_kwargs(self, nodes, pipeline_id="pl-test"):
        return dict(
            nodes=nodes,
            agent_map={n["stage"]: f"id_{n['stage']}" for n in nodes},
            agents_by_name={"a1": {}, "a2": {}},
            work_dir=Path("."),
            artifact_dir=Path(".df"),
            spec_summary="",
            approve=False,
            max_workers=4,
            pipeline_id=pipeline_id,
        )

    def _completed(self, node):
        return {
            "stage": node["stage"],
            "status": "completed",
            "output": "",
            "result": {},
            "error": "",
            "gate_blocked": False,
            "approval_path": "",
        }

    def _drain(self):
        from jarvis.jarvis_tools.pipeline_events import get_event_bus

        return get_event_bus().drain()

    def test_all_completed_emits_running_and_done(self, tool, monkeypatch):
        """全部完成：每个 stage 有 running+completed，末尾 pipeline_done=completed。"""
        self._drain()  # 清空遗留事件
        monkeypatch.setattr(
            tool, "_run_stage", lambda node, *a, **k: self._completed(node)
        )
        nodes = self._nodes()
        r = tool._schedule(**self._base_kwargs(nodes))
        assert r["success"] is True

        events = self._drain()
        assert all(e["pipeline_id"] == "pl-test" for e in events)
        stage_events = [e for e in events if e["type"] == "stage_update"]
        # s1/s2 各有 running 与 completed
        for stage in ("s1", "s2"):
            statuses = [e["status"] for e in stage_events if e["stage"] == stage]
            assert statuses.count("running") == 1
            assert statuses.count("completed") == 1
        done = [e for e in events if e["type"] == "pipeline_done"]
        assert len(done) == 1
        assert done[0]["success"] is True
        assert done[0]["final_status"] == "completed"

    def test_failed_emits_pipeline_done_failed(self, tool, monkeypatch):
        """失败：失败 stage 有 failed 事件，末尾 pipeline_done=failed。"""
        self._drain()

        def fake_run_stage(node, *a, **k):
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
            return self._completed(node)

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        nodes = self._nodes()
        # on_error=continue：失败不中止，走"存在失败阶段"出口
        nodes[0]["on_error"] = "continue"
        r = tool._schedule(**self._base_kwargs(nodes))
        assert r["success"] is False

        events = self._drain()
        failed = [
            e for e in events if e["type"] == "stage_update" and e["status"] == "failed"
        ]
        assert any(e["stage"] == "s1" for e in failed)
        done = [e for e in events if e["type"] == "pipeline_done"]
        assert len(done) == 1
        assert done[0]["success"] is False
        assert done[0]["final_status"] == "failed"

    def test_abort_emits_pipeline_done_aborted(self, tool, monkeypatch):
        """on_error=abort：失败立即中止，pipeline_done=aborted。"""
        self._drain()

        def fake_run_stage(node, *a, **k):
            return {
                "stage": node["stage"],
                "status": "failed",
                "output": "",
                "result": {},
                "error": "boom",
                "gate_blocked": False,
                "approval_path": "",
            }

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        nodes = self._nodes()
        r = tool._schedule(**self._base_kwargs(nodes))
        assert r["success"] is False

        events = self._drain()
        done = [e for e in events if e["type"] == "pipeline_done"]
        assert len(done) == 1
        assert done[0]["success"] is False
        assert done[0]["final_status"] == "aborted"

    def test_skipped_emits_skipped_event(self, tool, monkeypatch):
        """依赖失败被跳过：s2 有 skipped 事件。"""
        self._drain()

        def fake_run_stage(node, *a, **k):
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
            return self._completed(node)

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        nodes = self._nodes()
        # on_error=skip_dependents：s1 失败后 s2 被跳过
        nodes[0]["on_error"] = "skip_dependents"
        tool._schedule(**self._base_kwargs(nodes))

        events = self._drain()
        skipped = [
            e
            for e in events
            if e["type"] == "stage_update" and e["status"] == "skipped"
        ]
        assert any(e["stage"] == "s2" for e in skipped)

    def test_retry_emits_retry_event(self, tool, monkeypatch):
        """retry：首次失败发 retry 事件，重试成功后 completed。"""
        self._drain()
        attempts = {"s1": 0}

        def fake_run_stage(node, *a, **k):
            if node["stage"] == "s1":
                attempts["s1"] += 1
                if attempts["s1"] == 1:
                    return {
                        "stage": "s1",
                        "status": "failed",
                        "output": "",
                        "result": {},
                        "error": "flaky",
                        "gate_blocked": False,
                        "approval_path": "",
                    }
            return self._completed(node)

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        nodes = self._nodes()
        nodes[0]["retry"] = 1
        r = tool._schedule(**self._base_kwargs(nodes))
        assert r["success"] is True

        events = self._drain()
        retries = [
            e for e in events if e["type"] == "stage_update" and e["status"] == "retry"
        ]
        assert len(retries) == 1
        assert retries[0]["stage"] == "s1"
        assert retries[0]["retry_count"] == 1

    def test_gate_blocked_emits_gate_status(self, tool, monkeypatch):
        """门禁停住：pipeline_done=gate_blocked 且带 gate_stage。"""
        self._drain()

        def fake_run_stage(node, *a, **k):
            return {
                "stage": node["stage"],
                "status": "completed",
                "output": "",
                "result": {},
                "error": "",
                "gate_blocked": node["stage"] == "s1",
                "approval_path": "/tmp/approval.md",
            }

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        nodes = self._nodes()
        nodes[0]["gate"] = True
        r = tool._schedule(**self._base_kwargs(nodes))
        assert r["success"] is True

        events = self._drain()
        done = [e for e in events if e["type"] == "pipeline_done"]
        assert len(done) == 1
        assert done[0]["final_status"] == "gate_blocked"
        assert done[0]["gate_stage"] == "s1"

    def test_gate_blocked_emits_pending_approval(self, tool, monkeypatch):
        """门禁停住：额外广播一条 pipeline_approval action=pending 事件。"""
        self._drain()

        def fake_run_stage(node, *a, **k):
            return {
                "stage": node["stage"],
                "status": "completed",
                "output": "",
                "result": {},
                "error": "",
                "gate_blocked": node["stage"] == "s1",
                "approval_path": "/tmp/approval.md",
            }

        monkeypatch.setattr(tool, "_run_stage", fake_run_stage)
        nodes = self._nodes()
        nodes[0]["gate"] = True
        r = tool._schedule(**self._base_kwargs(nodes))
        assert r["success"] is True

        events = self._drain()
        approvals = [e for e in events if e["type"] == "pipeline_approval"]
        assert len(approvals) == 1
        assert approvals[0]["action"] == "pending"
        assert approvals[0]["gate_stage"] == "s1"
        assert approvals[0]["approval_path"] == "/tmp/approval.md"
        assert "ts" in approvals[0]

    def test_emit_is_pure_side_effect(self, tool, monkeypatch):
        """事件总线异常不影响执行结果（纯副作用）。"""
        self._drain()

        class _BoomBus:
            def emit(self, event):
                raise RuntimeError("bus down")

        import jarvis.jarvis_tools.pipeline_events as pe

        monkeypatch.setattr(pe, "get_event_bus", lambda: _BoomBus())
        monkeypatch.setattr(
            tool, "_run_stage", lambda node, *a, **k: self._completed(node)
        )
        nodes = self._nodes()
        r = tool._schedule(**self._base_kwargs(nodes))
        assert r["success"] is True
        assert "全部阶段完成" in r["stdout"]


# ---------------------------------------------------------------------------
# 门禁人工审批记录（record_approval）
# ---------------------------------------------------------------------------
class TestRecordApproval:
    """验证 record_approval 记录审批决定并广播 pipeline_approval 事件。"""

    def _drain(self):
        from jarvis.jarvis_tools.pipeline_events import get_event_bus

        return get_event_bus().drain()

    def test_approve_records_and_emits(self, tool):
        """放行：返回成功并广播 action=approve 事件（含审批人/备注/时间）。"""
        self._drain()
        r = tool.record_approval(
            pipeline_id="pl-1", action="approve", approver="alice", note="ok"
        )
        assert r["success"] is True
        assert r["data"]["action"] == "approve"
        assert r["data"]["approver"] == "alice"
        assert r["data"]["note"] == "ok"
        events = self._drain()
        appr = [e for e in events if e["type"] == "pipeline_approval"]
        assert len(appr) == 1
        assert appr[0]["action"] == "approve"
        assert appr[0]["approver"] == "alice"
        assert appr[0]["note"] == "ok"
        assert appr[0]["pipeline_id"] == "pl-1"
        assert "ts" in appr[0]

    def test_reject_and_retry_actions(self, tool):
        """拒绝/重试：均成功广播对应 action。"""
        for action in ("reject", "retry"):
            self._drain()
            r = tool.record_approval(pipeline_id="pl-1", action=action)
            assert r["success"] is True
            assert r["data"]["action"] == action
            events = self._drain()
            appr = [e for e in events if e["type"] == "pipeline_approval"]
            assert len(appr) == 1
            assert appr[0]["action"] == action

    def test_invalid_action_rejected(self, tool):
        """非法动作：返回失败且不广播事件。"""
        self._drain()
        r = tool.record_approval(pipeline_id="pl-1", action="banana")
        assert r["success"] is False
        assert "无效审批动作" in r["error"]
        events = self._drain()
        assert not [e for e in events if e["type"] == "pipeline_approval"]

    def test_missing_pipeline_id_rejected(self, tool):
        """缺少 pipeline_id：返回失败。"""
        r = tool.record_approval(pipeline_id="", action="approve")
        assert r["success"] is False
        assert "pipeline_id" in r["error"]

    def test_action_case_insensitive(self, tool):
        """动作大小写不敏感：Approve 归一为 approve。"""
        self._drain()
        r = tool.record_approval(pipeline_id="pl-1", action="Approve")
        assert r["success"] is True
        assert r["data"]["action"] == "approve"
