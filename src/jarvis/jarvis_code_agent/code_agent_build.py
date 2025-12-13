"""CodeAgent 构建验证模块"""

from typing import Any
from typing import List

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
from typing import Optional
from typing import Tuple

from jarvis.jarvis_code_agent.build_validation_config import BuildValidationConfig
from jarvis.jarvis_code_agent.code_analyzer.build_validator import BuildResult
from jarvis.jarvis_code_agent.code_analyzer.build_validator import BuildValidator
from jarvis.jarvis_code_agent.code_analyzer.build_validator import (
    FallbackBuildValidator,
)
from jarvis.jarvis_utils.config import get_build_validation_timeout
from jarvis.jarvis_utils.config import is_enable_build_validation
from jarvis.jarvis_utils.input import user_confirm


def format_build_error(result: BuildResult, max_len: int = 2000) -> str:
    """格式化构建错误信息，限制输出长度"""
    error_msg = result.error_message or ""
    output = result.output or ""

    full_error = f"{error_msg}\n{output}".strip()

    if len(full_error) > max_len:
        return full_error[:max_len] + "\n... (输出已截断)"
    return full_error


class BuildValidationManager:
    """构建验证管理器"""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def validate_build_after_edit(
        self, modified_files: List[str]
    ) -> Optional[BuildResult]:
        """编辑后验证构建

        Args:
            modified_files: 修改的文件列表

        Returns:
            BuildResult: 验证结果，如果验证被禁用或出错则返回None
        """
        if not is_enable_build_validation():
            return None

        # 检查项目配置，看是否已禁用构建验证
        config = BuildValidationConfig(self.root_dir)
        if config.is_build_validation_disabled():
            # 已禁用，返回None，由调用方处理基础静态检查
            return None

        # 输出编译检查日志
        import os

        file_count = len(modified_files)
        files_str = ", ".join(os.path.basename(f) for f in modified_files[:3])
        if file_count > 3:
            files_str += f" 等{file_count}个文件"
        PrettyOutput.auto_print(f"🔨 正在进行编译检查 ({files_str})...")

        try:
            timeout = get_build_validation_timeout()
            validator = BuildValidator(self.root_dir, timeout=timeout)
            result = validator.validate(modified_files)
            return result
        except Exception as e:
            # 构建验证失败不应该影响主流程，仅记录日志
            PrettyOutput.auto_print(f"⚠️ 构建验证执行失败: {e}")
            return None

    def handle_build_validation_disabled(
        self, modified_files: List[str], config: Any, agent: Any, final_ret: str
    ) -> str:
        """处理构建验证已禁用的情况

        Returns:
            更新后的结果字符串
        """
        reason = config.get_disable_reason()
        reason_text = f"（原因: {reason}）" if reason else ""
        final_ret += f"\n\nℹ️ 构建验证已禁用{reason_text}，仅进行基础静态检查\n"

        # 输出基础静态检查日志
        import os

        file_count = len(modified_files)
        files_str = ", ".join(os.path.basename(f) for f in modified_files[:3])
        if file_count > 3:
            files_str += f" 等{file_count}个文件"

        # 使用兜底验证器进行基础静态检查
        fallback_validator = FallbackBuildValidator(
            self.root_dir, timeout=get_build_validation_timeout()
        )
        static_check_result = fallback_validator.validate(modified_files)
        if not static_check_result.success:
            final_ret += f"\n⚠️ 基础静态检查失败:\n{static_check_result.error_message or static_check_result.output}\n"
            agent.set_addon_prompt(
                f"基础静态检查失败，请根据以下错误信息修复代码:\n{static_check_result.error_message or static_check_result.output}\n"
            )
        else:
            final_ret += (
                f"\n✅ 基础静态检查通过（耗时 {static_check_result.duration:.2f}秒）\n"
            )

        return final_ret

    def handle_build_validation_failure(
        self,
        build_validation_result: Any,
        config: Any,
        modified_files: List[str],
        agent: Any,
        final_ret: str,
    ) -> str:
        """处理构建验证失败的情况

        Returns:
            更新后的结果字符串
        """
        if not config.has_been_asked():
            # 首次失败，询问用户
            error_preview = format_build_error(build_validation_result)
            PrettyOutput.auto_print(f"\n⚠️ 构建验证失败:\n{error_preview}\n")
            PrettyOutput.auto_print(
                "ℹ️ 提示：如果此项目需要在特殊环境（如容器）中构建，或使用独立构建脚本，"
                "可以选择禁用构建验证，后续将仅进行基础静态检查。"
            )

            if user_confirm(
                "是否要禁用构建验证，后续仅进行基础静态检查？",
                default=True,
            ):
                # 用户选择禁用
                config.disable_build_validation(
                    reason="用户选择禁用（项目可能需要在特殊环境中构建）"
                )
                config.mark_as_asked()
                final_ret += "\n\nℹ️ 已禁用构建验证，后续将仅进行基础静态检查\n"

                # 输出基础静态检查日志
                import os

                file_count = len(modified_files)
                files_str = ", ".join(os.path.basename(f) for f in modified_files[:3])
                if file_count > 3:
                    files_str += f" 等{file_count}个文件"

                # 立即进行基础静态检查
                fallback_validator = FallbackBuildValidator(
                    self.root_dir, timeout=get_build_validation_timeout()
                )
                static_check_result = fallback_validator.validate(modified_files)
                if not static_check_result.success:
                    final_ret += f"\n⚠️ 基础静态检查失败:\n{static_check_result.error_message or static_check_result.output}\n"
                    agent.set_addon_prompt(
                        f"基础静态检查失败，请根据以下错误信息修复代码:\n{static_check_result.error_message or static_check_result.output}\n"
                    )
                else:
                    final_ret += f"\n✅ 基础静态检查通过（耗时 {static_check_result.duration:.2f}秒）\n"
            else:
                # 用户选择继续验证，标记为已询问
                config.mark_as_asked()
                final_ret += f"\n\n⚠️ 构建验证失败:\n{format_build_error(build_validation_result)}\n"
                # 如果构建失败，添加修复提示
                agent.set_addon_prompt(
                    f"构建验证失败，请根据以下错误信息修复代码:\n{format_build_error(build_validation_result)}\n"
                    "请仔细检查错误信息，修复编译/构建错误后重新提交。"
                )
        else:
            # 已经询问过，直接显示错误
            final_ret += (
                f"\n\n⚠️ 构建验证失败:\n{format_build_error(build_validation_result)}\n"
            )
            # 如果构建失败，添加修复提示
            agent.set_addon_prompt(
                f"构建验证失败，请根据以下错误信息修复代码:\n{format_build_error(build_validation_result)}\n"
                "请仔细检查错误信息，修复编译/构建错误后重新提交。"
            )

        return final_ret

    def handle_build_validation(
        self, modified_files: List[str], agent: Any, final_ret: str
    ) -> Tuple[Optional[Any], str]:
        """处理构建验证

        Returns:
            (build_validation_result, updated_final_ret)
        """
        if not is_enable_build_validation():
            return None, final_ret

        config = BuildValidationConfig(self.root_dir)

        # 检查是否已禁用构建验证
        if config.is_build_validation_disabled():
            final_ret = self.handle_build_validation_disabled(
                modified_files, config, agent, final_ret
            )
            return None, final_ret

        # 未禁用，进行构建验证
        build_validation_result = self.validate_build_after_edit(modified_files)
        if build_validation_result:
            if not build_validation_result.success:
                final_ret = self.handle_build_validation_failure(
                    build_validation_result, config, modified_files, agent, final_ret
                )
            else:
                build_system_info = (
                    f" ({build_validation_result.build_system.value})"
                    if build_validation_result.build_system
                    else ""
                )
                final_ret += f"\n\n✅ 构建验证通过{build_system_info}（耗时 {build_validation_result.duration:.2f}秒）\n"

        return build_validation_result, final_ret
