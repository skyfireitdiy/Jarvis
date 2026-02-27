---
description: 规则文件通用规范
---

# Jarvis 内置规则列表

本目录包含以下分类的规则文件，每个分类对应一个子目录。

> **注意**：本文档仅列出通用规则索引。特定领域的规则（如转译规则、语言特定规则、UI设计规则等）仍然存在于对应目录中，可通过 `load_rule` 工具直接加载使用。

## 架构设计 (architecture_design/)

- [SOLID 设计原则]({{ rule_file_dir }}/architecture_design/solid.md) - 面向对象设计的五大原则，指导如何设计可维护、可扩展的软件
- [整洁架构]({{ rule_file_dir }}/architecture_design/clean_architecture.md) - 分层架构设计方法，解耦业务逻辑与框架
- [整洁代码]({{ rule_file_dir }}/architecture_design/clean_code.md) - 代码编写规范和最佳实践，提升代码可读性
- [反向工程规则]({{ rule_file_dir }}/architecture_design/reverse_engineering.md) - 从现有代码推导设计意图和架构
- [架构图生成规则]({{ rule_file_dir }}/architecture_design/architecture-diagram-generation.md) - 自动生成系统架构图和组件关系图

## 开发流程 (development_workflow/)

- [Spec 驱动开发 (SDD)]({{ rule_file_dir }}/development_workflow/sdd.md) - 先编写规范再实现代码的开发流程，确保需求明确
- [测试驱动开发 (TDD)]({{ rule_file_dir }}/development_workflow/tdd.md) - 先编写测试再实现功能，提升代码质量
- [重构]({{ rule_file_dir }}/development_workflow/refactoring.md) - 代码重构方法和流程，改善代码结构

## 代码质量 (code_quality/)

- [代码审查]({{ rule_file_dir }}/code_quality/code_review.md) - 代码审查标准和流程，确保代码质量
- [文档编写]({{ rule_file_dir }}/code_quality/documentation.md) - 文档编写规范和最佳实践
- [重构检查专家]({{ rule_file_dir }}/code_quality/refactor-checker.md) - 代码重构检查和评估工具

## 安全规范 (security/)

- [安全编码]({{ rule_file_dir }}/security/security.md) - 安全编码规范和最佳实践
- [安全漏洞分析规则]({{ rule_file_dir }}/security/vulnerability-analysis.md) - 安全漏洞分析方法和技术

## 开发工具 (development_tools/)

- [脚本生成规则]({{ rule_file_dir }}/development_tools/script-generation.md) - 脚本代码生成规范和模板
- [Jarvis 帮助规则]({{ rule_file_dir }}/development_tools/jarvis_help.md) - Jarvis 系统帮助信息和使用指南
- [LSP 工具使用规则]({{ rule_file_dir }}/development_tools/lsp_usage.md) - LSP (Language Server Protocol) 工具配置和使用
- [Jarvis Browser CLI (jb) 使用指南]({{ rule_file_dir }}/development_tools/jarvis_browser_cli.md) - 浏览器自动化命令行工具，支持 35+ 命令和守护进程模式
- [Jarvis Windows CLI (jw) 使用指南]({{ rule_file_dir }}/development_tools/jarvis_windows_cli.md) - Windows 桌面程序自动化命令行工具，支持启动/连接应用、点击、输入、截图、控件树等（仅 Windows）

## 性能优化 (performance/)

- [性能优化]({{ rule_file_dir }}/performance/performance.md) - 代码性能优化策略和最佳实践
