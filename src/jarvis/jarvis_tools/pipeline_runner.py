# -*- coding: utf-8 -*-
"""pipeline_runner 工具：内置多 Agent 编排执行引擎（通用基础设施）。

把编排文件（含 `agents` 定义与可选 `flow` 顺序）解析后，按 `flow` 声明的
阶段构建 DAG（有向无环图），用常驻 `jvs` Agent 并行调度各阶段，通过
`status_file` 同步等待每个阶段完成、校验产物落盘、把上阶段产物路径传入
下阶段，实现"规划 → 生成 → 验证 → 门禁"这类多 Agent 流水线的自动编排。

设计取向（详见 docs/design/ai-dark-factory-orchestration-engine.md）：
- **只协调不执行**（sw-controller 模式）：本工具不写码、不测试，只负责按
  依赖关系调度与产物传递，具体阶段/产物/门禁由使用方的编排文件声明。
- **通用性**：不依赖任何插件业务。任何插件/用户都能用它定义自己的多 Agent
  流水线，黑灯工厂只是使用者之一。
- **DAG 编排**：`flow` 支持 `depends_on`/`input`(多输入)/`when`(条件)/
  `on_error`(失败策略)/`retry`(重试)，并行度 `max_workers` 默认 4。
- **复用现有机制**：阶段 Agent 统一为常驻 `jvs` Agent（无仓库文件锁，可并行），
  通过 `send_to_agent(wait=true, status_file=...)` 同步等待完成。
- **保持人工审批关口**：`gate: true` 的阶段完成后停住，默认 `approve=false`，
  必须人工确认才放行（不完全无人值守）。

编排文件 `flow` 为可选字段；无 `flow` 时本工具报错提示（此时应由
`@OrganizeAgents` 负责只创建 agent，行为不变）。
"""
import json
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

import yaml

from jarvis.jarvis_tools.gateway_manager import GatewayManagerTool
from jarvis.jarvis_tools.pipeline_events import emit_remote
from jarvis.jarvis_tools.pipeline_events import get_event_bus
from jarvis.jarvis_tools.pipeline_events import is_local_pump_active
from jarvis.jarvis_utils.output import PrettyOutput

# 状态文件轮询间隔（秒）
_POLL_INTERVAL = 2.0
# 单阶段默认超时（秒）：30 分钟
_DEFAULT_STAGE_TIMEOUT = 30 * 60
# 工作产物目录名（相对 working_dir，收进 .jarvis 隐藏目录统一管理）
_ARTIFACT_DIR = ".jarvis/artifacts"
# 默认并行度
_DEFAULT_MAX_WORKERS = 4


