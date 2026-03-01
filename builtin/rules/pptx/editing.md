# 编辑演示文稿

## 基于模板的工作流程

当使用现有演示文稿作为模板时：

1. **分析现有幻灯片**：

   ```bash
   python scripts/thumbnail.py template.pptx
   python -m markitdown template.pptx
   ```

   查看 `thumbnails.jpg` 了解布局，并查看 markitdown 输出了解占位符文本。

2. **规划幻灯片映射**：对于每个内容部分，选择一个模板幻灯片。

   ⚠️ **使用多样化的布局**——单调的演示文稿是常见的失败模式。不要默认使用基本标题 + 项目符号幻灯片。积极寻找：
   - 多列布局（2 列、3 列）
   - 图像 + 文本组合
   - 带文本覆盖的全出血图像
   - 引用或展示幻灯片
   - 章节分隔符
   - 统计/数字展示框
   - 图标网格或图标 + 文本行

   **避免**：为每张幻灯片重复相同的文本密集型布局。

   将内容类型与布局样式匹配（例如，关键点 → 项目符号幻灯片，团队信息 → 多列，推荐语 → 引用幻灯片）。

3. **解包**：`python scripts/office/unpack.py template.pptx unpacked/`

4. **构建演示文稿**（自己做，而不是使用子代理）：
   - 删除不需要的幻灯片（从 `<p:sldIdLst>` 中删除）
   - 复制要重用的幻灯片（`add_slide.py`）
   - 在 `<p:sldIdLst>` 中重新排序幻灯片
   - **在步骤 5 之前完成所有结构更改**

5. **编辑内容**：在每个 `slide{N}.xml` 中更新文本。
   **如果可用，在此处使用子代理**——幻灯片是单独的 XML 文件，因此子代理可以并行编辑。

6. **清理**：`python scripts/clean.py unpacked/`

7. **打包**：`python scripts/office/pack.py unpacked/ output.pptx --original template.pptx`

---

## 脚本

| 脚本           | 用途                   |
| -------------- | ---------------------- |
| `unpack.py`    | 提取并美化打印 PPTX    |
| `add_slide.py` | 复制幻灯片或从布局创建 |
| `clean.py`     | 删除孤立文件           |
| `pack.py`      | 带验证重新打包         |
| `thumbnail.py` | 创建幻灯片的视觉网格   |

### unpack.py

```bash
python scripts/office/unpack.py input.pptx unpacked/
```

提取 PPTX，美化打印 XML，转义智能引号。

### add_slide.py

```bash
python scripts/add_slide.py unpacked/ slide2.xml      # 复制幻灯片
python scripts/add_slide.py unpacked/ slideLayout2.xml # 从布局创建
```

打印要添加到 `<p:sldIdLst>` 中所需位置的 `<p:sldId>`。

### clean.py

```bash
python scripts/clean.py unpacked/
```

删除不在 `<p:sldIdLst>` 中的幻灯片、未引用的媒体、孤立的关系。

### pack.py

```bash
python scripts/office/pack.py unpacked/ output.pptx --original input.pptx
```

验证、修复、压缩 XML、重新编码智能引号。

### thumbnail.py

```bash
python scripts/thumbnail.py input.pptx [output_prefix] [--cols N]
```

创建带有幻灯片文件名作为标签的 `thumbnails.jpg`。默认 3 列，每网格最多 12 个。

**仅用于模板分析**（选择布局）。对于视觉 QA，使用 `soffice` + `pdftoppm` 创建全分辨率单个幻灯片图像——参见 SKILL.md。

---

## 幻灯片操作

幻灯片顺序在 `ppt/presentation.xml` → `<p:sldIdLst>` 中。

**重新排序**：重新排列 `<p:sldId>` 元素。

**删除**：删除 `<p:sldId>`，然后运行 `clean.py`。

**添加**：使用 `add_slide.py`。永远不要手动复制幻灯片文件——脚本处理手动复制遗漏的备注引用、Content_Types.xml 和关系 ID。

---

## 编辑内容

**子代理**：如果可用，在此处使用它们（完成步骤 4 后）。每张幻灯片都是一个单独的 XML 文件，因此子代理可以并行编辑。在您对子代理的提示中，包括：

