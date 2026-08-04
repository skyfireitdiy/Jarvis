---
name: add_builtin_rule
description: 当需要添加或管理内置规则时触发。每当用户提及"添加内置规则"、"创建内置规则"、"内置规则管理"、"builtin规则"时触发。不触发：添加项目规则（用add_rule规则）；修改规则内容；删除规则。
---

# 新增内置规则规范

## 规则简介

本规范用于指导如何在 Jarvis 系统中添加新之内置规则。内置规则是 Jarvis 系统自带之规则，适用于所有项目，存储在 `{{ jarvis_src_dir }}/builtin/rules/` 目录下。

## 工作流程

### 1. 定规则类型

- 定规则所属之类别（如 security、performance、testing 等）
- 检查是否已有同类规则
- 定规则之触发条件

### 2. 创建规则文件

- 在对应目录下创建 `.md` 文件
- 添加 frontmatter（name、description）
- 编规则正文

### 3. 规则内容要求

- 用精简文言文风格
- 保留 frontmatter 中 description 字段原文
- 保留代码示例与 markdown 结构
- 用"汝"代"你"，"吾"代"我"，"之"代"的"

### 4. 验证规则

- 检查 markdown 格式
- 验证 frontmatter 完整性
- 确认触发条件准确

## 文件结构

```text
builtin/rules/
  ├── security/
  │   └── security.md
  ├── performance/
  │   └── performance.md
  └── ...
```

## 检查清单

- [ ] 规则类别定
- [ ] 规则文件已创建
- [ ] frontmatter 完整
- [ ] 正文为文言文风格
- [ ] 代码示例保留
- [ ] markdown 格式正确
