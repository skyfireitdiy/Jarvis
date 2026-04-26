# -*- coding: utf-8 -*-
"""分析相关模块"""
# type: ignore

from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from jarvis.jarvis_utils.output import PrettyOutput

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_sec.parsers import try_parse_summary_report
from jarvis.jarvis_sec.prompts import build_summary_prompt
from jarvis.jarvis_sec.utils import git_restore_if_dirty


def _build_detailed_error_guidance(
    prev_parsed_items: Optional[List[Dict[str, Any]]],
) -> str:
    """构建详细的格式错误指导信息"""
    if prev_parsed_items is None:
        return "\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- 无法解析出有效的 JSON 数组"

    errors = []
    if not isinstance(prev_parsed_items, list):
        errors.append("结果不是数组")
        error_text = "\n".join(f"- {err}" for err in errors)
        return f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n{error_text}"

    for idx, item in enumerate(prev_parsed_items):
        if not isinstance(item, dict):
            errors.append(f"元素{idx}不是字典")
            break

        # 基础字段检查
        has_gid = "gid" in item
        has_gids = "gids" in item
        if not has_gid and not has_gids:
            errors.append(f"元素{idx}缺少必填字段 gid 或 gids")
            break
        if has_gid and has_gids:
            errors.append(f"元素{idx}不能同时包含 gid 和 gids")
            break

        # 具体字段验证
        if has_gid:
            try:
                gid_val = int(item.get("gid", 0))
                if gid_val < 1:
                    errors.append(f"元素{idx}的 gid 必须 >= 1")
                    break
            except (ValueError, TypeError):
                errors.append(f"元素{idx}的 gid 格式错误（必须是整数）")
                break

        elif has_gids:
            gids_list = item.get("gids", [])
            if not isinstance(gids_list, list) or len(gids_list) == 0:
                errors.append(f"元素{idx}的 gids 必须是非空数组")
                break
            for g_idx, gid_val in enumerate(gids_list):
                try:
                    if int(gid_val) < 1:
                        errors.append(f"元素{idx}的 gids[{g_idx}] 必须 >= 1")
                        break
                except (ValueError, TypeError):
                    errors.append(f"元素{idx}的 gids 格式错误（必须是整数数组）")
                    break

        # has_risk字段验证
        has_risk = item.get("has_risk")
        if has_risk is None or not isinstance(has_risk, bool):
            errors.append(f"元素{idx}缺少必填字段 has_risk（必须是布尔值）")
            break

        if has_risk is True:
            required = ["preconditions", "trigger_path", "consequences", "suggestions"]
            for key in required:
                if key not in item:
                    errors.append(f"元素{idx}的 has_risk 为 true，但缺少必填字段 {key}")
                    break
                val = item[key]
                if not isinstance(val, str) or not val.strip():
                    errors.append(f"元素{idx}的 {key} 字段不能为空")
                    break

    if errors:
        error_text = "\n".join(f"- {err}" for err in errors)
        return f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n{error_text}"

    return "\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- 数据格式不符合要求，请检查必填字段和数据类型"


def valid_items(items: Optional[List[Dict[str, Any]]]) -> bool:
    """验证分析结果项的格式"""
    if not isinstance(items, list):
        return False

    for it in items:
        if not isinstance(it, dict):
            return False
        has_gid = "gid" in it
        has_gids = "gids" in it
        if not has_gid and not has_gids:
            return False
        if has_gid and has_gids:
            return False
        if has_gid:
            try:
                if int(it["gid"]) < 1:
                    return False
            except Exception:
                return False
        elif has_gids:
            if not isinstance(it["gids"], list) or len(it["gids"]) == 0:
                return False
            for gid_val in it["gids"]:
                try:
                    if int(gid_val) < 1:
                        return False
                except Exception:
                    return False
        if "has_risk" not in it or not isinstance(it["has_risk"], bool):
            return False
        if it.get("has_risk"):
            for key in ["preconditions", "trigger_path", "consequences", "suggestions"]:
                if key not in it:
                    return False
                if not isinstance(it[key], str) or not it[key].strip():
                    return False
    return True


def build_analysis_task_context(
    batch: List[Dict[str, Any]], entry_path: str, langs: List[str]
) -> str:
    """构建分析任务上下文"""
    import json as _json2

    batch_ctx: List[Dict[str, Any]] = list(batch)
    cluster_verify = str(batch_ctx[0].get("verify") if batch_ctx else "")
    cluster_gids_ctx = [it.get("gid") for it in batch_ctx]
    return f"""
# 安全子任务批次
上下文参数：
- entry_path: {entry_path}
- languages: {langs}
- cluster_verification: {cluster_verify}

- cluster_gids: {cluster_gids_ctx}
- note: 每个候选含 gid/verify 字段，模型仅需输出 gid 统一给出验证/判断结论（全局编号）；无需使用局部 id

批次候选(JSON数组):
{_json2.dumps(batch_ctx, ensure_ascii=False, indent=2)}
""".strip()


