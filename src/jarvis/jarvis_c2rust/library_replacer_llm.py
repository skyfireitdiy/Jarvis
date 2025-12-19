# -*- coding: utf-8 -*-
"""库替换器的 LLM 模型创建和评估模块。"""

from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from jarvis.jarvis_utils.output import PrettyOutput

from jarvis.jarvis_c2rust.constants import MAX_LLM_RETRIES
from jarvis.jarvis_c2rust.library_replacer_prompts import build_subtree_prompt


def check_llm_availability() -> tuple[bool, Any, Any, Any, Any]:
    """检查LLM可用性，返回(是否可用, PlatformRegistry, get_smart_platform_name, get_smart_model_name, get_llm_config)
    使用smart平台，适用于代码生成等复杂场景
    """
    try:
        from jarvis.jarvis_platform.registry import PlatformRegistry
        from jarvis.jarvis_utils.config import get_llm_config
        from jarvis.jarvis_utils.config import get_smart_model_name
        from jarvis.jarvis_utils.config import get_smart_platform_name

        return (
            True,
            PlatformRegistry,
            get_smart_platform_name,
            get_smart_model_name,
            get_llm_config,
        )
    except Exception:
        return False, None, None, None, None


def create_llm_model(
    llm_group: Optional[str],
    disabled_display: str,
    model_available: bool,
    PlatformRegistry: Any,
    get_smart_platform_name: Any,
    get_smart_model_name: Any,
    get_llm_config: Any,
) -> Optional[Any]:
    """创建LLM模型，使用smart平台，适用于代码生成等复杂场景"""
    if not model_available:
        return None
    try:
        registry = PlatformRegistry.get_global_platform_registry()
        # 直接使用 get_smart_platform，避免先调用 create_platform 再回退导致的重复错误信息
        # get_smart_platform 内部会处理配置获取和平台创建
        model = registry.get_smart_platform(llm_group if llm_group else None)
        try:
            model.set_model_group(llm_group)
        except Exception:
            pass
        if llm_group:
            try:
                mn = get_smart_model_name(llm_group)
                if mn:
                    model.set_model_name(mn)
            except Exception:
                pass
        model.set_system_prompt(
            "你是资深 C→Rust 迁移专家。任务：给定一个函数及其调用子树（依赖图摘要、函数签名、源码片段），"
            "判断是否可以使用一个或多个成熟的 Rust 库整体替代该子树的功能（允许库内多个 API 协同，允许多个库组合；不允许使用不成熟/不常见库）。"
            "如可替代，请给出 libraries 列表（库名），可选给出代表性 API/模块与实现备注 notes（如何用这些库协作实现）。"
            "输出格式：仅输出一个 <SUMMARY> 块，块内直接包含 JSON 对象（不需要额外的标签），字段: replaceable(bool), libraries(list[str]), confidence(float 0..1)，可选 library(str,首选主库), api(str) 或 apis(list)，notes(str)。"
        )
        return model
    except Exception as e:
        PrettyOutput.auto_print(
            f"⚠️ [c2rust-library] 初始化 LLM 平台失败，将回退为保守策略: {e}"
        )
        return None


