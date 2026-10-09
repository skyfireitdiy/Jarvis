# -*- coding: utf-8 -*-
"""编排文件统一加载器（第 1 层：结构生成）。

按文件后缀分发，把 YAML 与 Python DSL 两种编排来源统一解析为**同构结构**：

    {"agents": [...], "flow": [...], "spec": str(可选), "default_on_error": str(可选)}

两种后缀对应两种编排意图：

- `.yaml` / `.yml`：**组织的编排**——声明一组 Agent（agents），用于批量创建。
- `.flow`：**流程的编排**——用 Python DSL（orchestration_dsl）声明 DAG 结构
  （agents + flow），脚本内容为 Python 代码，取顶层变量 `pipeline`（Pipeline 实例）
  导出其结构。脚本约定**只声明结构、不产生副作用**（受信环境）。

设计取向（详见 docs/design/orchestration-python-dsl.md）：
- **唯一解析入口**：pipeline_runner / app.py / node_manager.py 三处解析统一走本模块，
  避免多份重复实现漂移。
- **与 YAML 同构**：返回值可直接交给 pipeline_runner 的 `_build_dag` 消费，
  因此执行引擎、调度、事件、前端可视化、跨节点分发全部不变。
"""

from pathlib import Path
from typing import Any
from typing import Dict
from typing import Union

import yaml

# 支持的编排文件后缀
_YAML_SUFFIXES = (".yaml", ".yml")
_FLOW_SUFFIXES = (".flow",)

# 流程编排脚本约定的顶层变量名（Pipeline 实例）
_PIPELINE_VAR = "pipeline"


def load_orchestration(path: Union[str, Path]) -> Dict[str, Any]:
    """按后缀加载编排文件，返回与 YAML 解析结果同构的字典。

    参数:
        path: 编排文件路径（str 或 Path）。

    返回:
        {"agents": list, "flow": list, "spec": str(可选), "default_on_error": str(可选)}

    异常:
        ValueError: 文件不存在、后缀不支持、YAML 解析失败、Python 脚本执行失败、
            脚本缺少 `pipeline` 变量或类型不符。调用方据此统一转成错误返回。
    """
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        raise ValueError(f"编排文件不存在: {path}")

    suffix = file_path.suffix.lower()
    if suffix in _YAML_SUFFIXES:
        return _load_yaml(file_path)
    if suffix in _FLOW_SUFFIXES:
        return _load_flow(file_path)
    raise ValueError(
        f"不支持的编排文件类型 '{suffix}'（仅支持 .yaml/.yml/.flow）: {path}"
    )


def _load_yaml(file_path: Path) -> Dict[str, Any]:
    """加载 YAML 编排文件（与既有行为一致）。"""
    try:
        content = file_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"编排 YAML 解析失败: {e}") from e
    except OSError as e:
        raise ValueError(f"读取编排文件失败: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("编排文件内容须为映射（mapping）")
    return data


def _load_flow(file_path: Path) -> Dict[str, Any]:
    """执行流程编排脚本（.flow），取顶层 `pipeline` 变量导出结构。

    受信环境下直接执行脚本（脚本约定只声明结构、无副作用）。
    在独立命名空间执行，异常统一转成清晰的 ValueError。
    """
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError as e:
        raise ValueError(f"读取编排脚本失败: {e}") from e

    namespace: Dict[str, Any] = {
        "__file__": str(file_path),
        "__name__": "__orchestration__",
    }
    try:
        code = compile(source, str(file_path), "exec")
        exec(code, namespace)  # pylint: disable=exec-used
    except Exception as e:  # pylint: disable=broad-except
        raise ValueError(f"编排脚本执行失败: {type(e).__name__}: {e}") from e

    pipeline = namespace.get(_PIPELINE_VAR)
    if pipeline is None:
        raise ValueError(
            f"编排脚本缺少顶层变量 '{_PIPELINE_VAR}'（须为 Pipeline 实例）"
        )
    # 优先用 to_dict()（Pipeline 的导出契约）；否则回退读取属性。
    to_dict = getattr(pipeline, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
    else:
        data = {
            "agents": getattr(pipeline, "agents", None),
            "flow": getattr(pipeline, "flow", None),
            "spec": getattr(pipeline, "spec_text", ""),
            "default_on_error": getattr(pipeline, "default_on_error_value", ""),
        }
    if not isinstance(data, dict):
        raise ValueError(
            f"编排脚本的 '{_PIPELINE_VAR}' 导出结果须为字典，实际为 {type(data).__name__}"
        )
    return data
