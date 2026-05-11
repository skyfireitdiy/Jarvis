---
name: fireworks_tech_graph
description: 当需要创建技术图表时使用此规则——Fireworks技术图表生成规则，将自然语言描述转换为高质量SVG图表并导出PNG。包括：架构图、数据流图、流程图、Agent架构图、记忆架构图、序列图、对比矩阵、时间线、思维导图、UML类图、用例图、状态机图、ER图、网络拓扑图等14种图表类型；7种视觉样式（扁平图标、深色终端、蓝图、Notion简洁、玻璃态、Claude官方、OpenAI官方）；SVG生成与验证；布局规则与箭头语义。每当用户提及"画图"、"帮我画"、"生成图"、"做个图"、"架构图"、"流程图"、"可视化一下"、"出图"、"generate diagram"、"draw diagram"、"visualize"或任何需要图示化的系统/流程描述时触发。
license: MIT
---

# Fireworks Tech Graph

生成高质量SVG技术图表并通过`rsvg-convert`导出PNG。

## 安装源

从GitHub安装此技能：

```bash
npx skills add yizhiyanhua-ai/fireworks-tech-graph
```

公共包页面：

```text
https://www.npmjs.com/package/@yizhiyanhua-ai/fireworks-tech-graph
```

更新命令：

```bash
npx skills add yizhiyanhua-ai/fireworks-tech-graph --force -g -y
```

## 辅助脚本（推荐）

`scripts/`目录中的四个辅助脚本提供稳定的SVG生成和验证：

### 1. generate-diagram.sh - 验证SVG + 导出PNG

```bash
./scripts/generate-diagram.sh -t architecture -s 1 -o ./output/arch.svg
```

### 2. generate-from-template.py - 从模板创建SVG

```bash
python3 ./scripts/generate-from-template.py architecture ./output/arch.svg '{"title":"My Diagram","nodes":[],"arrows":[]}'
```

### 3. validate-svg.sh - 验证SVG语法

```bash
./scripts/validate-svg.sh <svg-file>
```

### 4. test-all-styles.sh - 批量测试所有样式

```bash
./scripts/test-all-styles.sh
```

## 工作流程（始终遵循此顺序）

1. **分类**图表类型
2. **提取结构** — 从用户描述中识别层、节点、边、流和语义组
3. **规划布局** — 应用图表类型的布局规则
4. **加载样式参考** — 默认加载style-1-flat-icon
5. **将节点映射到形状** — 使用形状词汇表
6. **检查图标需求**
7. **编写SVG** — 使用Python List方法（强制）
8. **验证**：运行`rsvg-convert file.svg -o /dev/null 2>&1`
9. **导出PNG**：`rsvg-convert -w 1920 file.svg -o file.png`
10. **报告**生成的文件路径
11. **（可选）视觉自查**

## 图表类型与布局规则

### 架构图

节点=服务/组件。分组为水平层（从上到下或从左到右）。

- 典型层：客户端 → 网关/负载均衡 → 服务 → 数据/存储
- 使用`<rect>`虚线容器将同一层的相关服务分组
- 箭头方向跟随数据/请求流
- ViewBox：`0 0 960 600`标准，`0 0 960 800`用于高堆栈

### 数据流图

强调数据移动到哪里。关注数据转换。

- 为每个箭头标注数据类型（如embeddings、query、context）
- 使用更宽的箭头（stroke-width: 2.5）表示主要数据路径
- 虚线箭头表示控制/触发流
- 按数据类别为箭头着色

### 流程图/过程流

顺序决策/过程步骤。

- 优先从上到下；宽流程从左到右
- 菱形表示决策，圆角矩形表示过程，平行四边形表示I/O
- 保持节点标签简短（≤3个词）
- 在网格上对齐节点：x位置对齐到120px间隔，y对齐到80px

### Agent架构图

展示AI代理如何推理、使用工具和管理记忆。

关键概念层：
- **输入层**：用户、查询、触发
- **Agent核心**：LLM、推理循环、规划器
- **记忆层**：短期（上下文窗口）、长期（向量/图数据库）、情景
- **工具层**：工具调用、API、搜索、代码执行
- **输出层**：响应、动作、副作用

使用循环箭头（循环弧）显示迭代推理。视觉上分离不同类型的记忆。

### 记忆架构图（Mem0、MemGPT风格）

专注于记忆操作的Agent图。

- 分别显示记忆写入路径和读取路径（不同箭头颜色）
- 记忆层级：工作记忆 → 短期 → 长期 → 外部存储
- 标注记忆操作：store()、retrieve()、forget()、consolidate()
- 使用堆叠矩形或分层圆柱体表示存储层级

### 序列图

参与者之间按时间排序的消息交换。

- 参与者作为垂直生命线（顶部标签 + 垂直虚线）
- 消息作为生命线之间的水平箭头，从上到下时间排序
- 激活框（生命线上的细填充矩形）显示活动处理
- 使用`<rect>`循环/alt框架分组，标签在左上角
- ViewBox高度 = 80 + (消息数 × 50)