def parse_agent_json_summary(
    text: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    解析Agent返回的JSON摘要
    返回(解析结果, 错误信息)
    如果解析成功，返回(data, None)
    如果解析失败，返回(None, 错误信息)
    """
    if not isinstance(text, str) or not text.strip():
        return None, "摘要文本为空"
    import re as _re

    from jarvis.jarvis_utils.jsonnet_compat import loads as _json_loads

    # 提取 <SUMMARY> 块
    m_sum = _re.search(r"<SUMMARY>([\s\S]*?)</SUMMARY>", text, flags=_re.IGNORECASE)
    block = (m_sum.group(1) if m_sum else text).strip()

    if not block:
        return None, "未找到 <SUMMARY> 或 </SUMMARY> 标签，或标签内容为空"

    # 直接解析 <SUMMARY> 块内的内容为 JSON
    # jsonnet_compat.loads 会自动处理 markdown 代码块标记（如 ```json5、```json、``` 等）
    try:
        data = _json_loads(block)
        if isinstance(data, dict):
            return data, None
        return None, f"JSON 解析结果不是字典，而是 {type(data).__name__}"
    except Exception as json_err:
        return None, f"JSON 解析失败: {str(json_err)}"


def llm_evaluate_subtree(
    fid: int,
    desc: set,
    by_id: Dict[int, Dict[str, Any]],
    adj_func: Dict[int, List[int]],
    disabled_norm: List[str],
    disabled_display: str,
    model_available: bool,
    new_model_func: Callable[[], Optional[Any]],
    additional_notes: str = "",
) -> Dict[str, Any]:
    """使用LLM评估子树是否可替代，支持最多3次重试"""
    if not model_available:
        return {"replaceable": False}
    model = new_model_func()
    if not model:
        return {"replaceable": False}

    base_prompt = build_subtree_prompt(
        fid, desc, by_id, adj_func, disabled_display, additional_notes
    )
    last_parse_error = None

    for attempt in range(1, MAX_LLM_RETRIES + 1):
        try:
            # 构建当前尝试的提示词
            if attempt == 1:
                prompt = base_prompt
            else:
                # 重试时包含之前的错误信息
                error_hint = ""
                if last_parse_error:
                    error_hint = (
                        f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- {last_parse_error}\n\n"
                        + "请确保输出的JSON格式正确，包括正确的引号、逗号、大括号等。仅输出一个 <SUMMARY> 块，块内直接包含 JSON 对象（不需要额外的标签）。"
                    )
                prompt = base_prompt + error_hint

            # 调用LLM
            result = model.chat_until_success(prompt)
            parsed, parse_error = parse_agent_json_summary(result or "")

            if parse_error:
                # JSON解析失败，记录错误并准备重试
                last_parse_error = parse_error
                PrettyOutput.auto_print(
                    f"⚠️ [c2rust-library] 第 {attempt}/{MAX_LLM_RETRIES} 次尝试：JSON解析失败: {parse_error}"
                )
                # 打印原始内容以便调试
                result_text = str(result or "").strip()
                if result_text:
                    PrettyOutput.auto_print(
                        f"📄 [c2rust-library] 原始LLM响应内容（前1000字符）:\n{result_text[:1000]}"
                    )
                    if len(result_text) > 1000:
                        PrettyOutput.auto_print(
                            f"📄 [c2rust-library] ... (还有 {len(result_text) - 1000} 个字符未显示)"
                        )
                if attempt < MAX_LLM_RETRIES:
                    continue  # 继续重试
                else:
                    # 最后一次尝试也失败，使用默认值
                    PrettyOutput.auto_print(
                        f"⚠️ [c2rust-library] 重试 {MAX_LLM_RETRIES} 次后JSON解析仍然失败: {parse_error}，使用默认值"
                    )
                    return {"replaceable": False}

            # 解析成功，检查是否为字典
            if not isinstance(parsed, dict):
                last_parse_error = f"解析结果不是字典，而是 {type(parsed).__name__}"
                PrettyOutput.auto_print(
                    f"⚠️ [c2rust-library] 第 {attempt}/{MAX_LLM_RETRIES} 次尝试：{last_parse_error}"
                )
                # 打印解析结果和原始内容以便调试
                PrettyOutput.auto_print(
                    f"📊 [c2rust-library] 解析结果类型: {type(parsed).__name__}, 值: {repr(parsed)[:500]}"
                )
                result_text = str(result or "").strip()
                if result_text:
                    PrettyOutput.auto_print(
                        f"📄 [c2rust-library] 原始LLM响应内容（前1000字符）:\n{result_text[:1000]}"
                    )
                if attempt < MAX_LLM_RETRIES:
                    continue  # 继续重试
                else:
                    PrettyOutput.auto_print(
                        f"🔴 [c2rust-library] 重试 {MAX_LLM_RETRIES} 次后结果格式仍然不正确，视为不可替代。"
                    )
                    return {"replaceable": False}

            # 成功解析为字典，处理结果
            rep = bool(parsed.get("replaceable") is True)
            lib = str(parsed.get("library") or "").strip()
            api = str(parsed.get("api") or parsed.get("function") or "").strip()
            apis = parsed.get("apis")
            libs_raw = parsed.get("libraries")
            notes = str(parsed.get("notes") or "").strip()
            # 归一化 libraries
            libraries: List[str] = []
            if isinstance(libs_raw, list):
                libraries = [str(x).strip() for x in libs_raw if str(x).strip()]
            elif isinstance(libs_raw, str):
                libraries = [s.strip() for s in libs_raw.split(",") if s.strip()]
            conf = parsed.get("confidence")
            try:
                conf = float(conf) if conf is not None else 0.0
            except Exception:
                conf = 0.0
            # 不强制要求具体 API 或特定库名；若缺省且存在 library 字段，则纳入 libraries
            if not libraries and lib:
                libraries = [lib]

            # 禁用库命中时，强制视为不可替代
            if disabled_norm:
                libs_lower = [lib_name.lower() for lib_name in libraries]
                lib_single_lower = lib.lower() if lib else ""
                banned_hit = any(
                    lower_lib in disabled_norm for lower_lib in libs_lower
                ) or (lib_single_lower and lib_single_lower in disabled_norm)
                if banned_hit:
                    rep = False
                    warn_libs = (
                        ", ".join(sorted(set([lib] + libraries)))
                        if (libraries or lib)
                        else "(未提供库名)"
                    )
                    root_rec = by_id.get(fid, {})
                    root_name = (
                        root_rec.get("qualified_name")
                        or root_rec.get("name")
                        or f"sym_{fid}"
                    )
                    PrettyOutput.auto_print(
                        f"🚫 [c2rust-library] 评估结果包含禁用库，强制判定为不可替代: {root_name} | 命中库: {warn_libs}"
                    )
                    if notes:
                        notes = notes + f" | 禁用库命中: {warn_libs}"
                    else:
                        notes = f"禁用库命中: {warn_libs}"

            result_obj: Dict[str, Any] = {
                "replaceable": rep,
                "library": lib,
                "libraries": libraries,
                "api": api,
                "confidence": conf,
            }
            if isinstance(apis, list):
                result_obj["apis"] = apis
            if notes:
                result_obj["notes"] = notes

            # 成功获取结果，返回
            if attempt > 1:
                PrettyOutput.auto_print(
                    f"✅ [c2rust-library] 第 {attempt} 次尝试成功获取评估结果"
                )
            return result_obj

        except Exception as e:
            # LLM调用异常，记录并准备重试
            last_parse_error = f"LLM调用异常: {str(e)}"
            PrettyOutput.auto_print(
                f"⚠️ [c2rust-library] 第 {attempt}/{MAX_LLM_RETRIES} 次尝试：LLM评估失败: {e}"
            )
            if attempt < MAX_LLM_RETRIES:
                continue  # 继续重试
            else:
                # 最后一次尝试也失败，返回默认值
                PrettyOutput.auto_print(
                    f"🔴 [c2rust-library] 重试 {MAX_LLM_RETRIES} 次后LLM评估仍然失败: {e}，视为不可替代"
                )
                return {"replaceable": False}

    # 理论上不会到达这里，但作为保险
    return {"replaceable": False}
