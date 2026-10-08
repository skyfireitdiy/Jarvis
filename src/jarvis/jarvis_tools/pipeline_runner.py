# -*- coding: utf-8 -*-
"""pipeline_runner 工具：内置多 Agent 编排执行引擎（通用基础设施）。

把编排文件（含 `agents` 定义与可选 `flow` 顺序）解析后，按 `flow` 声明的
阶段顺序，用 `jca -n --task-file` 逐个驱动阶段 agent，并通过 status_file
同步等待每个阶段完成、校验产物落盘、把上阶段产物路径写入下阶段 task-file，
实现"规划 → 生成 → 验证 → 门禁"这类多 Agent 流水线的自动顺序协作。

设计取向（详见 docs/design/ai-dark-factory-orchestration-engine.md）：
- **只协调不执行**（sw-controller 模式）：本工具不写码、不测试，只负责按序
  调度与产物传递，具体阶段/产物/门禁由使用方的编排文件声明。
- **通用性**：不依赖任何插件业务。任何插件/用户都能用它定义自己的多 Agent
  流水线，黑灯工厂只是使用者之一。
- **复用现有机制**：复用 `jca -n --task-file`（非交互执行入口）与
  `status_file`（完成状态回传），不重复造轮子。
- **保持人工审批关口**：`gate: true` 的阶段完成后停住，默认 `approve=false`，
  必须人工确认才放行（不完全无人值守）。

编排文件 `flow` 为可选字段；无 `flow` 时本工具报错提示（此时应由
`@OrganizeAgents` 负责只创建 agent，行为不变）。
"""
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

import yaml

from jarvis.jarvis_utils.output import PrettyOutput

# 状态文件轮询间隔（秒）
_POLL_INTERVAL = 2.0
# 单阶段默认超时（秒）：30 分钟
_DEFAULT_STAGE_TIMEOUT = 30 * 60
# 工作产物目录名（相对 working_dir）
_ARTIFACT_DIR = ".df"


