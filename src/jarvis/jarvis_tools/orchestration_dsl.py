# -*- coding: utf-8 -*-
"""编排 Python DSL（第 1 层：结构生成）。

让用户用 Python 编写编排，但 Python **只负责生成 DAG 结构**，不参与运行时调度。
脚本执行后，`Pipeline` 对象导出的结构（agents/flow/spec_text/default_on_error）
与 YAML 编排文件解析后的结构**同构**，可直接交给 pipeline_runner 的 `_build_dag`
消费——因此执行引擎、调度、事件、前端可视化、跨节点分发全部不变。

设计取向（详见 docs/design/orchestration-python-dsl.md）：
- **纯库、无副作用**：本模块只提供构造器，不派发任务、不写文件、不依赖引擎。
- **只声明结构**：脚本执行完即得到 DAG 数据；预览 = 执行脚本拿结构，不跑 Agent。
- **与 YAML 同构**：flow 项字段与 YAML `flow` 一致
  （stage/agent/depends_on/input/output/gate/when/retry/on_error），
  agents 项字段与 YAML `agents` 一致（name/working_dir/task 等）。
- **循环是编译期展开**：用 Python 的 for/if 在生成时决定阶段集合；
  运行时动态循环（loop 原语）不在本层范围。

用法（编排脚本约定顶层变量 `pipeline`）：

    from jarvis.jarvis_tools.orchestration_dsl import Pipeline, stage

    pipeline = Pipeline()
    pipeline.spec("流水线背景……")
    pipeline.agent("planner", working_dir=".", task="你是规划器……")
    pipeline.add(stage("plan", agent="planner", output=".df/plan.md"))
"""

from typing import Any
from typing import Dict
from typing import List
from typing import Optional

# flow 项允许的字段（与 pipeline_runner._build_dag 读取的键一致）
_FLOW_KEYS = (
    "stage",
    "agent",
    "depends_on",
    "input",
    "output",
    "gate",
    "when",
    "retry",
    "on_error",
)

# agents 项允许的字段（与 YAML agents 项一致）
_AGENT_KEYS = (
    "name",
    "working_dir",
    "task",
    "llm_group",
    "tool_group",
    "node_id",
    "proxy_node",
    "quick_mode",
    "restore_session",
    "no_interaction_mode",
    "access_acl",
    "additional_args",
)

# loop 项允许的字段（第 2 层：运行时循环原语）
_LOOP_KEYS = (
    "loop",
    "body",
    "until",
    "max_iterations",
    "on_error",
)


def stage(
    name: str,
    agent: str,
    depends_on: Optional[Any] = None,
    input: Optional[Any] = None,  # noqa: A002 - 与 YAML 字段名保持一致
    output: str = "",
    gate: bool = False,
    when: Optional[str] = None,
    retry: int = 0,
    on_error: Optional[str] = None,
) -> Dict[str, Any]:
    """声明一个流水线阶段（对应 YAML `flow` 的一项）。

    参数与 YAML `flow` 项字段一一对应，本函数只做**归一化与校验**，
    不补全 `depends_on`（缺省 = 上一个 stage 的语义由 `_build_dag` 负责，
    以保证与 YAML 行为完全一致）。

    参数:
        name: 阶段名（唯一，供 depends_on/when 引用）。
        agent: 引用的 agent 名（须在 Pipeline.agent() 中定义）。
        depends_on: 依赖的阶段名（字符串或列表）；None/空表示交由 `_build_dag`
            按"上一个 stage"缺省处理。
        input: 上游产物路径（字符串或列表）。
        output: 本阶段产物路径（非空时全局唯一）。
        gate: 是否门禁（True 时 approve=false 会停住等人工审批）。
        when: 受限条件表达式（语义同 YAML，由引擎求值）。
        retry: 失败重试次数。
        on_error: 失败策略（abort/continue/skip_dependents）；None 表示交由
            `_build_dag` 回退到顶层 default_on_error。

    返回:
        flow 项字典（仅含显式声明的键，缺省键不写入，交由 `_build_dag` 处理）。
    """
    if not str(name or "").strip():
        raise ValueError("stage 缺少 name")
    if not str(agent or "").strip():
        raise ValueError(f"stage '{name}' 缺少 agent")

    item: Dict[str, Any] = {
        "stage": str(name).strip(),
        "agent": str(agent).strip(),
    }
    if depends_on is not None:
        item["depends_on"] = depends_on
    if input is not None:
        item["input"] = input
    if output:
        item["output"] = str(output).strip()
    if gate:
        item["gate"] = True
    if when:
        item["when"] = str(when).strip()
    if retry:
        item["retry"] = int(retry)
    if on_error:
        item["on_error"] = str(on_error).strip()
    return item


