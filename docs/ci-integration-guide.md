# Jarvis CI 集成指南

本文档介绍如何把 Jarvis 接入 CI/CD（GitHub Actions / GitLab CI），实现 **PR 自动代码审查、issue 自动分类、CI 测试自动汇报**。

Jarvis 复用 **headless 非交互模式**（`jvs -n`）+ **`--task-file` 状态文件机制** 完成 CI 集成，无需额外服务。

---

## 1. 原理

Jarvis CodeAgent CLI（`jvs`）支持两种 CI 友好用法：

### 1.1 直接传任务（简单场景）

```bash
jvs -n --task "对 src/ 目录做一次代码审查"
```

- `-n` / `--non-interactive`：非交互模式，任务完成后自动退出
- 输出写到 stdout

### 1.2 通过 `--task-file` 传 JSON（推荐，支持状态文件）

```bash
cat > task.json <<'EOF'
{
  "task_desc": "请审查本次代码变更",
  "background": "这是 CI 自动审查",
  "status_file": "/tmp/status.json"
}
EOF

jvs -n --task-file task.json
```

任务完成后会生成：

| 文件                                            | 内容                                                 |
| ----------------------------------------------- | ---------------------------------------------------- |
| `status_file`（如 `/tmp/status.json`）          | `{"status": "completed"/"failed", "exit_code": 0/1}` |
| `status_file.output`（如 `/tmp/status.output`） | Agent 的结构化输出                                   |
| `status_file.error`（如 `/tmp/status.error`）   | 失败时的错误信息                                     |

CI 只需解析这三个文件即可拿到结构化结果，**无需新增 `--output-format json` 参数**。

---

## 2. GitHub Actions 模板

仓库 `scripts/ci/` 下提供 3 个开箱即用的模板：

| 模板                      | 触发      | 用途                                |
| ------------------------- | --------- | ----------------------------------- |
| `jarvis-pr-review.yml`    | PR        | 对 `git diff` 做代码审查，评论到 PR |
| `jarvis-issue-triage.yml` | issue     | 自动分类 issue 并评论               |
| `jarvis-ci-test.yml`      | push / PR | 跑测试并汇报结果                    |

### 2.1 使用步骤

1. 把对应模板复制到你的仓库 `.github/workflows/` 下（如 `jarvis-pr-review.yml`）。
2. 在仓库 **Settings → Secrets and variables → Actions** 配置（Jarvis 从标准 LLM 环境变量读取 API Key）：
   - `OPENAI_API_KEY`（OpenAI 平台）：调用 LLM 的 API Key
   - `ANTHROPIC_API_KEY`（Anthropic 平台）：调用 LLM 的 API Key
   - `OPENAI_API_BASE`（可选）：自定义 OpenAI 兼容端点
   - `JARVIS_MODEL`（可选）：指定模型，默认 `gpt-5`
   - `JARVIS_PLATFORM`（可选）：指定平台，默认 `openai`
3. 按需调整模板里的 `TEST_COMMAND`（`jarvis-ci-test.yml`，默认 `pytest -v`）或 `JARVIS_REVIEW_RULES`（`jarvis-pr-review.yml`，附加审查规则）。

> **安装与配置说明**：模板用 `pip install jarvis-ai-assistant` 从 PyPI 安装 Jarvis（适用于任意用户仓库）。首次运行 `jvs` 会自动生成默认 `~/.jarvis/config.yaml`（无交互），API Key 通过上述标准环境变量注入，**无需预置 config.yaml**。

### 2.1.1 无交互快速配置（便于 CI）

Jarvis 提供两种无交互配置方式，二选一即可：

#### 方式 A：环境变量（运行期覆盖，最轻量）

```bash
export OPENAI_API_KEY=sk-xxx        # API Key
export JARVIS_MODEL=gpt-4o          # 覆盖默认模型 gpt-5
export JARVIS_PLATFORM=openai       # 覆盖默认平台 openai
export JARVIS_SKIP_INTERACTIVE_CONFIG=1  # 跳过首次交互配置引导
jvs -n --task-file task.json
```