class PipelineRunnerTool:
    """内置多 Agent 编排执行引擎。

    读取编排文件（agents + flow），按 flow 顺序用 `jca -n --task-file` 驱动
    各阶段 agent，poll status_file 等待完成，传递产物，门禁停住。
    """

    name = "pipeline_runner"
    description = (
        "内置多 Agent 编排执行引擎：读取编排 YAML（agents + flow），按 flow "
        "声明的阶段顺序，用 jca -n --task-file 逐个驱动阶段 agent，同步等待每个"
        "阶段完成、校验产物落盘、把上阶段产物路径传入下阶段，实现多 Agent 流水线"
        "的自动顺序协作。门禁阶段（gate: true）完成后停住，默认 approve=false，"
        "需人工审批确认才放行。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "orchestration_file": {
                "type": "string",
                "description": "编排 YAML 文件路径（含 agents 定义与可选 flow 顺序）",
            },
            "spec_file": {
                "type": "string",
                "description": "NLSpec 文件路径（流水线输入，作为各阶段背景信息）",
            },
            "working_dir": {
                "type": "string",
                "description": "工作目录（默认当前目录），产物 .df/ 在其中创建",
            },
            "approve": {
                "type": "boolean",
                "description": "门禁阶段是否已获人工审批（默认 false，需人工确认）",
            },
        },
        "required": ["orchestration_file", "spec_file"],
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """按编排文件 flow 驱动多 Agent 流水线。"""
        args = args or {}
        orchestration_file = str(args.get("orchestration_file") or "").strip()
        spec_file = str(args.get("spec_file") or "").strip()
        working_dir = str(args.get("working_dir") or "").strip() or "."
        approve = bool(args.get("approve", False))

        # 1. 校验参数
        if not orchestration_file:
            return self._error("缺少必填参数 orchestration_file（编排 YAML 路径）")
        if not spec_file:
            return self._error("缺少必填参数 spec_file（NLSpec 文件路径）")

        orch_path = Path(orchestration_file)
        if not orch_path.exists() or not orch_path.is_file():
            return self._error(f"编排文件不存在: {orchestration_file}")

        spec_path = Path(spec_file)
        if not spec_path.exists() or not spec_path.is_file():
            return self._error(f"NLSpec 文件不存在: {spec_file}")

        work_dir = Path(working_dir).resolve()
        if not work_dir.is_dir():
            return self._error(f"工作目录不存在: {working_dir}")

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

        # 3. 初始化产物目录
        artifact_dir = work_dir / _ARTIFACT_DIR
        try:
            artifact_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # pylint: disable=broad-except
            return self._error(f"无法创建产物目录 {artifact_dir}: {e}")

        # jca 可用性校验
        jca_bin = shutil.which("jca")
        if not jca_bin:
            return self._error(
                "未找到 jca 命令。请确认 Jarvis 已安装且 jca 在 PATH 中。"
            )

        # 读取 spec 摘要作为各阶段背景
        spec_summary = self._read_spec_summary(spec_path)

        # 4. 遍历 flow 各阶段
        stdout_lines: List[str] = []
        previous_output: Optional[str] = None
        for idx, stage in enumerate(flow):
            stage_name = str(stage.get("stage") or f"stage_{idx}")
            agent_name = str(stage.get("agent") or "")
            output = str(stage.get("output") or "").strip()
            input_ref = str(stage.get("input") or "").strip()
            is_gate = bool(stage.get("gate", False))

            if agent_name not in agents_by_name:
                return self._error(
                    f"flow 阶段 '{stage_name}' 引用了未定义的 agent '{agent_name}'"
                )

            agent_def = agents_by_name[agent_name]
            task_desc = str(agent_def.get("task") or agent_def.get("task_desc") or "")

            # 组装本阶段 task-file
            stage_input = input_ref or previous_output
            taskfile = artifact_dir / f"{stage_name}.task.json"
            status_file = artifact_dir / f"{stage_name}.status"
            self._write_task_file(
                taskfile=taskfile,
                task_desc=task_desc,
                stage=stage_name,
                stage_input=stage_input,
                output=output,
                spec_summary=spec_summary,
                status_file=status_file,
            )

            PrettyOutput.auto_print(
                f"▶ 阶段 [{stage_name}] agent={agent_name} 启动（jca -n --task-file）"
            )
            # 启动阶段 agent（同步等待子进程退出）
            try:
                subprocess.run(
                    [jca_bin, "-n", "--task-file", str(taskfile)],
                    cwd=str(work_dir),
                    capture_output=True,
                    text=True,
                    timeout=_DEFAULT_STAGE_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                return self._error(
                    f"阶段 [{stage_name}] 超时（>{_DEFAULT_STAGE_TIMEOUT // 60} 分钟），"
                    f"已中止流水线。产物保留在 {artifact_dir} 便于排查。"
                )
            except Exception as e:  # pylint: disable=broad-except
                return self._error(f"阶段 [{stage_name}] 启动失败: {e}")

            # poll status_file 等待阶段完成
            stage_ok = self._wait_status(status_file, stage_name)
            if stage_ok is None:
                return self._error(f"阶段 [{stage_name}] 状态等待超时")

            if not stage_ok:
                err = self._read_error_file(status_file)
                return self._error(
                    f"阶段 [{stage_name}] 失败（agent={agent_name}）"
                    + (f": {err}" if err else "")
                    + f"。产物保留在 {artifact_dir} 便于排查。"
                )

            # 校验产物落盘
            if output:
                output_path = work_dir / output
                if not output_path.exists():
                    return self._error(
                        f"阶段 [{stage_name}] 声明产物 {output} 未落盘，已中止流水线。"
                    )
                stdout_lines.append(
                    f"  ✅ 阶段 [{stage_name}] 完成，产物: {output}"
                )
                previous_output = output
            else:
                stdout_lines.append(f"  ✅ 阶段 [{stage_name}] 完成")

            # 门禁阶段：停住等人工审批
            if is_gate:
                if not approve:
                    approval_path = work_dir / (output or f"{stage_name}.approval.md")
                    stdout_lines.append(
                        f"  ⛔ 门禁阶段 [{stage_name}] 已产出审批报告: {approval_path}"
                    )
                    stdout_lines.append(
                        "  ⛔ 待人工审批：请确认审批报告后，以 approve=true 重跑门禁确认。"
                    )
                    return {
                        "success": True,
                        "stdout": "\n".join(stdout_lines),
                        "stderr": "",
                    }
                stdout_lines.append(
                    f"  ✅ 门禁阶段 [{stage_name}] 已获人工审批，流水线放行"
                )

        stdout_lines.append("🏁 流水线全部阶段完成")
        return {"success": True, "stdout": "\n".join(stdout_lines), "stderr": ""}

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    def _write_task_file(
        self,
        taskfile: Path,
        task_desc: str,
        stage: str,
        stage_input: Optional[str],
        output: str,
        spec_summary: str,
        status_file: Path,
    ) -> None:
        """组装并写入本阶段 task-file（复用 jca 的 task_desc/background/additional_info/status_file 字段）。"""
        task = task_desc.strip()
        if spec_summary:
            task += f"\n\n流水线输入 NLSpec:\n{spec_summary}"
        if stage_input:
            task += f"\n\n本阶段输入产物:\n{stage_input}"
        data = {
            "task_desc": task,
            "background": f"多 Agent 流水线阶段={stage}，输入={stage_input or '无'}，输出={output or '无'}",
            "additional_info": (
                f"请完成本阶段职责后，将产物写入 {output or '（本阶段无产物要求）'}，"
                "完成后正常退出。"
            ),
            "status_file": str(status_file),
        }
        taskfile.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _wait_status(self, status_file: Path, stage: str) -> Optional[bool]:
        """轮询 status_file 直到 completed/failed，返回 True=成功 False=失败 None=超时。"""
        deadline = time.time() + _DEFAULT_STAGE_TIMEOUT
        while time.time() < deadline:
            if status_file.exists():
                try:
                    data = json.loads(status_file.read_text(encoding="utf-8"))
                    status = str(data.get("status") or "")
                    if status == "completed":
                        return True
                    if status == "failed":
                        return False
                except (json.JSONDecodeError, OSError):
                    # 文件可能正在写入，稍后重试
                    pass
            time.sleep(_POLL_INTERVAL)
        return None

    def _read_error_file(self, status_file: Path) -> str:
        """读取 status_file 对应的 .error 文件内容（若存在）。"""
        error_file = status_file.with_suffix(".error")
        try:
            if error_file.exists():
                return error_file.read_text(encoding="utf-8").strip()
        except OSError:
            pass
        return ""

    def _read_spec_summary(self, spec_path: Path) -> str:
        """读取 NLSpec 前若干行作为各阶段背景摘要。"""
        try:
            text = spec_path.read_text(encoding="utf-8")
        except OSError:
            return ""
        lines = text.splitlines()
        if len(lines) <= 60:
            return text
        return "\n".join(lines[:60]) + "\n...（NLSpec 较长，仅展示前 60 行）"

    def _error(self, message: str) -> Dict[str, Any]:
        """构造错误返回。"""
        PrettyOutput.auto_print(f"❌ pipeline_runner: {message}")
        return {"success": False, "stdout": "", "stderr": message}