- 要编辑的幻灯片文件路径
- **"对所有更改使用 Edit 工具"**
- 下面的格式规则和常见陷阱

对于每张幻灯片：

1. 读取幻灯片的 XML
2. 识别所有占位符内容——文本、图像、图表、图标、说明
3. 将每个占位符替换为最终内容

**使用 Edit 工具，而不是 sed 或 Python 脚本。** Edit 工具强制指定要替换什么以及在哪里，从而产生更好的可靠性。

### 格式规则

- **将所有标题、副标题和内联标签加粗**：在 `<a:rPr>` 上使用 `b="1"`。这包括：
  - 幻灯片标题
  - 幻灯片内的章节标题
  - 内联标签，如（例如："状态："、"描述："）在行的开头
- **永远不要使用 unicode 项目符号（•）**：使用带有 `<a:buChar>` 或 `<a:buAutoNum>` 的适当列表格式
- **项目符号一致性**：让项目符号从布局继承。仅指定 `<a:buChar>` 或 `<a:buNone>`。

---

## 常见陷阱

### 模板适配

当源内容的项目比模板少时：

- **完全删除多余的元素**（图像、形状、文本框），而不仅仅是清除文本
- 清除文本内容后检查孤立的视觉效果
- 运行视觉 QA 以捕获不匹配的计数

当用不同长度的内容替换文本时：

- **较短的替换**：通常安全
- **较长的替换**：可能会溢出或意外换行
- 文本更改后使用视觉 QA 进行测试
- 考虑截断或拆分内容以适应模板的设计约束

**模板槽位 ≠ 源项目**：如果模板有 4 个团队成员但源有 3 个用户，则删除第 4 个成员的整个组（图像 + 文本框），而不仅仅是文本。

### 多项内容

如果源有多个项目（编号列表、多个章节），则为每个项目创建单独的 `<a:p>` 元素——**永远不要连接成一个字符串**。

**❌ 错误**——一个段落中的所有项目：

```xml
<a:p>
  <a:r><a:rPr .../><a:t>步骤 1：做第一件事。步骤 2：做第二件事。</a:t></a:r>
</a:p>
```

**✅ 正确**——带有粗体标题的单独段落：

```xml
<a:p>
  <a:pPr algn="l"><a:lnSpc><a:spcPts val="3919"/></a:lnSpc></a:pPr>
  <a:r><a:rPr lang="en-US" sz="2799" b="1" .../><a:t>步骤 1</a:t></a:r>
</a:p>
<a:p>
  <a:pPr algn="l"><a:lnSpc><a:spcPts val="3919"/></a:lnSpc></a:pPr>
  <a:r><a:rPr lang="en-US" sz="2799" .../><a:t>做第一件事。</a:t></a:r>
</a:p>
<a:p>
  <a:pPr algn="l"><a:lnSpc><a:spcPts val="3919"/></a:lnSpc></a:pPr>
  <a:r><a:rPr lang="en-US" sz="2799" b="1" .../><a:t>步骤 2</a:t></a:r>
</a:p>
<!-- 继续模式 -->
```

从原始段落复制 `<a:pPr>` 以保留行距。在标题上使用 `b="1"`。

### 智能引号

由 unpack/pack 自动处理。但 Edit 工具会将智能引号转换为 ASCII。

**添加带有引号的新文本时，使用 XML 实体：**

```xml
<a:t>the &#x201C;Agreement&#x201D;</a:t>
```

| 字符 | 名称     | Unicode | XML 实体   |
| ---- | -------- | ------- | ---------- |
| `"`  | 左双引号 | U+201C  | `&#x201C;` |
| `"`  | 右双引号 | U+201D  | `&#x201D;` |
| `'`  | 左单引号 | U+2018  | `&#x2018;` |
| `'`  | 右单引号 | U+2019  | `&#x2019;` |

### 其他

- **空白**：在带有前导/尾随空格的 `<a:t>` 上使用 `xml:space="preserve"`
- **XML 解析**：使用 `defusedxml.minidom`，而不是 `xml.etree.ElementTree`（损坏命名空间）
