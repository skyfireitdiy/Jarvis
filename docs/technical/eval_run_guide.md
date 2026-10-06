# Terminal-Bench 2.0 评测运行指南

> 本文档说明**如何手动运行** Terminal-Bench 2.0 评测（Jarvis 适配层）。
> 环境搭建细节见 [eval_environment_setup.md](./eval_environment_setup.md)。
> 本文档聚焦「运行」本身，并包含 verifier 网络问题的增强镜像方案。

## 一、环境前提

- 已按 `eval_environment_setup.md` 完成环境搭建（harbor venv + 数据集 + wheelhouse）。
- 本机 Docker daemon 正常运行。
- 已配置 LLM API key（`~/.jarvis/config.yaml` 的 `ds` 模型组，或环境变量 `OPENAI_API_KEY`）。
- 本机代理环境变量 `http_proxy/https_proxy=127.0.0.1:7890` 会导致 pip/uv 安装失败，
  安装类命令需前置 `env -u http_proxy -u https_proxy` 直连（脚本已处理）。

## 二、快速运行（一键）

```bash
cd /home/skyfire/Jarvis

# 指定 harbor venv（本机实际路径），运行评测
EVAL_VENV_DIR=/home/skyfire/harbor-venv \
  bash scripts/run_eval.sh run \
  --n-tasks 1 --n-concurrent 1 \
  --include-task-name crack-7z-hash
```

- `run_eval.sh run` 会自动：
  1. 从 `~/.jarvis/config.yaml` 的 `ds` 模型组读取 platform/model/api_base/api_key；
  2. 透传 `OPENAI_API_KEY`、`OPENAI_API_BASE`、`JARVIS_MODEL`、`JARVIS_PLATFORM`；
  3. 透传 `OPENAI_EXTRA_BODY={"thinking":{"type":"disabled"}}`（禁用 deepseek 推理，关键修复）；
  4. 以 `JARVIS_WHEELHOUSE_DIR` 指向离线 wheelhouse，供容器内 `install()` 离线安装 jca。
- 其他常用参数：
  - `--n-tasks N`：跑 N 个任务；`--n-concurrent N`：并发数。
  - `--include-task-name <name>`：只跑指定任务（如 `crack-7z-hash`）。
  - `--agent-timeout-multiplier 2`：把 agent 超时放大 2 倍（默认 900s，复杂任务可能不够）。

> 终端是 fish 时用 `bash scripts/run_eval.sh ...` 显式调用。

### 后台运行（可选）

```bash
cd /home/skyfire/Jarvis
setsid env EVAL_VENV_DIR=/home/skyfire/harbor-venv \
  bash scripts/run_eval.sh run \
  --n-tasks 1 --n-concurrent 1 \
  --include-task-name crack-7z-hash \
  > /tmp/eval-run.log 2>&1 < /dev/null &
tail -f /tmp/eval-run.log
```

## 三、查看结果

Harbor 评测结果写在任务对应的 trial 目录下，核心文件是 `result.json`：

```bash
# 找到最近生成的 result.json
find ~/.cache/harbor -name result.json -newermt '-1 hour' 2>/dev/null | tail -5
```

`result.json` 中的关键字段：

```json
{
  "reward": 1, // 0 或 1
  "verifier": {
    "stdout": "...", // verifier 输出（pytest 结果）
    "reward": 1
  }
}
```

- `reward: 1`：任务通过。
- `reward: 0`：未通过。查看 `verifier.stdout` 判断是 agent 没完成，还是 verifier 本身失败。

## 四、verifier 网络问题与增强镜像方案（重要）

### 背景

Terminal-Bench 2.0 的 verifier 默认 `test.sh` 会在**评测容器内**执行：

```bash
curl -LsSf https://astral.sh/uv/0.9.5/install.sh | sh   # 下载 uv
uvx -p 3.13 -w pytest==8.4.1 pytest --ctrf ...           # 用 uvx 跑 pytest
```

但容器内访问 `astral.sh`（Cloudflare）**间歇性超时**，且 `curl` 无重试，
导致 uv/uvx 不可用、pytest 无法运行，**即使 agent 完成了任务也会 reward=0**。

### 解决方案：预构建增强镜像 + 修改 test.sh

让 verifier **完全离线**运行，不依赖容器内下载任何东西：

1. 构建增强镜像 `crack-7z-hash-enh`（预装 python3.12 + pytest + jca）。
2. 把缓存任务的 `test.sh` 改为用 `python3 -m pytest`（替代 curl+uvx）。
3. 把 `task.toml` 的 `docker_image` 指向增强镜像。

> Harbor 任务缓存命中后**不会覆盖**已存在的任务目录
> （`tasks/client.py` 中 `target_dir.exists() and not overwrite` 直接返回 cached），
> 因此修改 `~/.cache/harbor/tasks/.../crack-7z-hash/tests/test.sh` 和 `task.toml` 是安全的。

### 增强镜像 Dockerfile

