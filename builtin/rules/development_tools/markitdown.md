---
name: markitdown
description: 当需要将文件转换为Markdown格式时触发。每当用户提及"文件转markdown"、"文档转换"、"markitdown"时触发。不触发：仅编写Markdown内容；仅阅读Markdown文件；Markdown格式化不涉及文件转换。
license: MIT
---

# markitdown 工具使用规则

## 规则简介

markitdown乃微软所创之轻量级Python工具，专用于将各类文件格式转换为Markdown格式，尤适于LLM与文本分析管道。其支持PDF、PowerPoint、Word、Excel、图像、音频、HTML等多种格式之转换，能保留重要之文档结构（标题、列表、表格、链接等）。

## 汝必守之原则

### 1. 安装配置原则

**要求说明：**

- **必**：直接安装完整功能版本以获最佳体验
- **荐**：用uv工具进行安装管理

**示例：**

```bash
# 用uv安装markitdown完整功能版本
uv tool install 'markitdown[all]'
```

### 2. 使用安全原则

**要求说明：**

- **必**：处理敏感文档时确保环境安全
- **必**：用Azure文档智能时配置正确之端点
- **禁**：将API密钥等敏感信息硬编码于代码中
- **禁**：处理未知来源之恶意文件

## 汝必行之操作

### 操作1：命令行使用

**执行步骤：**

1. 基本文件转换
2. 指定输出文件
3. 管道操作

**示例：**

```bash
# 基本转换
markitdown document.pdf > output.md

# 指定输出文件
markitdown document.pdf -o output.md

# 管道操作
cat document.pdf | markitdown
```

### 操作2：Python API调用

**执行步骤：**

1. 导入MarkItDown类
2. 创建转换器实例
3. 执行转换操作

**示例：**

```python
from markitdown import MarkItDown

# 基本使用
md = MarkItDown(enable_plugins=False)
result = md.convert("document.docx")
print(result.text_content)

# 用LLM进行图像描述
from openai import OpenAI

client = OpenAI()
md = MarkItDown(
    llm_client=client,
    llm_model="gpt-4o",
    llm_prompt="描述图像内容"
)
result = md.convert("image.jpg")
```

### 操作3：插件使用

**执行步骤：**

1. 安装插件
2. 启用插件功能
3. 用插件增强功能

**示例：**

```bash
# 安装OCR插件
pip install markitdown-ocr

# 列出可用插件
markitdown --list-plugins

# 启用插件
markitdown --use-plugins document.pdf
```

### 操作4：Azure文档智能集成

**执行步骤：**

1. 配置Azure文档智能端点
2. 用文档智能功能
3. 处理转换结果

**示例：**

```bash
# 命令行使用
markitdown document.pdf -o output.md -d -e "<your-endpoint>"
```

```python
# Python API使用
from markitdown import MarkItDown

md = MarkItDown(docintel_endpoint="<your-endpoint>")
result = md.convert("document.pdf")
```

## 可选依赖项说明

markitdown支持按需安装之功能模块：

- `[all]` - 安装所有可选依赖
- `[pptx]` - PowerPoint文件支持
- `[docx]` - Word文件支持
- `[xlsx]` - Excel文件支持
- `[pdf]` - PDF文件支持
- `[az-doc-intel]` - Azure文档智能
- `[audio-transcription]` - 音频转录
- `[youtube-transcription]` - YouTube转录

## 检查清单

用markitdown完成任务后，汝必确认：

- [ ] 已正确安装markitdown与所需依赖
- [ ] 虚拟环境已激活（若用）
- [ ] 输入文件格式受支持
- [ ] 输出Markdown内容结构正确
- [ ] 敏感信息已妥善处理
- [ ] 必要之错误处理已实现

## 相关资源

- 官方GitHub仓库：[https://github.com/microsoft/markitdown](https://github.com/microsoft/markitdown)
- PyPI包页面：[https://pypi.org/project/markitdown/](https://pypi.org/project/markitdown/)
- Azure文档智能：[https://learn.microsoft.com/azure/ai-services/document-intelligence](https://learn.microsoft.com/azure/ai-services/document-intelligence)
