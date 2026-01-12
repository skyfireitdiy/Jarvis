# -*- coding: utf-8 -*-
"""load_rule 工具模块

提供读取规则文件并渲染 jinja2 模板的功能。
支持的内置变量：
- current_dir: 当前工作目录
- jarvis_data_dir: Jarvis数据目录
- jarvis_src_dir: Jarvis源码目录
- git_root_dir: Git根目录
- rule_file_dir: 规则文件所在目录
"""

import os
from typing import Any, Dict

from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.template_utils import render_rule_template


class LoadRuleTool:
    """加载规则文件并渲染 jinja2 模板"""

    name = "load_rule"
    description = (
        "读取规则文件内容并使用 jinja2 渲染模板变量。"
        "支持的变量包括：current_dir, git_root_dir, jarvis_src_dir, jarvis_data_dir, rule_file_dir"
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "规则文件路径（支持相对路径和绝对路径）",
            }
        },
        "required": ["file_path"],
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行规则文件加载和渲染

        参数:
            args (Dict): 包含 file_path 参数的字典

        返回:
            Dict[str, Any]: 包含成功状态、渲染内容和错误信息的字典
        """
        try:
            # 获取文件路径
            file_path = args.get("file_path", "").strip()
            if not file_path:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "文件路径不能为空",
                }

            # 展开路径并获取绝对路径
            expanded_path = os.path.expanduser(file_path)
            abs_path = os.path.abspath(expanded_path)

            # 检查文件是否存在
            if not os.path.exists(abs_path):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"文件不存在: {abs_path}",
                }

            # 检查是否为文件
            if not os.path.isfile(abs_path):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"路径不是文件: {abs_path}",
                }

            # 读取文件内容
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            if not content:
                return {
                    "success": True,
                    "stdout": f"文件 {abs_path} 为空",
                    "stderr": "",
                }

            # 获取文件所在目录
            file_dir = os.path.dirname(abs_path)

            # 渲染模板
            rendered_content = render_rule_template(content, file_dir, abs_path)

            # 返回渲染结果
            return {
                "success": True,
                "stdout": rendered_content,
                "stderr": "",
            }

        except Exception as e:
            PrettyOutput.auto_print(f"❌ {str(e)}")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"加载规则文件失败: {str(e)}",
            }
