# Terminal-Bench 2.0 评测环境搭建

> 本文档说明如何在本地搭建 Terminal-Bench 2.0 评测环境，用 Jarvis 的
> Harbor 适配层（`src/jarvis/jarvis_eval/harbor_agent.py`）运行评测，
> 产出 `reward.txt` 0/1，作为自进化的量化标尺。

## 背景

Jarvis 通过 `jarvis_eval` 包封装为 Harbor 的 `BaseInstalledAgent`
（`JarvisInstalledAgent`），
使 Jarvis 能在 Terminal-Bench 2.0 的隔离 Docker 任务环境中解决真实终端任务。
评测流程：

1. Harbor 在任务容器内安装 `jarvis-ai-assistant` 提供 `jca` CLI
   （优先用本机预构建的离线 wheelhouse，`--no-index --find-links` 完全离线安装；
   未提供 wheelhouse 时回退到在线多镜像源安装）
2. `run()` 把任务 instruction 写入容器文件，调用 `jca -n --task-file <path>` 执行
3. LLM API key 通过 Harbor 的 `--ae` 透传给容器内的 `jca` 进程
4. 每个任务产出 `reward.txt` 0/1，可对比进化前后通过率

## 环境要求

| 依赖        | 版本要求     | 说明                                           |
| ----------- | ------------ | ---------------------------------------------- |
| Docker      | 任意现代版本 | Terminal-Bench 隔离环境，需 daemon 运行        |
| uv          | 0.12+        | 创建隔离评测虚拟环境                           |
| Python      | 3.12+        | harbor 要求 `>=3.12`（本机为 3.14）            |
| 磁盘        | ≥10GB        | 评测容器镜像 + 数据集缓存                      |
| LLM API key | 任意         | OpenAI/Anthropic/DeepSeek 等，用于容器内 `jca` |

> **注意**：本机若配置了代理环境变量（`http_proxy`/`https_proxy`），
> 安装 harbor 时需直连（`env -u http_proxy -u https_proxy ...`），否则安装失败。
> 评测运行脚本已内置该处理。

## 快速开始

推荐使用项目自带的脚本 `scripts/run_eval.sh`，一条命令完成环境搭建：

```bash
# 1. 搭建环境（创建 venv + 安装 harbor + 下载数据集）
./scripts/run_eval.sh setup

# 2. 运行评测（需先设置 LLM API key）
export OPENAI_API_KEY=sk-xxx
./scripts/run_eval.sh run --n-concurrent 4 --n-tasks 10
```

脚本会：

- 用 `uv` 在 `~/.jarvis-eval-venv` 创建隔离虚拟环境（不污染系统 Python）
- 安装 `harbor` 并下载 `terminal-bench@2.0` 数据集到 `~/.cache/harbor/tasks`
- 用 Python 3.12 构建离线 wheelhouse 到 `~/.cache/harbor/wheelhouse`
  （本机预下载 `jarvis-ai-assistant` 及全部依赖，供容器离线安装）
- 运行 `harbor run`，自动透传已设置的 API key 环境变量

## 手动搭建（等价于脚本内部步骤）

```bash
# 1. 创建隔离虚拟环境并安装 harbor
uv venv ~/.jarvis-eval-venv --python 3.14
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    uv pip install --python ~/.jarvis-eval-venv/bin/python harbor

# 2. 下载 terminal-bench@2.0 数据集（89 个任务）
~/.jarvis-eval-venv/bin/harbor download "terminal-bench@2.0" --cache

# 3. 运行评测
export OPENAI_API_KEY=sk-xxx
PYTHONPATH=src ~/.jarvis-eval-venv/bin/harbor run \
    --dataset terminal-bench@2.0 \
    -a jarvis.jarvis_eval.harbor_agent:JarvisInstalledAgent \
    --ae OPENAI_API_KEY=$OPENAI_API_KEY \
    --n-concurrent 4
```

## 关键参数

