# 接入 Jev（TypeSafe System One）平台

## 使用场景

如果你希望把「类型化决策」这类判断交给 Jev 处理——例如从一批候选中选一个、按量表打分、做是/否判定——可以启用内置的 `jev` 平台。Jev 不生成自由文本、不支持多模态、也没有对话历史，一次请求返回结构化的概率化答案，适合替代「用大模型做小判断」的场景。

## 前置条件

- 一个 TypeSafe API Key（在 [TypeSafe 控制台](https://console.typesafe.ai/) 创建）。
- 网络可访问 `https://api.typesafe.ai`（或你自建的兼容网关）。

## 操作步骤

1. 在 `config.yaml` 的 `llms` 中新增一个 Jev 模型定义，`platform` 填 `jev`：

   ```yaml
   llms:
     jev:
       platform: jev
       model: jev-latest
       max_input_token_count: 64000
       llm_config:
         typesafe_api_key: "your-typesafe-api-key"
         typesafe_api_base: "https://api.typesafe.ai"
   ```

2. 在 `llm_groups` 中引用它。Jev 适合放在 `cheap_llm` 位置（用于廉价的小判断）：

   ```yaml
   llm_groups:
     default:
       normal_llm: gpt-5
       cheap_llm: jev
   ```

3. 重新启动 Jarvis，平台会在启动阶段被自动发现并注册。

## 输入格式

Jev 平台的 `chat()` 采用 JSON 文本协议，输入形如：

```json
{
  "state": "待评估的内容，可以是字符串、对象或数组",
  "questions": {
    "is_urgent": { "type": "noul", "instructions": "是否表达紧迫性？" },
    "department": {
      "type": "choice",
      "instructions": "应由哪个团队处理？",
      "criteria": { "billing": "计费", "technical": "技术" }
    },
    "frustration": {
      "type": "score",
      "instructions": "客户有多不满？",
      "criteria": ["平静", "不满", "非常愤怒"]
    }
  }
}
```

三种问题类型：

- `noul`：是/否判断，返回「是」的概率（0~1）。
- `choice`：从 `criteria` 定义的选项中选一个，最多 255 项，返回选中项、概率分布与 confidence。
- `score`：按 `criteria` 定义的有序量表打分，2~10 级，返回分数、各等级概率与 confidence。

## 你会看到的输出

平台会把结构化答案序列化为可读文本，包含每个问题的取值、confidence、概率分布（score 还含 legend），以及本次请求的 token 用量。

## 注意事项

- **仅文本输入**：不支持图像、音频、视频，多模态内容会被降级为文本。
- **无对话语义**：Jev 不维护上下文，每次请求只依赖当前输入；`set_system_prompt` 仅记录不参与请求。
- **中文效果弱于英文**：官方明确说明 CJK 支持不如英文，实际使用前请用中文样本自测，并关注 confidence。
- **数据出境**：Jev 是境外托管 API，`state` 内容会发送到 TypeSafe 服务端。若你的内容敏感，请先做合规评估。
- **限流**：遇到 429/529 时平台会自动指数退避重试（最多 4 次），并尊重 `retry-after` 头。
- **模型名**：非 `jev` 开头的模型名会被自动回退为 `jev-latest`，避免串到其它平台的模型名。