def loop(
    name: str,
    body: Any,
    until: str,
    max_iterations: int = 5,
    on_error: Optional[str] = None,
) -> Dict[str, Any]:
    """声明一个运行时循环节点（第 2 层：子图循环）。

    循环体 `body` 是一组已声明的 stage 名（子图）；引擎执行时把 body 整段
    按依赖跑一遍，然后求值 `until`，未满足则重置 body 内 stage 重跑，
    直到满足或达 `max_iterations`。

    参数:
        name: 循环节点名（唯一，供 depends_on 引用）。
        body: 循环体 stage 名（字符串或列表），须非空且引用已声明的 stage。
        until: 退出条件表达式（运行时求值，复用 when 求值器；支持
            `stage.field` 引用与 `file(path)`/`contains(text, substr)`）。
        max_iterations: 最大迭代轮次（正整数，防死循环）。
        on_error: 失败策略（abort/continue/skip_dependents）；None 交由引擎
            回退到顶层 default_on_error。

    返回:
        loop 项字典（供 Pipeline.add 追加）。

    异常:
        ValueError: name/until 为空、body 为空、max_iterations 非正整数。
    """
    loop_name = str(name or "").strip()
    if not loop_name:
        raise ValueError("loop 缺少 name")

    if body is None:
        body_list: List[str] = []
    elif isinstance(body, str):
        body_list = [body.strip()] if body.strip() else []
    elif isinstance(body, (list, tuple)):
        body_list = [str(b).strip() for b in body if str(b).strip()]
    else:
        raise ValueError(f"loop '{loop_name}' 的 body 须为字符串或列表")
    if not body_list:
        raise ValueError(f"loop '{loop_name}' 的 body 不能为空")

    until_expr = str(until or "").strip()
    if not until_expr:
        raise ValueError(f"loop '{loop_name}' 缺少 until 退出条件")

    try:
        max_iter = int(max_iterations)
    except (TypeError, ValueError):
        raise ValueError(f"loop '{loop_name}' 的 max_iterations 须为正整数") from None
    if max_iter < 1:
        raise ValueError(f"loop '{loop_name}' 的 max_iterations 须为正整数")

    item: Dict[str, Any] = {
        "loop": loop_name,
        "body": body_list,
        "until": until_expr,
        "max_iterations": max_iter,
    }
    if on_error:
        item["on_error"] = str(on_error).strip()
    return item