环境变量优先级最高（> config.yaml > 默认值），适合临时指定模型/平台，无需写文件。

#### 方式 B：`jqc` 非交互模式（持久化写入 config.yaml）

```bash
jqc --platform openai --base-url https://api.openai.com/v1 \
    --api-key sk-xxx --model gpt-4o --group default --skip-test
```

一次性把模型写入 `~/.jarvis/config.yaml` 的 `llms` + `llm_groups` 并设为默认组，后续 `jvs` 直接可用。适合 CI 里先配置再跑，或本地持久化。`--skip-test` 跳过连通性测试（避免 CI 网络依赖）。

> 交互模式：直接运行 `jqc`（不带参数）按提示输入，逻辑保持不变。

### 2.2 PR 自动审查（jarvis-pr-review.yml）

- 触发：`pull_request`（opened / synchronize / reopened），跳过 draft PR
- 流程：checkout（`fetch-depth: 0` 取完整历史）→ 安装 Jarvis → 计算 PR diff → 构建 task-file → `jvs -n --task-file` 审查 → 解析 `.output` → 用 `github-script` 评论到 PR
- 权限：需 `pull-requests: write`

### 2.3 Issue 自动分类（jarvis-issue-triage.yml）

- 触发：`issues`（opened）
- 流程：把 issue 正文写入临时文件 → 构建 task-file → `jvs -n` 分类 → 评论分类结论
- 权限：需 `issues: write`

### 2.4 CI 测试汇报（jarvis-ci-test.yml）

- 触发：push（main）/ PR
- 流程：安装依赖 → 构建 task-file → `jvs -n` 跑测试并分析失败根因 → PR 上评论测试报告
- 相比纯 pytest：Jarvis 能**自动分析失败用例、定位根因、给出修复建议**

---

## 3. GitLab CI 示例

GitLab CI 同样可用 `jvs -n --task-file`，示例 `.gitlab-ci.yml`：

```yaml
jarvis-review:
  stage: test
  image: python:3.12
  variables:
    OPENAI_API_KEY: $OPENAI_API_KEY # 在 CI/CD Variables 配置（OpenAI 平台）
    JARVIS_SKIP_INTERACTIVE_CONFIG: "1" # 跳过交互式配置引导
  script:
    - pip install jarvis-ai-assistant
    - |
      cat > /tmp/task.json <<'EOF'
      {
        "task_desc": "请审查本次 MR 的代码变更",
        "status_file": "/tmp/status.json"
      }
      EOF
    - jvs -n --task-file /tmp/task.json || true
    - cat /tmp/status.output 2>/dev/null || echo "(无输出)"
  artifacts:
    paths:
      - /tmp/status.json
      - /tmp/status.output
    when: always
```

---

## 4. 注意事项

- **API Key 安全**：务必通过 CI 平台的 Secrets/Variables 注入，**不要**硬编码在 workflow 文件或仓库中。
- **非交互模式必须传任务**：`jvs -n` 若不带 `--task` 或 `--task-file` 会报错退出（`exit code 2`）。
- **失败容忍**：模板中 `jvs ... || true` 是为了保证 Jarvis 审查失败时不阻塞 CI 主流程；如需让 Jarvis 结果影响 CI 通过/失败，可去掉 `|| true` 并根据 `status_file` 的 `exit_code` 判断。
- **LLM 成本**：CI 每次运行都会调用 LLM，建议只在必要事件（如非 draft PR、新 issue）触发，避免过度消耗。
- **模型配置**：若仓库有 `config.yaml`，Jarvis 会读取其中的 `llm_group` 等配置；CI 环境变量优先级更高。

---

## 5. 验证

本地可用样例 diff 跑通审查流程：

```bash
# 准备样例 diff
git diff HEAD~1 > /tmp/pr.diff

# 构建 task-file 并运行
cat > /tmp/task.json <<'EOF'
{
  "task_desc": "请审查 /tmp/pr.diff 中的代码变更",
  "status_file": "/tmp/status.json"
}
EOF

jvs -n --task-file /tmp/task.json
cat /tmp/status.output
```

确认 `status_file` 生成、`.output` 含结构化结论即可。
