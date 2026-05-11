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
