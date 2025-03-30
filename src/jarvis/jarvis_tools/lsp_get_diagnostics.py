import os
from typing import Dict, Any
from jarvis.jarvis_lsp.registry import LSPRegistry
class LSPGetDiagnosticsTool:
    """Tool for getting diagnostics (errors, warnings) from code using LSP."""

    # 工具名称
    name = "lsp_get_diagnostics"
    # 工具描述
    description = "Get diagnostic information (errors, warnings) from code files"
    # 工具标签
    labels = ['code', 'analysis', 'lsp']
    # 工具参数定义
    parameters = {
        "file_path": "Path to the file to analyze",
        "language": f"Programming language of the file ({', '.join(LSPRegistry.get_global_lsp_registry().get_supported_languages())})",
        "root_dir": {
            "type": "string",
            "description": "Root directory for LSP operations (optional)",
            "default": "."
        }
    }

    @staticmethod
    def check() -> bool:
        """检查是否有可用的LSP服务器"""
        registry = LSPRegistry.get_global_lsp_registry()
        return len(registry.get_supported_languages()) > 0

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具的主要逻辑"""
        file_path = args.get("file_path", "")
        language = args.get("language", "")
        root_dir = args.get("root_dir", ".")

        # 验证输入参数
        if not all([file_path, language]):
            return {
                "success": False,
                "stderr": "Both file_path and language must be provided",
                "stdout": ""
            }

        # 检查文件是否存在
        if not os.path.exists(file_path):
            return {
                "success": False,
                "stderr": f"File not found: {file_path}",
                "stdout": ""
            }

        # 存储当前目录
        original_dir = os.getcwd()

        try:
            # 切换到root_dir
            os.chdir(root_dir)

            # 获取LSP实例
            registry = LSPRegistry.get_global_lsp_registry()
            lsp = registry.create_lsp(language)

            # 检查语言是否支持
            if not lsp:
                return {
                    "success": False,
                    "stderr": f"No LSP support for language: {language}",
                    "stdout": ""
                }

            try:
                # 初始化LSP
                if not lsp.initialize(os.path.abspath(os.getcwd())):
                    return {
                        "success": False,
                        "stderr": "LSP initialization failed",
                        "stdout": ""
                    }

                # 获取诊断信息
                diagnostics = lsp.get_diagnostics(file_path)

                # 如果没有诊断信息
                if not diagnostics:
                    return {
                        "success": True,
                        "stdout": "No issues found in the file",
                        "stderr": ""
                    }

                # 格式化输出
                output = ["Diagnostics:"]
                # 严重程度映射
                severity_map = {1: "Error", 2: "Warning", 3: "Info", 4: "Hint"}

                # 按严重程度和行号排序诊断信息
                sorted_diagnostics = sorted(
                    diagnostics,
                    key=lambda x: (x["severity"], x["range"]["start"]["line"])
                )

                # 处理每个诊断信息
                for diag in sorted_diagnostics:
                    severity = severity_map.get(diag["severity"], "Unknown")
                    start = diag["range"]["start"]
                    line = LSPRegistry.get_line_at_position(file_path, start["line"]).strip()

                    output.extend([
                        f"\n{severity} at line {start['line'] + 1}, column {start['character'] + 1}:",
                        f"Message: {diag['message']}",
                        f"Code: {line}",
                        "-" * 60
                    ])

                    # 处理相关附加信息
                    if diag.get("relatedInformation"):
                        output.append("Related information:")
                        for info in diag["relatedInformation"]:
                            info_line = LSPRegistry.get_line_at_position(
                                info["location"]["uri"],
                                info["location"]["range"]["start"]["line"]
                            ).strip()
                            output.extend([
                                f"  - {info['message']}",
                                f"    at {info['location']['uri']}:{info['location']['range']['start']['line'] + 1}",
                                f"    {info_line}"
                            ])

                return {
                    "success": True,
                    "stdout": "\n".join(output),
                    "stderr": ""
                }

            except Exception as e:
                return {
                    "success": False,
                    "stderr": f"Error getting diagnostics: {str(e)}",
                    "stdout": ""
                }
            finally:
                # 确保关闭LSP连接
                if lsp:
                    lsp.shutdown()
        finally:
            # 恢复原始目录
            os.chdir(original_dir)