| 参数                                                      | 说明                                       |
| --------------------------------------------------------- | ------------------------------------------ |
| `-a jarvis.jarvis_eval.harbor_agent:JarvisInstalledAgent` | 指定 Jarvis 适配层类（自定义 import path） |
| `--ae KEY=VALUE`                                          | 透传环境变量给容器内的 `jca`（API key 等） |
| `--dataset terminal-bench@2.0`                            | 评测数据集                                 |
| `-n/--n-concurrent`                                       | 并发评测数（默认 4）                       |
| `--n-tasks`                                               | 最多运行的任务数（用于小规模验证）         |
| `--print-config`                                          | 只打印解析后的配置，不实际运行（用于自检） |

## 验证环境可用性

### 1. 确认适配层可被 Harbor 加载

```bash
cd /path/to/Jarvis
PYTHONPATH=src ~/.jarvis-eval-venv/bin/python -c "
from harbor.utils.import_path import import_class
from harbor.agents.installed.base import BaseInstalledAgent
cls = import_class('jarvis.jarvis_eval.harbor_agent:JarvisInstalledAgent')
assert cls.name() == 'jarvis'
assert issubclass(cls, BaseInstalledAgent)
print('适配层加载 OK')
"
```

### 2. 确认配置解析正确（不实际运行）

```bash
PYTHONPATH=src ~/.jarvis-eval-venv/bin/harbor run \
    --dataset terminal-bench@2.0 \
    -a jarvis.jarvis_eval.harbor_agent:JarvisInstalledAgent \
    --ae OPENAI_API_KEY=test --print-config
```

应输出包含 `"name": "terminal-bench", "version": "2.0"` 和 agent 路径的 JSON。

### 3. 确认数据集可下载

```bash
~/.jarvis-eval-venv/bin/harbor download "terminal-bench@2.0" --cache
# 输出 "Successfully downloaded 89 task(s)"
```

## 产出与结果

- 评测结果默认写入 `jobs/` 目录（`harbor run` 的 `--jobs-dir` 参数可改）
- 每个任务产出 `reward.txt` 0/1
- 可对比进化前后同一批任务的通过率，作为自进化量化标尺

## 重要注意事项

1. **安装来源**：适配层 `install()` 在容器内安装 `jarvis-ai-assistant`。
   默认优先使用**本机预构建的离线 wheelhouse**（`JARVIS_WHEELHOUSE_DIR` 指定，
   默认 `~/.cache/harbor/wheelhouse`），完全离线安装，绕开容器内直连 PyPI
   下载大包（playwright 等）网络不稳的问题。未提供 wheelhouse 时回退到
   在线多镜像源安装（清华 → 阿里云 → 直连 PyPI）。
   wheelhouse 由 `run_eval.sh setup` 用 Python 3.12 自动构建（与容器
   Ubuntu 24.04 的 Python 版本匹配，确保 wheel 平台/ABI 兼容），
   内含 `jarvis-ai-assistant` 及其全部依赖。默认取 **PyPI 最新版**
   （`JCA_VERSION=latest`），也可用 `JCA_VERSION=<版本>` 指定具体版本；
   wheelhouse 已构建时默认跳过（marker 记录实际版本），发新版本后
   需 `JCA_FORCE_REBUILD=1` 强制重建才会用新版。
   若需用本机最新源码评测，需先发布到 PyPI，或调整 `harbor_agent.py` 的
   `install()` 改为从本地 wheel/git 安装。

2. **API key 必须**：容器内 `jca` 需要真实 LLM API key 才能解决任务，
   通过 `--ae` 透传。无 key 时评测无法进行。

3. **网络**：使用离线 wheelhouse 时，容器内安装 `jarvis-ai-assistant` **无需访问 PyPI**。
   但 `jca` 运行仍需访问模型 API（通过 `--ae` 透传的 `OPENAI_API_BASE` 等）。
   若容器无法直连模型 API，需在 `--ae` 中透传代理变量（`HTTP_PROXY`/`HTTPS_PROXY`）。

4. **惰性依赖**：`jarvis_eval` 包本身不 import harbor，Jarvis 主项目可安全
   import；仅 `harbor_agent` 模块需要 harbor 环境。

## 相关文件

- `src/jarvis/jarvis_eval/harbor_agent.py` —— Jarvis 的 Harbor 适配层
- `src/jarvis/jarvis_eval/__init__.py` —— 轻量包入口（无 harbor 依赖）
- `tests/jarvis_eval/test_harbor_agent.py` —— 适配层单元测试
- `scripts/run_eval.sh` —— 评测环境搭建与运行脚本
