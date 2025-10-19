OpenHarmony 安全演进套件（jarvis_sec）
================================

概览
- 模式：单 Agent 逐条子任务分析（先直扫拆分候选，再由 Agent 精核）
- 目标：在不破坏现有功能的前提下，增强稳定性与可追溯性，减少“全部解析失败”的概率
- 关键特性：
  - 禁用方法论与分析（use_methodology=False, use_analysis=False），降低不确定性
  - 按次指定模型组（--llm-group / llm_group 参数），不修改全局配置
  - 启用摘要 need_summary=True，通过 <REPORT>…</REPORT> 输出结构化结果
  - 进度与过程日志输出（Progress / parse-fail / no-issue / issues-found）
  - 增量写入 JSONL 报告，长任务中可实时查看
  - 只读约束：禁止任何写文件或破坏性命令（rm/mv/cp/echo >/sed -i/git/patch/chmod/chown 等）

CLI 使用
- 入口：python -m jarvis.jarvis_sec.cli agent --path ./target_project
- 可选参数：
  - --languages/-l：逗号分隔的扩展名列表，例如 "c,cpp,h,hpp,rs"
  - --llm-group/-g：本次运行使用的模型组（仅透传，不改全局）
  - --report-file/-r：JSONL 报告输出路径（默认写入 path/.jarvis/sec/agent_issues.jsonl）

示例
- 最简运行：
  python -m jarvis.jarvis_sec.cli agent -p ./path/to/project

- 指定语言与临时模型组：
  python -m jarvis.jarvis_sec.cli agent -p ./proj -l c,cpp,h,hpp,rs -g my_llm_group

- 指定增量报告文件：
  python -m jarvis.jarvis_sec.cli agent -p ./proj -r ./out/agent_issues.jsonl

工作流要点
1) 直扫（direct_scan）
- 使用正则/命令行辅助在本地生成候选问题（issues）与统计信息（summary）
- 可在无外部服务时复现与回退，保障可用性

2) 子任务拆分与单 Agent 精核
- 将每个候选压缩为精简上下文（language、category、pattern、file、line、evidence 等）
- 单 Agent 周期内：
  - need_summary=True
  - summary_prompt 为 _build_summary_prompt(...) 返回的提示，要求在 <REPORT>…</REPORT> 内输出 JSON 或 YAML
  - 系统提示包含只读约束与“一次仅执行一个工具”规则
  - 推荐工具：read_code（读取目标文件附近源码）、execute_script（只读检索，如 rg/find）

3) 解析策略
- 优先解析摘要（agent.generate_summary()）中的 <REPORT>…</REPORT>：
  - _try_parse_summary_report 支持 JSON 优先，失败回退 YAML（safe_load）
- 摘要不可解析时，直接判定 parse-fail（不会回退解析主输出）

4) 增量写入 JSONL
- 每个子任务如检测到 issues，立即将记录 append 到 JSONL（默认 path/.jarvis/sec/agent_issues.jsonl）
- 支持通过 --report-file/-r 指定其他路径
- 失败不会影响主流程

JSONL 记录结构
- 每行一个 JSON 对象，格式如下：
  {
    "task_id": "JARVIS-SEC-Analyzer-3",
    "candidate": {
      "language": "c/cpp",
      "category": "unsafe_api",
      "pattern": "strcpy",
      "file": "src/foo.c",
      "line": 120,
      "evidence": "strcpy(dst, src);",
      "confidence": 0.9,
      "severity": "high"
    },
    "issues": [
      {
        "language": "c/cpp",
        "category": "unsafe_api",
        "pattern": "strcpy",
        "file": "src/foo.c",
        "line": 120,
        "evidence": "strcpy(dst, src);",
        "description": "使用不安全/高风险字符串API，可能导致缓冲区溢出或格式化风险。",
        "suggestion": "替换为带边界的安全API（如 snprintf/strlcpy 等）或加入显式长度检查。",
        "confidence": 0.9,
        "severity": "high"
      }
    ],
    "meta": {
      "entry_path": "/abs/path/to/project",
      "languages": ["c","cpp","h","hpp","rs"],
      "source": "summary"
      "timestamp": "2025-10-19T03:00:00Z"
    }
  }