class PipelineRunnerTool:
    """内置多 Agent 编排执行引擎。

    读取编排文件（agents + flow），把 flow 解析为 DAG，用常驻 jvs Agent 并行
    调度各阶段，poll status_file 等待完成，传递产物，门禁停住。
    """

    name = "pipeline_runner"
    description = (
        "内置多 Agent 编排执行引擎：读取编排 YAML（agents + flow），按 flow 声明的"
        "依赖关系构建 DAG，用常驻 jvs Agent 并行驱动各阶段，同步等待每个阶段完成、"
        "校验产物落盘、把上阶段产物路径传入下阶段，实现多 Agent 流水线的自动编排。"
        "支持并行（max_workers 默认 4）、多输入（input 列表）、条件（when）、失败"
        "策略（on_error: abort/continue/skip_dependents）、重试（retry）。门禁阶段"
        "（gate: true）完成后停住，默认 approve=false，需人工审批确认才放行。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "orchestration_file": {
                "type": "string",
                "description": "编排 YAML 文件路径（含 agents 定义与可选 flow 顺序）",
            },
            "working_dir": {
                "type": "string",
                "description": "工作目录（默认当前目录），产物 .jarvis/artifacts/ 在其中创建",
            },
            "approve": {
                "type": "boolean",
                "description": "门禁阶段是否已获人工审批（默认 false，需人工确认）",
            },
            "max_workers": {
                "type": "integer",
                "description": "并行度上限（默认 4），限制同时执行的阶段 Agent 数",
            },
            "dry_run": {
                "type": "boolean",
                "description": (
                    "仅预演编排计划（默认 false）：解析+校验+拓扑排序，输出将要"
                    "执行的 DAG（阶段/依赖/并行批次/产物/门禁/条件/重试/失败策略），"
                    "不创建 Agent、不派发任务。用于校验动态生成的编排文件。"
                ),
            },
        },
        "required": ["orchestration_file"],
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """按编排文件 flow 驱动多 Agent 流水线（DAG 调度）。"""
        args = args or {}
        orchestration_file = str(args.get("orchestration_file") or "").strip()
        working_dir = str(args.get("working_dir") or "").strip() or "."
        approve = bool(args.get("approve", False))
        dry_run = bool(args.get("dry_run", False))
        max_workers = int(
            args.get("max_workers", _DEFAULT_MAX_WORKERS) or _DEFAULT_MAX_WORKERS
        )

        # 1. 校验参数
        if not orchestration_file:
            return self._error("缺少必填参数 orchestration_file（编排 YAML 路径）")

        orch_path = Path(orchestration_file)
        if not orch_path.exists() or not orch_path.is_file():
            return self._error(f"编排文件不存在: {orchestration_file}")

        work_dir = Path(working_dir).resolve()
        if not work_dir.is_dir():
            return self._error(f"工作目录不存在: {working_dir}")

        if max_workers < 1:
            max_workers = 1

        # 2. 读取编排文件
        try:
            content = orch_path.read_text(encoding="utf-8")
            orch = yaml.safe_load(content) or {}
        except Exception as e:  # pylint: disable=broad-except
            return self._error(f"编排文件解析失败: {e}")

        agents = orch.get("agents") or []
        flow = orch.get("flow") or []
        if not agents:
            return self._error("编排文件缺少 agents 定义")
        if not flow:
            return self._error(
                "编排文件缺少 flow 字段（阶段顺序）。无 flow 时请用 @OrganizeAgents "
                "只创建 agent，本工具仅驱动带 flow 的流水线。"
            )

        agents_by_name = {a.get("name"): a for a in agents if a.get("name")}
        default_on_error = str(orch.get("default_on_error") or "abort").strip()

        # 3. 初始化产物目录（按 pipeline_id 隔离，避免多条流水线同目录冲突）
        pipeline_id = self._make_pipeline_id(orchestration_file)
        if dry_run:
            # dry-run 仅预演不落盘，用公共目录展示即可
            artifact_dir = work_dir / _ARTIFACT_DIR
        else:
            artifact_dir = work_dir / _ARTIFACT_DIR / pipeline_id
        try:
            artifact_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # pylint: disable=broad-except
            return self._error(f"无法创建产物目录 {artifact_dir}: {e}")

        # 4. 构建 DAG（解析 + 校验 + 环检测）
        dag_build = self._build_dag(flow, agents_by_name, default_on_error)
        if not dag_build["success"]:
            return self._error(dag_build["error"])
        nodes = dag_build["nodes"]

        # 读取编排文件顶层 spec 字段作为各阶段背景（可选；没有则不注入）
        inline_spec = orch.get("spec")
        spec_summary = (
            str(inline_spec).strip()
            if isinstance(inline_spec, str) and str(inline_spec).strip()
            else ""
        )

        # 4.5 dry-run：仅预演编排计划，不创建 Agent、不派发任务
        if dry_run:
            return self._dry_run_plan(
                nodes=nodes,
                agents_by_name=agents_by_name,
                default_on_error=default_on_error,
                max_workers=max_workers,
                approve=approve,
                artifact_dir=artifact_dir,
            )

        # 4.6 广播起始事件（供前端可视化），pipeline_id 已在第 3 步生成
        self._emit(
            pipeline_id,
            "pipeline_start",
            orchestration_file=str(orch_path),
            working_dir=str(work_dir),
            max_workers=max_workers,
            approve=approve,
            default_on_error=default_on_error,
            nodes=[
                {
                    "stage": n["stage"],
                    "agent": n["agent"],
                    "depends_on": list(n["depends_on"]),
                    "input": list(n["input"]),
                    "output": n["output"],
                    "gate": n["gate"],
                    "when": n["when"],
                    "retry": n["retry"],
                    "on_error": n["on_error"],
                }
                for n in nodes
            ],
        )

        # 5. 创建常驻 jvs Agent（每个 stage 一个）
        agent_created = self._create_stage_agents(
            nodes, agents_by_name, work_dir, pipeline_id
        )
        if not agent_created["success"]:
            self._emit(pipeline_id, "pipeline_done", success=False, final_status="failed")
            return self._error(agent_created["error"])
        agent_map = agent_created["agent_map"]

        # 5.1 广播 stage → agent_id 映射
        self._emit(pipeline_id, "pipeline_agents", agent_map=dict(agent_map))

        # 6. 调度执行（并行 DAG）
        return self._schedule(
            nodes=nodes,
            agent_map=agent_map,
            agents_by_name=agents_by_name,
            work_dir=work_dir,
            artifact_dir=artifact_dir,
            spec_summary=spec_summary,
            approve=approve,
            max_workers=max_workers,
            pipeline_id=pipeline_id,
        )

    # ------------------------------------------------------------------
    # 进度事件（供前端可视化，纯副作用，不影响执行语义）
    # ------------------------------------------------------------------
    def _emit(self, pipeline_id: str, event_type: str, **fields: Any) -> None:
        """向全局事件总线写入一条流水线进度事件。

        纯副作用：任何异常都被吞掉，绝不影响流水线执行。

        pipeline_runner 可能运行在 web_gateway 进程内（如前端「运行流水线」），
        也可能运行在 Agent 进程内（如用户对话 Agent 调用本工具）。事件泵
        （drain 并广播给前端）只存在于 web_gateway 进程，因此：
        - 本地事件泵已激活（本进程即 web_gateway）：只写本地进程内总线；
        - 否则（Agent 进程）：除写本地总线外，还通过 HTTP 上报到 master 网关，
          由网关侧 /api/pipeline-events 写入网关进程总线，从而被事件泵读到。
        """
        try:
            event: Dict[str, Any] = {"pipeline_id": pipeline_id, "type": event_type}
            event.update(fields)
            get_event_bus().emit(event)
            if not is_local_pump_active():
                emit_remote(event)
        except Exception:  # pylint: disable=broad-except
            pass

    @staticmethod
    def _make_pipeline_id(orchestration_file: str) -> str:
        """生成稳定唯一的 pipeline_id：<编排文件名>-<时间戳>-<短随机>。"""
        stem = Path(orchestration_file).stem or "pipeline"
        return f"{stem}-{int(time.time())}-{uuid.uuid4().hex[:6]}"

    # ------------------------------------------------------------------
    # DAG 构建
    # ------------------------------------------------------------------
    def _build_dag(
        self,
        flow: List[Dict[str, Any]],
        agents_by_name: Dict[str, Any],
        default_on_error: str = "abort",
    ) -> Dict[str, Any]:
        """解析 flow 为 DAG 节点列表，补全 depends_on/input，环检测。

        - `depends_on` 缺省 = 上一个 stage（线性兼容）。
        - `input` 单字符串自动转单元素列表。
        - `on_error` 缺省回退到编排文件顶层 `default_on_error`，再缺省 abort。
        - 校验 agent 引用、重复 stage 名、output 唯一、环检测。

        返回:
            {"success": True, "nodes": [...]} 或 {"success": False, "error": str}
        """
        if default_on_error not in ("abort", "continue", "skip_dependents"):
            default_on_error = "abort"

        nodes: List[Dict[str, Any]] = []
        stage_names: List[str] = []
        output_owners: Dict[str, str] = {}
        for idx, stage in enumerate(flow):
            stage_name = str(stage.get("stage") or f"stage_{idx}").strip()
            if not stage_name:
                return {"success": False, "error": f"flow 第 {idx + 1} 项缺少 stage 名"}
            if stage_name in stage_names:
                return {
                    "success": False,
                    "error": f"flow 中存在重复 stage 名: {stage_name}",
                }
            stage_names.append(stage_name)

            agent_name = str(stage.get("agent") or "").strip()
            if agent_name not in agents_by_name:
                return {
                    "success": False,
                    "error": f"flow 阶段 '{stage_name}' 引用了未定义的 agent '{agent_name}'",
                }

            # depends_on 缺省 = 上一个 stage
            depends_on = stage.get("depends_on")
            if depends_on is None:
                depends_on = [stage_names[idx - 1]] if idx > 0 else []
            elif isinstance(depends_on, str):
                depends_on = [depends_on]
            depends_on = [str(d).strip() for d in (depends_on or [])]
            for d in depends_on:
                if d not in stage_names:
                    return {
                        "success": False,
                        "error": f"flow 阶段 '{stage_name}' 依赖了不存在的 stage '{d}'",
                    }

            # input 单字符串自动转单元素列表
            input_ref = stage.get("input")
            if input_ref is None:
                input_list: List[str] = []
            elif isinstance(input_ref, str):
                input_list = [input_ref.strip()] if input_ref.strip() else []
            elif isinstance(input_ref, list):
                input_list = [str(i).strip() for i in input_ref if str(i).strip()]
            else:
                input_list = []

            on_error = str(stage.get("on_error") or default_on_error).strip()
            if on_error not in ("abort", "continue", "skip_dependents"):
                on_error = default_on_error

            output = str(stage.get("output") or "").strip()
            if output:
                if output in output_owners:
                    return {
                        "success": False,
                        "error": (
                            f"flow 阶段 '{stage_name}' 与 '{output_owners[output]}' "
                            f"声明了相同的产物路径 '{output}'（产物须唯一）"
                        ),
                    }
                output_owners[output] = stage_name

            nodes.append(
                {
                    "stage": stage_name,
                    "agent": agent_name,
                    "depends_on": depends_on,
                    "input": input_list,
                    "output": output,
                    "gate": bool(stage.get("gate", False)),
                    "when": str(stage.get("when") or "").strip() or None,
                    "retry": int(stage.get("retry", 0) or 0),
                    "on_error": on_error,
                }
            )

        # 环检测（Kahn 拓扑排序，有环返回 None）
        if self._topo_sort(nodes) is None:
            return {
                "success": False,
                "error": "flow 依赖存在环，无法执行（请检查 depends_on）",
            }
        return {"success": True, "nodes": nodes}

    def _topo_sort(self, nodes: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """Kahn 拓扑排序；有环返回 None。"""
        by_stage = {n["stage"]: n for n in nodes}
        indegree = {n["stage"]: len(n["depends_on"]) for n in nodes}
        dependents: Dict[str, List[str]] = {n["stage"]: [] for n in nodes}
        for n in nodes:
            for d in n["depends_on"]:
                dependents[d].append(n["stage"])

        queue = [s for s, deg in indegree.items() if deg == 0]
        order: List[str] = []
        while queue:
            s = queue.pop(0)
            order.append(s)
            for child in dependents[s]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if len(order) != len(nodes):
            return None
        return [by_stage[s] for s in order]

    # ------------------------------------------------------------------
    # dry-run 预演
    # ------------------------------------------------------------------
    def _dry_run_plan(
        self,
        nodes: List[Dict[str, Any]],
        agents_by_name: Dict[str, Any],
        default_on_error: str,
        max_workers: int,
        approve: bool,
        artifact_dir: Path,
    ) -> Dict[str, Any]:
        """仅预演编排计划：输出 DAG 执行计划，不创建 Agent、不派发任务。

        用于校验动态生成的编排文件：解析 + 校验 + 拓扑排序 + 分批，
        打印阶段/依赖/并行批次/产物/门禁/条件/重试/失败策略。
        """
        lines: List[str] = []
        lines.append("🧪 dry-run：编排计划预演（不创建 Agent、不派发任务）")
        lines.append(f"  产物目录: {artifact_dir}")
        lines.append(f"  并行度上限: {max_workers}")
        lines.append(f"  顶层 default_on_error: {default_on_error}")
        lines.append(f"  门禁 approve: {approve}")
        lines.append(f"  阶段总数: {len(nodes)}")

        # 拓扑排序（_build_dag 已做环检测，此处再取一次顺序）
        order = self._topo_sort(nodes)
        if order is None:
            return self._error("dry-run 失败：编排存在环，无法拓扑排序")

        # 按"依赖层级"分批：每批为可并行执行的阶段集合
        batches = self._plan_batches(nodes)
        lines.append("")
        lines.append("📋 执行计划（按并行批次）：")
        for i, batch in enumerate(batches, 1):
            parallel = len(batch) > 1
            tag = "并行" if parallel else "串行"
            lines.append(f"  批次 {i} [{tag}]（{len(batch)} 个阶段）:")
            for n in batch:
                lines.append(self._format_stage_plan(n, agents_by_name))

        # 阶段清单（拓扑序）
        lines.append("")
        lines.append("🔗 拓扑序: " + " → ".join(n["stage"] for n in order))

        gate_stages = [n["stage"] for n in nodes if n["gate"]]
        if gate_stages:
            lines.append(f"🚧 门禁阶段: {', '.join(gate_stages)}（完成后停住等人工审批）")

        return {"success": True, "stdout": "\n".join(lines), "stderr": ""}

    def _plan_batches(self, nodes: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """按依赖层级把节点分批（同批可并行），用于 dry-run 展示。

        与 `_schedule` 的 ready 批次语义一致：每批 = 依赖都在更早批次完成的节点。
        """
        by_stage = {n["stage"]: n for n in nodes}
        remaining = {n["stage"]: set(n["depends_on"]) for n in nodes}
        done: set = set()
        batches: List[List[Dict[str, Any]]] = []
        while remaining:
            ready = [
                s for s, deps in remaining.items() if deps.issubset(done)
            ]
            if not ready:
                break  # 有环时 _build_dag 已拦截，此处仅防御
            batch = [by_stage[s] for s in ready]
            batches.append(batch)
            for s in ready:
                done.add(s)
                del remaining[s]
        return batches

    def _format_stage_plan(
        self, node: Dict[str, Any], agents_by_name: Dict[str, Any]
    ) -> str:
        """格式化单个阶段的计划行。"""
        agent_def = agents_by_name.get(node["agent"], {})
        working_dir = agent_def.get("working_dir") or "."
        parts = [f"    - {node['stage']} (agent={node['agent']}, dir={working_dir})"]
        if node["depends_on"]:
            parts.append(f"依赖={','.join(node['depends_on'])}")
        if node["input"]:
            parts.append(f"输入={','.join(node['input'])}")
        parts.append(f"产物={node['output'] or '（无）'}")
        if node["gate"]:
            parts.append("门禁")
        if node["when"]:
            parts.append(f"when={node['when']}")
        if node["retry"]:
            parts.append(f"retry={node['retry']}")
        parts.append(f"on_error={node['on_error']}")
        return "  ".join(parts)

    # ------------------------------------------------------------------
    # 常驻 Agent 创建
    # ------------------------------------------------------------------
    def _create_stage_agents(
        self,
        nodes: List[Dict[str, Any]],
        agents_by_name: Dict[str, Any],
        work_dir: Path,
        pipeline_id: str = "",
    ) -> Dict[str, Any]:
        """为每个 stage 创建常驻 jvs Agent（type: agent）。

        返回:
            {"success": True, "agent_map": {stage: agent_id}} 或错误
        """
        gw = GatewayManagerTool()
        agent_map: Dict[str, str] = {}
        for node in nodes:
            stage_name = node["stage"]
            agent_def = agents_by_name[node["agent"]]
            working_dir = str(agent_def.get("working_dir") or str(work_dir))
            agent_id, last_error = self._create_agent_with_retry(
                gw, stage_name, working_dir, pipeline_id=pipeline_id
            )
            if not agent_id:
                return {
                    "success": False,
                    "error": (
                        f"创建阶段 [{stage_name}] 常驻 Agent 失败（已重试）: "
                        f"{last_error}"
                    ),
                }
            agent_map[stage_name] = agent_id
            PrettyOutput.auto_print(
                f"  🛠 阶段 [{stage_name}] 常驻 Agent 就绪: {agent_id}"
            )
        return {"success": True, "agent_map": agent_map}

    def _create_agent_with_retry(
        self,
        gw: Any,
        stage_name: str,
        working_dir: str,
        pipeline_id: str = "",
        max_attempts: int = 3,
    ) -> tuple:
        """创建常驻 Agent，失败时重试（间隔递增）。

        返回:
            (agent_id, error): agent_id 非空表示成功；失败时 agent_id 为空字符串，
            error 为最后一次错误信息。
        """
        last_error = ""
        # Agent 名加 pipeline_id 前缀，避免多条流水线同目录创建同名 Agent 冲突
        agent_name = (
            f"df_{pipeline_id}_{stage_name}" if pipeline_id else f"df_{stage_name}"
        )
        for attempt in range(1, max_attempts + 1):
            create_result = gw._create_agent(
                agent_type="agent",
                working_dir=working_dir,
                name=agent_name,
            )
            if create_result.get("success"):
                try:
                    agent_info = json.loads(create_result["stdout"])
                    agent_id = str(agent_info.get("agent_id") or "")
                except (json.JSONDecodeError, AttributeError, TypeError):
                    agent_id = ""
                if agent_id:
                    if attempt > 1:
                        PrettyOutput.auto_print(
                            f"  ♻️ 阶段 [{stage_name}] 第 {attempt} 次创建 Agent 成功"
                        )
                    return agent_id, ""
                last_error = "创建成功但无法获取 agent_id"
            else:
                last_error = str(create_result.get("stderr") or "未知错误")
            if attempt < max_attempts:
                PrettyOutput.auto_print(
                    f"  ⚠️ 阶段 [{stage_name}] 创建 Agent 失败"
                    f"（第 {attempt}/{max_attempts} 次）: {last_error}，"
                    f"{attempt} 秒后重试"
                )
                time.sleep(attempt)
        return "", last_error

    # ------------------------------------------------------------------
    # 单阶段执行
    # ------------------------------------------------------------------
    def _run_stage(
        self,
        node: Dict[str, Any],
        agent_id: str,
        agents_by_name: Dict[str, Any],
        work_dir: Path,
        artifact_dir: Path,
        spec_summary: str,
        approve: bool,
    ) -> Dict[str, Any]:
        """执行单个 stage：组装任务消息 → send_to_agent(wait=true, status_file) → 校验产物。

        返回:
            {
              "stage": str, "status": "completed"|"failed",
              "output": str, "result": {...}, "error": str,
              "gate_blocked": bool, "approval_path": str,
            }
        """
        stage_name = node["stage"]
        agent_def = agents_by_name[node["agent"]]
        task_desc = str(agent_def.get("task") or agent_def.get("task_desc") or "")
        output = node["output"]
        input_list = node["input"]

        status_file = artifact_dir / f"{stage_name}.status"
        # 清空旧 status_file（支持重试）
        if status_file.exists():
            try:
                status_file.unlink()
            except OSError:
                pass

        # 组装任务消息
        message = self._build_stage_message(
            task_desc=task_desc,
            stage=stage_name,
            input_list=input_list,
            output=output,
            spec_summary=spec_summary,
            status_file=str(status_file),
        )

        PrettyOutput.auto_print(
            f"▶ 阶段 [{stage_name}] agent={node['agent']} 启动（send_to_agent wait）"
        )

        gw = GatewayManagerTool()
        send_result = gw._send_to_agent(
            agent_id=agent_id,
            message=message,
            wait=True,
            status_file=str(status_file),
        )

        if not send_result["success"]:
            return {
                "stage": stage_name,
                "status": "failed",
                "output": output,
                "result": {},
                "error": send_result["stderr"] or "阶段 Agent 任务失败",
                "gate_blocked": False,
                "approval_path": "",
            }

        # 读取 status_file 内容作为结构化结果（供 when 表达式引用）
        result = self._read_status(status_file)

        # 校验产物落盘
        if output:
            output_path = work_dir / output
            if not output_path.exists():
                return {
                    "stage": stage_name,
                    "status": "failed",
                    "output": output,
                    "result": result,
                    "error": f"阶段 [{stage_name}] 声明产物 {output} 未落盘",
                    "gate_blocked": False,
                    "approval_path": "",
                }
            # 若产物是 JSON，读取其字段合并进 result（status_file 字段优先），
            # 供下游 when 表达式引用产物内容（如 report.pass_rate）。
            artifact_json = self._read_artifact_json(output_path)
            if artifact_json:
                merged = dict(artifact_json)
                merged.update(result)
                result = merged

        # 门禁：停住等人工审批
        if node["gate"]:
            if not approve:
                approval_path = work_dir / (output or f"{stage_name}.approval.md")
                return {
                    "stage": stage_name,
                    "status": "completed",
                    "output": output,
                    "result": result,
                    "error": "",
                    "gate_blocked": True,
                    "approval_path": str(approval_path),
                }
            return {
                "stage": stage_name,
                "status": "completed",
                "output": output,
                "result": result,
                "error": "",
                "gate_blocked": False,
                "approval_path": "",
            }

        return {
            "stage": stage_name,
            "status": "completed",
            "output": output,
            "result": result,
            "error": "",
            "gate_blocked": False,
            "approval_path": "",
        }

    def _build_stage_message(
        self,
        task_desc: str,
        stage: str,
        input_list: List[str],
        output: str,
        spec_summary: str,
        status_file: str,
    ) -> str:
        """组装本阶段任务消息（含写 status_file 的完成指示）。"""
        parts: List[str] = []
        task = task_desc.strip()
        if task:
            parts.append(task)
        if spec_summary:
            parts.append(f"流水线背景:\n{spec_summary}")
        if input_list:
            parts.append(
                "本阶段输入产物:\n" + "\n".join(f"- {i}" for i in input_list)
            )
        parts.append(
            f"请完成本阶段职责后，将产物写入 {output or '（本阶段无产物要求）'}。"
            f"完成后，把结果写入状态文件 {status_file}，内容为 JSON："
            f'{{"status": "completed", "output": "<产物路径>"}}；'
            f"若失败则写 {{\"status\": \"failed\", \"error\": \"<原因>\"}}。"
        )
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # 并行调度
    # ------------------------------------------------------------------
    def _schedule(
        self,
        nodes: List[Dict[str, Any]],
        agent_map: Dict[str, str],
        agents_by_name: Dict[str, Any],
        work_dir: Path,
        artifact_dir: Path,
        spec_summary: str,
        approve: bool,
        max_workers: int,
        pipeline_id: str = "",
    ) -> Dict[str, Any]:
        """并行调度 DAG：每轮收集依赖已满足的 ready 节点，线程池并发执行。

        处理 when（条件跳过）、on_error（失败策略）、retry（重试）、门禁。
        """
        state: Dict[str, str] = {n["stage"]: "pending" for n in nodes}
        results: Dict[str, Dict[str, Any]] = {}
        stdout_lines: List[str] = []
        gate_blocked_stage: Optional[str] = None
        gate_approval_path = ""

        def _deps_satisfied(n: Dict[str, Any]) -> bool:
            for d in n["depends_on"]:
                if state.get(d) != "completed":
                    return False
            return True

        def _deps_blocked(n: Dict[str, Any]) -> bool:
            # 任一依赖失败/跳过则该节点无法执行
            return any(state.get(d) in ("failed", "skipped") for d in n["depends_on"])

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            while True:
                # 依赖被阻塞的节点直接跳过
                for n in nodes:
                    if state[n["stage"]] == "pending" and _deps_blocked(n):
                        state[n["stage"]] = "skipped"
                        results[n["stage"]] = {
                            "stage": n["stage"],
                            "status": "skipped",
                            "output": n["output"],
                            "result": {},
                            "error": "依赖失败/跳过，本阶段被跳过",
                        }
                        stdout_lines.append(
                            f"  ⏭ 阶段 [{n['stage']}] 因依赖失败被跳过"
                        )
                        self._emit(
                            pipeline_id,
                            "stage_update",
                            stage=n["stage"],
                            status="skipped",
                            agent_id=agent_map.get(n["stage"], ""),
                            output=n["output"],
                            error="依赖失败/跳过，本阶段被跳过",
                        )

                # 收集 ready 节点
                ready = [
                    n
                    for n in nodes
                    if state[n["stage"]] == "pending"
                    and _deps_satisfied(n)
                    and not _deps_blocked(n)
                ]

                if not ready:
                    # 无 ready 节点：检查是否全部结束
                    if all(
                        s in ("completed", "failed", "skipped")
                        for s in state.values()
                    ):
                        break
                    # 有 pending 但无 ready 且无 running：死锁保护
                    if all(s != "running" for s in state.values()):
                        break
                    continue

                # when 条件评估（不满足的节点标记 skipped）
                effective_ready: List[Dict[str, Any]] = []
                for n in ready:
                    if n["when"]:
                        ok, err = self._eval_when(n["when"], results)
                        if not ok:
                            state[n["stage"]] = "skipped"
                            results[n["stage"]] = {
                                "stage": n["stage"],
                                "status": "skipped",
                                "output": n["output"],
                                "result": {},
                                "error": (
                                    f"when 条件不满足: {n['when']}"
                                    + (f"（{err}）" if err else "")
                                ),
                            }
                            stdout_lines.append(
                                f"  ⏭ 阶段 [{n['stage']}] 因 when 条件不满足被跳过"
                            )
                            self._emit(
                                pipeline_id,
                                "stage_update",
                                stage=n["stage"],
                                status="skipped",
                                agent_id=agent_map.get(n["stage"], ""),
                                output=n["output"],
                                error=f"when 条件不满足: {n['when']}",
                            )
                            continue
                    effective_ready.append(n)

                if not effective_ready:
                    continue

                # 并发执行 ready 节点
                futures = {}
                for n in effective_ready:
                    state[n["stage"]] = "running"
                    agent_id = agent_map[n["stage"]]
                    self._emit(
                        pipeline_id,
                        "stage_update",
                        stage=n["stage"],
                        status="running",
                        agent_id=agent_id,
                        output=n["output"],
                    )
                    futures[
                        pool.submit(
                            self._run_stage,
                            n,
                            agent_id,
                            agents_by_name,
                            work_dir,
                            artifact_dir,
                            spec_summary,
                            approve,
                        )
                    ] = n

                for fut in as_completed(futures):
                    n = futures[fut]
                    try:
                        stage_result = fut.result()
                    except Exception as e:  # pylint: disable=broad-except
                        stage_result = {
                            "stage": n["stage"],
                            "status": "failed",
                            "output": n["output"],
                            "result": {},
                            "error": f"阶段执行异常: {e}",
                            "gate_blocked": False,
                            "approval_path": "",
                        }
                    self._handle_stage_result(
                        n=n,
                        stage_result=stage_result,
                        state=state,
                        results=results,
                        stdout_lines=stdout_lines,
                        work_dir=work_dir,
                        pipeline_id=pipeline_id,
                    )
                    # 门禁停住
                    if stage_result.get("gate_blocked"):
                        gate_blocked_stage = n["stage"]
                        gate_approval_path = stage_result.get("approval_path", "")
                    # abort 中止（仅当该阶段最终失败；重试中不中止）
                    if (
                        state[n["stage"]] == "failed"
                        and n["on_error"] == "abort"
                    ):
                        self._emit(
                            pipeline_id,
                            "pipeline_done",
                            success=False,
                            final_status="aborted",
                            failed_stage=n["stage"],
                        )
                        return self._abort_result(
                            stage_name=n["stage"],
                            error=str(stage_result.get("error", "") or ""),
                            stdout_lines=stdout_lines,
                            artifact_dir=artifact_dir,
                        )

        # 全部调度完成
        if gate_blocked_stage:
            stdout_lines.append(
                f"  ⛔ 门禁阶段 [{gate_blocked_stage}] 已产出审批报告: {gate_approval_path}"
            )
            stdout_lines.append(
                "  ⛔ 待人工审批：请确认审批报告后，以 approve=true 重跑门禁确认。"
            )
            self._emit(
                pipeline_id,
                "pipeline_done",
                success=True,
                final_status="gate_blocked",
                gate_stage=gate_blocked_stage,
                approval_path=gate_approval_path,
            )
            return {
                "success": True,
                "stdout": "\n".join(stdout_lines),
                "stderr": "",
            }

        # 检查是否有 failed 阶段
        failed = [s for s, st in state.items() if st == "failed"]
        if failed:
            errs = [
                results[s].get("error", "") for s in failed if results.get(s)
            ]
            stdout_lines.append("❌ 流水线存在失败阶段")
            self._emit(
                pipeline_id,
                "pipeline_done",
                success=False,
                final_status="failed",
                failed_stages=failed,
            )
            return {
                "success": False,
                "stdout": "\n".join(stdout_lines),
                "stderr": (
                    "失败阶段: "
                    + ", ".join(failed)
                    + "；"
                    + "；".join(e for e in errs if e)
                ),
            }

        stdout_lines.append("🏁 流水线全部阶段完成")
        self._emit(
            pipeline_id,
            "pipeline_done",
            success=True,
            final_status="completed",
        )
        return {"success": True, "stdout": "\n".join(stdout_lines), "stderr": ""}

    def _handle_stage_result(
        self,
        n: Dict[str, Any],
        stage_result: Dict[str, Any],
        state: Dict[str, str],
        results: Dict[str, Dict[str, Any]],
        stdout_lines: List[str],
        work_dir: Path,
        pipeline_id: str = "",
    ) -> None:
        """处理单个 stage 的执行结果（含 retry 重试）。"""
        stage_name = n["stage"]
        status = stage_result["status"]

        if status == "completed":
            state[stage_name] = "completed"
            results[stage_name] = stage_result
            if stage_result.get("output"):
                stdout_lines.append(
                    f"  ✅ 阶段 [{stage_name}] 完成，产物: {stage_result['output']}"
                )
            else:
                stdout_lines.append(f"  ✅ 阶段 [{stage_name}] 完成")
            self._emit(
                pipeline_id,
                "stage_update",
                stage=stage_name,
                status="completed",
                output=n["output"],
                artifact=stage_result.get("output", ""),
            )
            return

        # failed：处理 retry 重试
        retry = n["retry"]
        if retry > 0:
            retry_count = results.get(stage_name, {}).get("_retry_count", 0) + 1
            if retry_count <= retry:
                stage_result["_retry_count"] = retry_count
                results[stage_name] = stage_result
                state[stage_name] = "pending"
                stdout_lines.append(
                    f"  🔁 阶段 [{stage_name}] 失败，重试 {retry_count}/{retry}"
                )
                self._emit(
                    pipeline_id,
                    "stage_update",
                    stage=stage_name,
                    status="retry",
                    output=n["output"],
                    retry_count=retry_count,
                    retry_max=retry,
                    error=str(stage_result.get("error", "") or ""),
                )
                return
            # 重试耗尽，按失败处理
            state[stage_name] = "failed"
            results[stage_name] = stage_result
            stdout_lines.append(
                f"  ❌ 阶段 [{stage_name}] 失败（重试耗尽）: "
                f"{stage_result.get('error', '')}"
            )
            self._emit(
                pipeline_id,
                "stage_update",
                stage=stage_name,
                status="failed",
                output=n["output"],
                error=str(stage_result.get("error", "") or ""),
            )
            return

        # 无重试，直接失败
        state[stage_name] = "failed"
        results[stage_name] = stage_result
        stdout_lines.append(
            f"  ❌ 阶段 [{stage_name}] 失败: {stage_result.get('error', '')}"
        )
        self._emit(
            pipeline_id,
            "stage_update",
            stage=stage_name,
            status="failed",
            output=n["output"],
            error=str(stage_result.get("error", "") or ""),
        )
        # on_error=skip_dependents/continue：失败但不中止，
        # 依赖它的节点会在下一轮被 _deps_blocked 跳过。

    def _abort_result(
        self,
        stage_name: str,
        error: str,
        stdout_lines: List[str],
        artifact_dir: Path,
    ) -> Dict[str, Any]:
        """构造 abort 中止结果。"""
        stdout_lines.append(
            f"⛔ 流水线因阶段 [{stage_name}] 失败而中止（on_error=abort）"
        )
        return {
            "success": False,
            "stdout": "\n".join(stdout_lines),
            "stderr": (
                f"阶段 [{stage_name}] 失败: {error}。"
                f"产物保留在 {artifact_dir} 便于排查。"
            ),
        }

    # ------------------------------------------------------------------
    # when 受限表达式解析
    # ------------------------------------------------------------------
    def _eval_when(self, expr: str, results: Dict[str, Dict[str, Any]]) -> tuple:
        """受限表达式求值（白名单，不 eval 任意代码）。

        支持语法：`stage.field` 引用上游 stage 的 status_file 字段；
        比较 `==`/`!=`/`>=`/`<=`/`>`/`<`；逻辑 `&&`/`||`/`!`；字面量数字/字符串/布尔。

        返回:
            (ok, error): ok=True 表示条件满足，否则为 False 并附错误信息
        """
        try:
            substituted = self._substitute_refs(expr, results)
            value = self._eval_boolean(substituted)
            return bool(value), ""
        except Exception as e:  # pylint: disable=broad-except
            return False, f"when 表达式解析失败: {e}"

    def _substitute_refs(
        self, expr: str, results: Dict[str, Dict[str, Any]]
    ) -> str:
        """把 `stage.field` 引用替换为对应 stage 结果中的字段值（字符串形式）。"""

        def _lookup(match: "re.Match") -> str:
            stage_name = match.group(1)
            field = match.group(2)
            stage_result = results.get(stage_name, {})
            result_data = stage_result.get("result") or {}
            value = result_data.get(field)
            if value is None:
                return "None"
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, (int, float)):
                return str(value)
            return json.dumps(str(value), ensure_ascii=False)

        return re.sub(
            r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)", _lookup, expr
        )

    def _eval_boolean(self, expr: str) -> Any:
        """安全求值布尔表达式（只支持比较、逻辑、字面量，不 eval 任意代码）。"""
        expr = expr.strip()
        # 处理 ||
        parts = self._split_top_level(expr, "||")
        if len(parts) > 1:
            return any(self._eval_boolean(p) for p in parts)
        # 处理 &&
        parts = self._split_top_level(expr, "&&")
        if len(parts) > 1:
            return all(self._eval_boolean(p) for p in parts)
        e = parts[0].strip()
        if e.startswith("!"):
            return not self._eval_boolean(e[1:])
        if e.startswith("(") and e.endswith(")"):
            return self._eval_boolean(e[1:-1])
        # 比较表达式
        return self._eval_comparison(e)

    def _split_top_level(self, expr: str, op: str) -> List[str]:
        """按顶层操作符分割（忽略括号内与引号内的）。"""
        parts: List[str] = []
        depth = 0
        in_quote: Optional[str] = None
        current = ""
        i = 0
        while i < len(expr):
            ch = expr[i]
            if in_quote:
                current += ch
                if ch == in_quote:
                    in_quote = None
                i += 1
                continue
            if ch in ("'", '"'):
                in_quote = ch
                current += ch
                i += 1
                continue
            if ch == "(":
                depth += 1
                current += ch
                i += 1
                continue
            if ch == ")":
                depth -= 1
                current += ch
                i += 1
                continue
            if depth == 0 and expr[i : i + len(op)] == op:
                parts.append(current)
                current = ""
                i += len(op)
                continue
            current += ch
            i += 1
        parts.append(current)
        return parts

    def _find_top_level_op(self, expr: str, op: str) -> int:
        """在顶层查找操作符位置（忽略括号与引号内），找不到返回 -1。"""
        depth = 0
        in_quote: Optional[str] = None
        i = 0
        while i < len(expr):
            ch = expr[i]
            if in_quote:
                if ch == in_quote:
                    in_quote = None
                i += 1
                continue
            if ch in ("'", '"'):
                in_quote = ch
                i += 1
                continue
            if ch == "(":
                depth += 1
                i += 1
                continue
            if ch == ")":
                depth -= 1
                i += 1
                continue
            if depth == 0 and expr[i : i + len(op)] == op:
                return i
            i += 1
        return -1

    def _eval_comparison(self, e: str) -> bool:
        """求值单个比较表达式（或布尔/数值字面量）。"""
        e = e.strip()
        if e in ("true", "True"):
            return True
        if e in ("false", "False"):
            return False
        if e == "None":
            return False
        # 数值/字符串比较
        for op in ("==", "!=", ">=", "<=", ">", "<"):
            idx = self._find_top_level_op(e, op)
            if idx >= 0:
                left_s = e[:idx].strip()
                right_s = e[idx + len(op) :].strip()
                left = self._coerce(left_s)
                right = self._coerce(right_s)
                if op == "==":
                    return left == right
                if op == "!=":
                    return left != right
                if op == ">=":
                    return left >= right
                if op == "<=":
                    return left <= right
                if op == ">":
                    return left > right
                if op == "<":
                    return left < right
        # 无比较符：尝试数值/布尔字面量
        num = self._coerce(e)
        if isinstance(num, bool):
            return num
        if isinstance(num, (int, float)):
            return num != 0
        return bool(num)

    def _coerce(self, s: str) -> Any:
        """把字面量字符串转为数值/布尔/字符串（用于比较）。"""
        s = s.strip()
        if s in ("true", "True"):
            return True
        if s in ("false", "False"):
            return False
        if s == "None":
            return None
        # 带引号的字符串
        if (s.startswith('"') and s.endswith('"')) or (
            s.startswith("'") and s.endswith("'")
        ):
            return s[1:-1]
        # 数值
        try:
            if "." in s:
                return float(s)
            return int(s)
        except ValueError:
            return s

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    def _read_status(self, status_file: Path) -> Dict[str, Any]:
        """读取 status_file 内容（JSON），失败返回空 dict。"""
        try:
            if status_file.exists():
                data = json.loads(status_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except (json.JSONDecodeError, OSError):
            pass
        return {}

    def _read_artifact_json(self, artifact_path: Path) -> Dict[str, Any]:
        """若产物为 JSON 对象则读取其内容，否则返回空 dict。

        仅接受顶层为 dict 的 JSON，供 when 表达式引用产物字段。
        """
        try:
            if artifact_path.suffix.lower() != ".json":
                return {}
            data = json.loads(artifact_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError, ValueError):
            pass
        return {}



    def _error(self, msg: str) -> Dict[str, Any]:
        """构造错误返回。"""
        return {"success": False, "stdout": "", "stderr": msg}
