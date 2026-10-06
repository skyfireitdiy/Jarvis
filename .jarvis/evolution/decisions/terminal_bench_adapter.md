# Terminal-Bench 2.0 接入方案：Harbor 适配层（BaseInstalledAgent + jca CLI）

> 状态：**已实现并单元测试**（2026-10-06 第六轮）
> 决策背景：第五轮调研确认 Terminal-Bench 2.0 可作为自进化量化标尺（Claude Code/Codex 都在用），但当时因"大工程 + 评估能力而非增强能力"后置。本轮按 Administrator 确认的 **B + C 方案**落地实现：B = 适配层 + 本机 mock 单元测试；C = 运行脚本/文档（面向 Docker/云端机器）。

## 目标

把 Jarvis 封装进 Harbor 的 `BaseInstalledAgent`，使 Jarvis 能在 Terminal-Bench 2.0 的隔离任务环境中解决真实终端任务，产出 `reward.txt` 0/1，作为**自进化量化标尺**（进化前后跑同一批任务对比通过率）。

## 方案选型：BaseInstalledAgent（而非 BaseAgent）

调研时最初倾向 `BaseAgent`（外部 agent，agent loop 在 Harbor 进程跑，通过 `environment.exec()` 控制任务环境）。但 Administrator 指出 **Jarvis 有命令行工具 `jca`**，因此改用 **`BaseInstalledAgent`**：

- `install()`：在任务容器内 `pip install jarvis-ai-assistant`，把 jca CLI 装进容器
- `run()`：在容器内调用 `jca -n --task-file <instruction文件>` 解决任务
- 优点：agent loop 完全跑在任务容器里，与 Harbor 的隔离模型天然契合，无需在 Harbor 进程内重定向 Jarvis 的终端执行

## 实现

### 文件

- `src/jarvis/jarvis_eval/harbor_agent.py` —— 适配层主代码（`JarvisInstalledAgent`）
- `src/jarvis/jarvis_eval/__init__.py` —— 轻量 docstring，**不 import harbor**（Jarvis 主项目 import 该包安全，无 harbor 依赖）
- `tests/jarvis_eval/test_harbor_agent.py` —— 11 个单元测试（mock BaseEnvironment，不依赖 Docker）

### JarvisInstalledAgent 关键设计

- `capabilities = AgentCapabilities()`，`MODEL_CONNECTION = ModelConnectionSpec(default_provider=None, api_key_envs=_PASSTHROUGH_ENV_VARS, passthrough=True)`
- `name()` 返回 `"jarvis"`（AgentName 枚举无 jarvis，用自定义字符串）
- `install()`：先 `command -v jca` 检查，未安装则 `python3 -m pip install --quiet --upgrade jarvis-ai-assistant`
- `run()`：`@with_prompt_template` 装饰，把 instruction **base64 编码**写入 `/tmp/jarvis-instruction.txt`（避免特殊字符/引号问题），然后 `jca -n --task-file /tmp/jarvis-instruction.txt 2>&1 | tee <logs>/jca-<uuid>.log`
- `_build_passthrough_env()`：从 `_get_env` 读取 `_PASSTHROUGH_ENV_VARS`（OPENAI_API_KEY / ANTHROPIC_API_KEY / DEEPSEEK_API_KEY 等 11 个变量）透传给 jca 进程，使容器内 jca 能访问模型 API
- `get_version_command()` 返回 `"jca --version 2>/dev/null || true"`，`parse_version()` 取 stdout strip

### 关键技术决策与坑

1. **顶层 import harbor（非惰性函数内 import）**：Harbor 的 `import_class` 要求 `isinstance(symbol, type)`——必须是**类**，不能是工厂函数。所以 `harbor_agent.py` 模块顶层 `from harbor... import`，用 `# type: ignore` 抑制 ty 误报。`__init__.py` 保持轻量不 import harbor_agent，保证 Jarvis 主项目 import `jarvis_eval` 包安全。
2. **`# type: ignore[unresolved-import]` 对 ty 不生效**，必须用通用 `# type: ignore`。
3. **`# type: ignore` 字面量不能出现在注释文本里**，否则 ty 误报 `invalid-ignore-comment`。
4. **`BaseInstalledAgent._exec` 会自动加 `set -o pipefail;`**，run 命令里不要再自己加（已清理）。
5. **`exec_as_agent` 的 user 为 None**（默认 agent 用户）。
6. **jca CLI 参数**（已验证 code_agent.py:1117-1270）：`jca -n --task-file <path>` 非交互模式从文件读任务（支持纯文本或 JSON `{"task_desc":...}`），`-n` 必须配 task/task-file，任务环境里**不需要 `-w`**（worktree）。
7. **jca API key 读取**（已验证 openai.py:154-171）：从 `llm_config.openai_api_key` 或环境变量 `OPENAI_API_KEY` 读取，base_url 从 `OPENAI_API_BASE`/`OPENAI_BASE_URL` 读取。

## 验证

- 单元测试：`tests/jarvis_eval/test_harbor_agent.py` **11 passed**（有 harbor 环境）+ **1 skipped**（无 harbor 时正确跳过）
- Harbor `import_class` 加载验证：`harbor.utils.import_path.import_class('jarvis.jarvis_eval.harbor_agent:JarvisInstalledAgent')` 成功，`name()` 返回 `jarvis`，是 `BaseInstalledAgent` 子类
- 无 harbor 时安全：`import jarvis.jarvis_eval` 不触发 harbor 依赖
- 静态检查：ruff 0 错误、ruff format 通过、ty All checks passed
- 回归：`tests/jarvis_agent/` 全套 passed（新增 jarvis_eval 包不影响其他模块）

## 运行（Docker/云端机器，本机无法跑）

```bash
# 1. 安装 harbor（需 Docker 20GB+ 磁盘、Python3.9+、联网）
pip install harbor

# 2. 跑 Terminal-Bench 2.0，用 Jarvis 适配层
harbor run \
  --dataset terminal-bench@2.0 \
  -a jarvis_eval.harbor_agent:JarvisInstalledAgent \
  --ae OPENAI_API_KEY=sk-xxx \
  --n-concurrent 4
```

- `-a` 指定适配层类（import 路径:类名）
- `--ae` 透传环境变量给任务容器（jca 需要模型 API key）
- 产出 `reward.txt` 0/1，可对比进化前后通过率

## 边界与后续

- **适配层实现完 ≠ 直接接入**：实际评测还需 Docker 机器 + API key + `harbor run` 命令，本机资源不足（磁盘 1.8G/内存 3.8G）无法跑 Docker 镜像。
- **后续**：在 Docker/云端机器上跑通真实评测，作为自进化量化标尺；对比进化前后 reward 通过率。