class Pipeline:
    """编排容器：累积 agents 与 flow 声明，导出与 YAML 同构的结构。

    脚本执行完后，约定把 `Pipeline` 实例赋给顶层变量 `pipeline`，
    由 orchestration_loader 读取并导出结构。
    """

    def __init__(self) -> None:
        self._agents: List[Dict[str, Any]] = []
        self._flow: List[Dict[str, Any]] = []
        self._agent_names: set = set()
        self._stage_names: set = set()
        self._loop_names: set = set()
        self._spec_text: str = ""
        self._default_on_error: str = ""

    # ------------------------------------------------------------------
    # 声明
    # ------------------------------------------------------------------
    def add(self, stage_item: Dict[str, Any]) -> "Pipeline":
        """追加一个阶段或循环节点（由 `stage()` / `loop()` 构造）。

        - stage 项：以 `stage` 字段为名，校验唯一。
        - loop 项（第 2 层）：以 `loop` 字段为名，校验唯一，且 body 内引用的
          stage 须已声明。

        返回 self 以支持链式调用。
        """
        if not isinstance(stage_item, dict):
            raise TypeError("add() 需要 stage()/loop() 返回的字典")
        if "loop" in stage_item:
            loop_name = str(stage_item.get("loop") or "").strip()
            if not loop_name:
                raise ValueError("loop 项缺少 loop 名")
            if loop_name in self._loop_names:
                raise ValueError(f"重复的 loop 名: {loop_name}")
            if loop_name in self._stage_names:
                raise ValueError(f"loop 名与 stage 名冲突: {loop_name}")
            for b in stage_item.get("body") or []:
                if b not in self._stage_names:
                    raise ValueError(
                        f"loop '{loop_name}' 的 body 引用了未声明的 stage '{b}'"
                    )
            self._loop_names.add(loop_name)
            self._flow.append(stage_item)
            return self

        name = str(stage_item.get("stage") or "").strip()
        if name in self._stage_names:
            raise ValueError(f"重复的 stage 名: {name}")
        if name in self._loop_names:
            raise ValueError(f"stage 名与 loop 名冲突: {name}")
        self._stage_names.add(name)
        self._flow.append(stage_item)
        return self

    def agent(self, name: str, **fields: Any) -> "Pipeline":
        """声明一个 agent（对应 YAML `agents` 的一项）。

        参数:
            name: agent 名（唯一）。
            **fields: 其余 agent 字段（working_dir/task/llm_group/tool_group/
                node_id/proxy_node/quick_mode/restore_session/no_interaction_mode/
                access_acl/additional_args）。未知字段会被忽略并告警式保留。
        """
        agent_name = str(name or "").strip()
        if not agent_name:
            raise ValueError("agent 缺少 name")
        if agent_name in self._agent_names:
            raise ValueError(f"重复的 agent 名: {agent_name}")
        self._agent_names.add(agent_name)
        item: Dict[str, Any] = {"name": agent_name}
        for key, value in fields.items():
            if key in _AGENT_KEYS and key != "name":
                item[key] = value
        self._agents.append(item)
        return self

    def spec(self, text: str) -> "Pipeline":
        """设置流水线背景（对应 YAML 顶层 `spec` 字段）。"""
        self._spec_text = str(text or "")
        return self

    def default_on_error(self, mode: str) -> "Pipeline":
        """设置顶层默认失败策略（对应 YAML 顶层 `default_on_error`）。"""
        self._default_on_error = str(mode or "").strip()
        return self

    # ------------------------------------------------------------------
    # 导出（供 orchestration_loader 读取）
    # ------------------------------------------------------------------
    @property
    def agents(self) -> List[Dict[str, Any]]:
        """agent 定义列表（与 YAML `agents` 同构）。"""
        return list(self._agents)

    @property
    def flow(self) -> List[Dict[str, Any]]:
        """阶段列表（与 YAML `flow` 同构）。"""
        return list(self._flow)

    @property
    def spec_text(self) -> str:
        """流水线背景文本（对应 YAML 顶层 `spec`）。"""
        return self._spec_text

    @property
    def default_on_error_value(self) -> str:
        """顶层默认失败策略（对应 YAML 顶层 `default_on_error`）。"""
        return self._default_on_error

    def to_dict(self) -> Dict[str, Any]:
        """导出为与 YAML 编排文件解析结果同构的字典。

        返回:
            {"agents": [...], "flow": [...], "spec": str, "default_on_error": str}
            仅包含非空的可选字段（spec/default_on_error 为空时不写入）。
        """
        data: Dict[str, Any] = {
            "agents": list(self._agents),
            "flow": list(self._flow),
        }
        if self._spec_text:
            data["spec"] = self._spec_text
        if self._default_on_error:
            data["default_on_error"] = self._default_on_error
        return data