摘要 <REPORT> 结构
- Agent 在摘要中必须只输出以下内容（推荐 JSON，支持 YAML）：
  <REPORT>
  {
    "issues": [
      {
        "language": "c/cpp|rust",
        "category": "unsafe_api|buffer_overflow|memory_mgmt|error_handling|unsafe_usage|concurrency|ffi",
        "pattern": "命中的模式/关键字",
        "file": "相对或绝对路径",
        "line": 0,
        "evidence": "证据代码片段（单行简化）",
        "description": "问题说明",
        "suggestion": "修复建议",
        "confidence": 0.0,
        "severity": "high|medium|low"
      }
    ],
    "meta": {
      "task_id": "JARVIS-SEC-Analyzer-1",
      "entry_path": "/abs/path",
      "languages": ["c","cpp","h","hpp","rs"],
      "candidate": { "...": "子任务精简信息" }
    }
  }
  </REPORT>

- 要求：
  - 仅在 <REPORT> 与 </REPORT> 中输出报告，不得出现其他文本
  - 若确认误报，返回空数组 issues: []
  - 字段值需与实际分析一致

只读约束（强制）
- Agent 被要求仅做只读分析：禁止修改任何文件或执行写操作命令
- 禁止命令包含但不限于：rm/mv/cp/echo >、sed -i、git、patch、chmod、chown 等
- 推荐工具：
  - read_code：按文件路径与行号范围读取源码（建议围绕候选行上下 50 行）
  - execute_script：只读检索（如 rg/find/grep），避免任何写操作

日志与可观测性
- 进度日志：
  - [JARVIS-SEC] Progress i/N: file:line (lang)
  - [JARVIS-SEC] no-issue i/N: ...
  - [JARVIS-SEC] issues-found i/N: count=k -> append report (summary)
  - [JARVIS-SEC] parse-fail i/N: ...
- JSONL 写入：
  - [JARVIS-SEC] write K issue(s) to <path>

模型组（llm_group）
- 通过 CLI 的 --llm-group 或 API 的 llm_group 参数传入，仅对本次调用链生效
- 不会覆盖全局配置（不调用 set_config）

常见问题排查
- 解析失败（parse-fail）：
  - 确认模型已在摘要中输出 <REPORT>…</REPORT>
  - 优先使用 JSON；YAML 解析依赖 PyYAML（safe_load），若环境无此库将忽略 YAML 回退
  - 注意：不会回退解析主输出；若摘要缺失或格式不合规，将直接跳过该候选
- JSONL 未写入：
  - 仅当 issues 非空时追加写入
  - 确认 --report-file 或默认目录 path/.jarvis/sec/ 可写
- Agent 输出为空：
  - CLI 会回退到直扫基线（run_security_analysis_fast），仍可得到 JSON+Markdown 报告

API 概览
- run_with_multi_agent(entry_path, languages=None, llm_group=None, report_file=None) -> str
  - 透传到 run_security_analysis(...)，实现“直扫 + 单 Agent 逐条验证 + 聚合”
- run_security_analysis_fast(entry_path, languages=None, exclude_dirs=None) -> str
  - 纯直扫基线，返回 JSON + Markdown
- direct_scan(entry_path, languages=None, exclude_dirs=None) -> Dict
  - 返回结构化 issues 与 summary
- run_with_multi_agent(entry_path, languages=None, llm_group=None, report_file=None) -> str
  - 透传到 run_security_analysis(...)，实现“直扫 + 单 Agent 逐条验证 + 聚合”
- run_security_analysis_fast(entry_path, languages=None, exclude_dirs=None) -> str
  - 纯直扫基线，返回 JSON + Markdown
- direct_scan(entry_path, languages=None, exclude_dirs=None) -> Dict
  - 返回结构化 issues 与 summary

建议测试（可选）
- 摘要解析：
  - _try_parse_summary_report 对 JSON/YAML/无 REPORT 的输入解析正确
- CLI 参数链路：
  - --llm-group 仅透传，不改全局
  - --report-file 写入指定路径
- 只读约束：
  - 模拟 Agent 工具调用，确保拒绝写操作命令（可在提示词层面校验）

版本兼容与注意事项
- 本模块不修改全局模型组配置
- 摘要使用 JSON 优先，YAML 为回退路径（需 PyYAML）
- 直扫基线可在无外部服务时独立运行，便于复现与回退