```dockerfile
# scripts/docker/crack-7z-hash-enh.Dockerfile
FROM alexgshaw/crack-7z-hash:20251031

# 预装系统 python3.12 + pip + git（构建期网络可靠）
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip git \
    && rm -rf /var/lib/apt/lists/*

# 预装 pytest==8.4.1 + pytest-json-ctrf==0.3.5（纯 Python 包）
COPY pytest-site/ /tmp/pytest-site/
RUN cp -r /tmp/pytest-site/* /usr/lib/python3/dist-packages/ \
    && rm -rf /tmp/pytest-site

# 预装 jca（jarvis-ai-assistant）+ 依赖：用离线 cp312 wheelhouse 完全离线安装
COPY wheelhouse/ /tmp/wheelhouse/
RUN python3 -m pip install --break-system-packages --no-index \
        --find-links=/tmp/wheelhouse jarvis-ai-assistant \
    && rm -rf /tmp/wheelhouse

# PyPI 发布版未打包 builtin 提示词资源，从本机源码补齐
COPY prompts/ /root/.jarvis/prompts/

RUN python3 --version && python3 -m pytest --version && command -v jca
```

构建命令：

```bash
mkdir -p /tmp/enhimg
cp -r ~/.cache/harbor/wheelhouse /tmp/enhimg/wheelhouse
cp -r /tmp/pytest-site /tmp/enhimg/pytest-site       # pytest 8.4.1 + ctrf（见下）
cp -r /home/skyfire/Jarvis/builtin/prompts /tmp/enhimg/prompts
cp scripts/docker/crack-7z-hash-enh.Dockerfile /tmp/enhimg/Dockerfile
cd /tmp/enhimg && docker build -t crack-7z-hash-enh:latest .
```

> `pytest-site` 是预装好的 pytest 8.4.1 + pytest-json-ctrf 0.3.5 目录（纯 Python 包）。
>
> 生成方式（宿主机，Python 3.12）：
>
> ```bash
> uv pip install --python <py312> --target /tmp/pytest-site pytest==8.4.1 pytest-json-ctrf==0.3.5
> ```

### 修改 test.sh 与 task.toml

修改缓存任务目录（路径里的 hash 以实际为准）：

```bash
TASKDIR=~/.cache/harbor/tasks/MAyhSNHCZegJvZuPyTitjJ/crack-7z-hash

# 1. 改 test.sh：用 python3 -m pytest 替代 curl+uvx
cat > "$TASKDIR/tests/test.sh" <<'EOF'
#!/bin/bash
# 离线 verifier：使用增强镜像预装的 python3 + pytest
if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set."
    exit 1
fi
python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
if [ $? -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
EOF

# 2. 改 task.toml：docker_image 指向增强镜像
sed -i 's|docker_image = "alexgshaw/crack-7z-hash:20251031"|docker_image = "crack-7z-hash-enh:latest"|' "$TASKDIR/task.toml"
```

### 验证（离线）

```bash
docker run --rm --network=none \
  -v "$TASKDIR/tests/test_outputs.py:/tests/test_outputs.py:ro" \
  -v "$TASKDIR/tests/test.sh:/tests/test.sh:ro" \
  crack-7z-hash-enh:latest bash -c '
mkdir -p /app && echo "honeybear" > /app/solution.txt
mkdir -p /logs/verifier && cd /app
bash /tests/test.sh
echo "reward: $(cat /logs/verifier/reward.txt)"   # 期望 1
'
```

## 五、常见问题

### 1. reward=0，但 agent 明明完成了任务

大概率是 verifier 网络问题（见第四节）。先看 `result.json` 的 `verifier.stdout`：

- 若出现 `curl: (28) SSL connection timeout` / `uvx: command not found` → 用增强镜像方案。
- 若 agent 因超时未完成（`AgentTimeoutError`）→ 加 `--agent-timeout-multiplier 2`。

### 2. 容器内 pip 装依赖网络不稳

`install()` 已用离线 wheelhouse（`--no-index --find-links`）完全离线安装，
并带整体重试循环。若仍失败，确认 `JARVIS_WHEELHOUSE_DIR` 指向正确的 wheelhouse。

### 3. deepseek 响应超时 / 0 token

确认透传了 `OPENAI_EXTRA_BODY={"thinking":{"type":"disabled"}}`
（`run_eval.sh` 默认已加）。这是禁用 deepseek 推理模式的关键修复。

### 4. 其他任务也要用增强镜像？

每个任务的基础镜像不同（`python:3.13-slim`、`alexgshaw/gpt2-codegolf` 等）。
需为每个任务单独构建对应增强镜像、修改其缓存 `test.sh` 与 `task.toml`。
crack-7z-hash 的增强镜像方案可作为模板复用。

## 相关文件

- `scripts/run_eval.sh`：搭建 + 运行脚本（`setup` / `run` / `help`）。
- `src/jarvis/jarvis_eval/harbor_agent.py`：Jarvis 的 Harbor 适配层。
- `docs/technical/eval_environment_setup.md`：环境搭建文档。