def build_validation_error_guidance(
    parse_error_analysis: Optional[str],
    prev_parsed_items: Optional[List[Dict[str, Any]]],
) -> str:
    """构建验证错误指导信息"""
    if parse_error_analysis:
        return f"""

**格式错误详情（请根据以下错误修复输出格式）：**
- JSON解析失败: {parse_error_analysis}

请确保输出的JSON格式正确，包括正确的引号、逗号、大括号等。仅输出一个 <REPORT> 块，块内直接包含 JSON 数组（不需要额外的标签）。支持jsonnet语法（如尾随逗号、注释等）。"""
    elif prev_parsed_items is None:
        return "\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- 无法从摘要中解析出有效的 JSON 数组"

    # 如果通过验证函数，返回空字符串
    if valid_items(prev_parsed_items):
        return ""

    # 否则构建详细的错误指导
    return _build_detailed_error_guidance(prev_parsed_items)


def run_analysis_agent_with_retry(
    agent: Agent,
    per_task: str,
    summary_container: Dict[str, str],
    entry_path: str,
    task_id: str,
    bidx: int,
    meta_records: List[Dict[str, Any]],
) -> tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    """运行分析Agent并重试直到成功"""
    summary_items: Optional[List[Dict[str, Any]]] = None
    workspace_restore_info: Optional[Dict[str, Any]] = None
    use_direct_model_analysis = False
    prev_parsed_items: Optional[List[Dict[str, Any]]] = None
    parse_error_analysis: Optional[str] = None
    attempt = 0

    while True:
        attempt += 1
        summary_container["text"] = ""

        if use_direct_model_analysis:
            summary_prompt_text = build_summary_prompt()
            error_guidance = build_validation_error_guidance(
                parse_error_analysis, prev_parsed_items
            )
            full_prompt = f"{per_task}{error_guidance}\n\n{summary_prompt_text}"
            try:
                response = agent.model.chat_until_success(full_prompt)
                summary_container["text"] = response
            except Exception as e:
                try:
                    PrettyOutput.auto_print(
                        f"⚠️ [jarvis-sec] 直接模型调用失败: {e}，回退到 run()"
                    )
                except Exception:
                    pass
                agent.run(per_task)
        else:
            agent.run(per_task)

        # 工作区保护
        try:
            _changed = git_restore_if_dirty(entry_path)
            workspace_restore_info = {
                "performed": bool(_changed),
                "changed_files_count": int(_changed or 0),
                "action": "git checkout -- .",
            }
            meta_records.append(
                {
                    "task_id": task_id,
                    "batch_index": bidx,
                    "workspace_restore": workspace_restore_info,
                    "attempt": attempt + 1,
                }
            )
            if _changed:
                try:
                    PrettyOutput.auto_print(
                        f"🔵 [jarvis-sec] 工作区已恢复 ({_changed} 个文件），操作: git checkout -- ."
                    )
                except Exception:
                    pass
        except Exception:
            pass

        # 解析摘要中的 <REPORT>（JSON）
        summary_text = summary_container.get("text", "")
        parsed_items: Optional[List[Dict[str, Any]]] = None
        parse_error_analysis = None
        if summary_text:
            rep, parse_error_analysis = try_parse_summary_report(summary_text)
            if parse_error_analysis:
                try:
                    PrettyOutput.auto_print(
                        f"⚠️ [jarvis-sec] 分析结果JSON解析失败: {parse_error_analysis}"
                    )
                except Exception:
                    pass
            elif isinstance(rep, list):
                parsed_items = rep
            elif isinstance(rep, dict):
                items = rep.get("issues")
                if isinstance(items, list):
                    parsed_items = items

        # 关键字段校验
        # 空数组 [] 是有效的（表示没有发现问题），需要单独处理
        if parsed_items is not None:
            if len(parsed_items) == 0:
                # 空数组表示没有发现问题，这是有效的格式
                summary_items = parsed_items
                break
            elif valid_items(parsed_items):
                # 非空数组需要验证格式
                summary_items = parsed_items
                break

        # 格式校验失败，后续重试使用直接模型调用
        use_direct_model_analysis = True
        prev_parsed_items = parsed_items
        if parse_error_analysis:
            try:
                PrettyOutput.auto_print(
                    f"⚠️ [jarvis-sec] 分析结果JSON解析失败 -> 重试第 {attempt} 次 (批次={bidx}，使用直接模型调用，将反馈解析错误)"
                )
            except Exception:
                pass
        else:
            try:
                PrettyOutput.auto_print(
                    f"⚠️ [jarvis-sec] 分析结果格式无效 -> 重试第 {attempt} 次 (批次={bidx}，使用直接模型调用)"
                )
            except Exception:
                pass

    return summary_items, workspace_restore_info


def expand_and_filter_analysis_results(
    summary_items: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """展开gids格式为单个gid格式，并过滤出有风险的项目"""
    items_with_risk: List[Dict[str, Any]] = []
    items_without_risk: List[Dict[str, Any]] = []
    merged_items: List[Dict[str, Any]] = []

    for it in summary_items:
        has_risk = it.get("has_risk") is True
        if "gids" in it and isinstance(it.get("gids"), list):
            for gid_val in it.get("gids", []):
                try:
                    gid_int = int(gid_val)
                    if gid_int >= 1:
                        item = {
                            **{k: v for k, v in it.items() if k != "gids"},
                            "gid": gid_int,
                        }
                        if has_risk:
                            merged_items.append(item)
                            items_with_risk.append(item)
                        else:
                            items_without_risk.append(item)
                except Exception:
                    pass
        elif "gid" in it:
            if has_risk:
                merged_items.append(it)
                items_with_risk.append(it)
            else:
                items_without_risk.append(it)

    return items_with_risk, items_without_risk
