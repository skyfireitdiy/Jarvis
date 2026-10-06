# -*- coding: utf-8 -*-
"""Jarvis 评测适配层（Terminal-Bench / Harbor 接入）。

将 Jarvis 封装为 Harbor 的 ``BaseInstalledAgent``，使其可作为
Terminal-Bench 2.0 的评测 Agent 运行。

Harbor 为惰性依赖：本包（``jarvis_eval``）可被 Jarvis 主项目安全 import，
不会触发 harbor 依赖；仅当 Harbor 实际加载 ``jarvis_eval.harbor_agent``
模块时才需要已安装 ``harbor``。

用法（在具备 Docker 的评测机器上）：:

    harbor run --dataset terminal-bench@2.0 \\
        -a jarvis_eval.harbor_agent:JarvisInstalledAgent \\
        --ae OPENAI_API_KEY=<your-key>
"""
