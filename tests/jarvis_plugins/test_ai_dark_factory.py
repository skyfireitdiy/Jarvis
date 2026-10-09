# -*- coding: utf-8 -*-
"""AI 黑灯工厂插件（ai-dark-factory）测试。

覆盖：
1. 3 个工具（spec_validator / holdout_generator / gate_calculator）的正常、
   边界、异常场景；
2. 编排模板 dark_factory_pipeline.yaml 的格式（agents 列表、flow 字段、四要素齐全）；
3. config.yaml 的可解析性与声明完整性。

所有工具用 importlib 直接加载插件源码文件，不依赖全局配置加载，
避免污染真实环境。
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

PLUGIN_DIR = (
    Path(__file__).resolve().parents[2]
    / "builtin"
    / "plugins"
    / "ai-dark-factory"
)
TOOLS_DIR = PLUGIN_DIR / "tools"


def _load_tool_class(module_name: str, filename: str):
    """用 importlib 加载插件工具文件，返回其中的 Tool 类。"""
    file_path = TOOLS_DIR / filename
    assert file_path.is_file(), f"工具文件不存在: {file_path}"
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    for attr in dir(mod):
        if attr.endswith("Tool"):
            cls = getattr(mod, attr)
            if isinstance(cls, type):
                return cls
    raise AssertionError(f"{filename} 中未找到 Tool 类")


@pytest.fixture(scope="module")
def spec_validator():
    return _load_tool_class("df_spec_validator", "spec_validator.py")()


@pytest.fixture(scope="module")
def holdout_generator():
    return _load_tool_class("df_holdout_generator", "holdout_generator.py")()


@pytest.fixture(scope="module")
def gate_calculator():
    return _load_tool_class("df_gate_calculator", "gate_calculator.py")()


class TestToolInterface:
    """工具接口完备性（name/description/parameters/check/execute）。"""

    @pytest.mark.parametrize(
        "tool_name,filename",
        [
            ("spec_validator", "spec_validator.py"),
            ("holdout_generator", "holdout_generator.py"),
            ("gate_calculator", "gate_calculator.py"),
        ],
    )
    def test_interface_complete(self, tool_name, filename):
        cls = _load_tool_class(f"iface_{tool_name}", filename)
        tool = cls()
        assert tool.name == tool_name, f"{tool_name} name 不匹配"
        assert tool.description
        assert isinstance(tool.parameters, dict)
        assert callable(tool.check)
        assert callable(tool.execute)
        assert tool.check() is True


class TestSpecValidator:
    """NLSpec 四要素校验工具。"""

    def test_valid_spec(self, spec_validator):
        r = spec_validator.execute(
            {
                "spec": (
                    "目标：构建一个计算器。约束：必须用 Python，性能要求。"
                    "接口：函数 add(a,b)。非目标：不做 GUI。"
                )
            }
        )
        assert r["success"] is True
        out = json.loads(r["stdout"])
        assert out["valid"] is True
        assert out["missing"] == []

    def test_missing_elements(self, spec_validator):
        r = spec_validator.execute({"spec": "随便写点什么"})
        assert r["success"] is True
        out = json.loads(r["stdout"])
        assert out["valid"] is False
        assert len(out["missing"]) >= 1

    def test_empty_spec(self, spec_validator):
        r = spec_validator.execute({"spec": ""})
        assert r["success"] is False
        assert "非空字符串" in r["stderr"]

    def test_missing_param(self, spec_validator):
        r = spec_validator.execute({})
        assert r["success"] is False

    def test_non_string_spec(self, spec_validator):
        r = spec_validator.execute({"spec": 123})
        assert r["success"] is False


class TestHoldoutGenerator:
    """holdout scenarios 生成工具。"""

    def test_generate_default_count(self, holdout_generator):
        r = holdout_generator.execute({"feature": "计算器"})
        assert r["success"] is True
        out = json.loads(r["stdout"])
        assert out["count"] == 5
        assert len(out["scenarios"]) == 5
        # 每个场景必须标记 hidden（编码侧不可见）
        assert all(s["hidden"] is True for s in out["scenarios"])

    def test_generate_specific_count(self, holdout_generator):
        r = holdout_generator.execute({"feature": "计算器", "count": 3})
        out = json.loads(r["stdout"])
        assert out["count"] == 3
        assert len(out["scenarios"]) == 3

    def test_count_clamped_upper(self, holdout_generator):
        r = holdout_generator.execute({"feature": "x", "count": 999})
        out = json.loads(r["stdout"])
        assert out["count"] == 20

    def test_count_clamped_lower(self, holdout_generator):
        r = holdout_generator.execute({"feature": "x", "count": 0})
        out = json.loads(r["stdout"])
        assert out["count"] == 1

    def test_missing_feature(self, holdout_generator):
        r = holdout_generator.execute({})
        assert r["success"] is False


class TestGateCalculator:
    """门禁指标计算工具。"""

    def test_pass_rate_above_threshold(self, gate_calculator):
        r = gate_calculator.execute(
            {"results": [{"id": 1, "pass": True}, {"id": 2, "pass": True}, {"id": 3, "pass": True}]}
        )
        out = json.loads(r["stdout"])
        assert out["pass_rate"] == 1.0
        assert out["meets_threshold"] is True
        assert "建议通过" in out["decision"]

    def test_pass_rate_below_threshold(self, gate_calculator):
        r = gate_calculator.execute(
            {"results": [{"id": 1, "pass": True}, {"id": 2, "pass": True}, {"id": 3, "pass": False}]}
        )
        out = json.loads(r["stdout"])
        # 工具将 pass_rate 四舍五入到 4 位小数
        assert out["pass_rate"] == pytest.approx(2 / 3, abs=0.0001)
        assert out["meets_threshold"] is False

    def test_caution_high_false_positive(self, gate_calculator):
        r = gate_calculator.execute(
            {
                "results": [{"id": 1, "pass": True}, {"id": 2, "pass": True}],
                "false_positives": 2,
            }
        )
        out = json.loads(r["stdout"])
        assert out["caution"] is True

    def test_empty_results(self, gate_calculator):
        r = gate_calculator.execute({"results": []})
        assert r["success"] is False

    def test_missing_results(self, gate_calculator):
        r = gate_calculator.execute({})
        assert r["success"] is False


class TestOrchestrationTemplate:
    """预置编排模板 dark_factory_pipeline.yaml 格式。"""

    def _load(self):
        path = PLUGIN_DIR / "orchestration" / "dark_factory_pipeline.yaml"
        assert path.is_file(), "编排模板不存在"
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_has_all_layer_agents(self):
        data = self._load()
        assert "agents" in data
        agents = data["agents"]
        assert len(agents) == 6
        names = [a["name"] for a in agents]
        # 架构：planner / holdout / generator / validator / regression / orchestrator
        assert "df_planner" in names
        assert "df_holdout" in names
        assert "df_generator" in names
        assert "df_validator" in names
        assert "df_regression" in names
        assert "df_orchestrator" in names

    def test_each_agent_has_required_fields(self):
        """每个 agent 必须声明 name / working_dir / task（不含 type）。

        编排系统忽略阶段 type 字段，阶段 Agent 一律按 type: agent → jvs 创建，
        因此模板 agent 无需声明 type。
        """
        data = self._load()
        for a in data["agents"]:
            assert a.get("name"), "agent 缺 name"
            assert a.get("working_dir"), "agent 缺 working_dir"
            assert a.get("task"), "agent 缺 task"

    def test_orchestrator_not_auto_merge(self):
        """编排器（orchestrator）应强调人工审批，不自动合并（不完全无人值守）。"""
        data = self._load()
        orch = next(a for a in data["agents"] if a["name"] == "df_orchestrator")
        task = orch["task"]
        assert "人工审批" in task or "不自动合并" in task or "审批" in task

    def test_has_flow_field(self):
        """编排模板声明 flow（供 pipeline_runner 驱动）。"""
        data = self._load()
        assert "flow" in data, "编排模板缺 flow 字段"
        assert isinstance(data["flow"], list) and data["flow"]
        stages = [s["stage"] for s in data["flow"]]
        # 按序：planner → holdout → generator → validator → regression → orchestrator
        assert stages == [
            "planner",
            "holdout",
            "generator",
            "validator",
            "regression",
            "orchestrator",
        ]

    def test_flow_agents_referenced(self):
        """flow 每个 stage 引用的 agent 必须存在于 agents 中。"""
        data = self._load()
        names = {a["name"] for a in data["agents"]}
        for s in data["flow"]:
            assert s.get("agent") in names, f"flow 引用未定义 agent: {s.get('agent')}"

    def test_orchestrator_is_gate(self):
        """orchestrator 阶段应为门禁（gate: true），停住等人工审批。"""
        data = self._load()
        orch_stage = next(s for s in data["flow"] if s["stage"] == "orchestrator")
        assert orch_stage.get("gate") is True

    def test_generator_no_isolated_output(self):
        """generator 阶段应无独立代码目录产物（在已有代码库中直接修改）。"""
        data = self._load()
        gen_stage = next(s for s in data["flow"] if s["stage"] == "generator")
        assert "output" not in gen_stage, "generator 不应有独立 output 目录"
        assert gen_stage.get("input") == ".df/plan.md"

    def test_holdout_stage_exists(self):
        """holdout 阶段生成隐藏验收场景，产物 .df/holdout.json。"""
        data = self._load()
        ho = next(s for s in data["flow"] if s["stage"] == "holdout")
        assert ho.get("output") == ".df/holdout.json"
        assert ho.get("agent") == "df_holdout"

    def test_holdout_isolated_from_generator(self):
        """holdout 产物只传 validator，绝不注入 generator（隔离纪律）。"""
        data = self._load()
        gen_stage = next(s for s in data["flow"] if s["stage"] == "generator")
        gen_inputs = gen_stage.get("input")
        gen_inputs = gen_inputs if isinstance(gen_inputs, list) else [gen_inputs]
        assert ".df/holdout.json" not in gen_inputs, "holdout 不得注入 generator"
        val_stage = next(s for s in data["flow"] if s["stage"] == "validator")
        val_inputs = val_stage.get("input")
        val_inputs = val_inputs if isinstance(val_inputs, list) else [val_inputs]
        assert ".df/holdout.json" in val_inputs, "validator 应消费 holdout 场景"

    def test_regression_stage_exists(self):
        """regression 阶段跑既有测试防回归，失败即中止。"""
        data = self._load()
        reg = next(s for s in data["flow"] if s["stage"] == "regression")
        assert reg.get("agent") == "df_regression"
        assert reg.get("output") == ".df/regression.json"
        assert reg.get("on_error") == "abort"


class TestPluginConfig:
    """插件 config.yaml 声明完整性。"""

    def _load(self):
        path = PLUGIN_DIR / "config.yaml"
        assert path.is_file(), "config.yaml 不存在"
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_metadata_complete(self):
        cfg = self._load()
        assert cfg.get("name") == "ai-dark-factory"
        assert cfg.get("description")
        assert cfg.get("version")
        assert cfg.get("builtin") is True

    def test_declares_rules_and_tools_dirs(self):
        cfg = self._load()
        assert cfg.get("rules_load_dirs"), "缺 rules_load_dirs"
        assert cfg.get("tool_load_dirs"), "缺 tool_load_dirs"

    def test_declares_orchestration(self):
        cfg = self._load()
        orch = cfg.get("orchestration")
        assert isinstance(orch, list) and orch
        entry = orch[0]
        assert entry.get("name") == "dark-factory-pipeline"
        assert entry.get("file")

    def test_declares_replace_map(self):
        cfg = self._load()
        rm = cfg.get("replace_map")
        assert isinstance(rm, dict)
        assert "dark-factory/issue" in rm
        assert "dark-factory/pr" in rm
