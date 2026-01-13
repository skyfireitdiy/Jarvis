# 规则列表

## 架构设计

### SOLID 设计原则

用于指导面向对象设计的五大原则。（{{ rule_file_dir }}/solid.md）

### 整洁架构

用于指导构建可维护、可测试的架构。（{{ rule_file_dir }}/clean_architecture.md）

### 整洁代码

用于强调可读性优先和单一职责原则。（{{ rule_file_dir }}/clean_code.md）

### 代码反向设计专家

能够阅读给定代码并输出详细的设计方案，帮助开发者理解代码结构并实现功能对齐的开发。（{{ rule_file_dir }}/code-reverse-design-expert.md）

### 架构图生成器

能够阅读代码，抽象关键组件，并使用Graphviz按要求输出逻辑视图、实现
视图、进程视图、部署视图和用例视图中的一个或多个架构图，并最终渲染成
PNG图片。（{{ rule_file_dir }}/architecture-diagram-generator.md）

## 开发流程

### C2Rust 转译

用于指导 C/C++ 到 Rust 的代码转译过程，确保转译质量、功能一致性和类型安全。（{{ rule_file_dir }}/c2rust_transpiler.md）

### Spec 驱动开发 (SDD)

用于定义 Spec-实现-验证循环。（{{ rule_file_dir }}/sdd.md）

### 测试驱动开发 (TDD)

用于定义红-绿-重构循环。（{{ rule_file_dir }}/tdd.md）

### 重构

用于定义小步快跑和保持功能不变原则。（{{ rule_file_dir }}/refactoring.md）

## 代码质量

### 代码审查

用于提供功能正确性、代码质量的审查标准。（{{ rule_file_dir }}/code_review.md）

### 文档编写

用于定义清晰性和完整性原则。（{{ rule_file_dir }}/documentation.md）

### 重构检查专家

重构检查专家，负责检查重构后的代码逻辑是否与原代码完全一致。（{{ rule_file_dir }}/refactor-checker.md）

## 安全规范

### 安全编码

用于定义输入验证和最小权限原则。（{{ rule_file_dir }}/security.md）

### 安全漏洞分析师

逻辑/安全漏洞查找专家，接受用户给出的代码目录、文件，分析代码功能，如果分析其中的逻辑和安全漏洞。（{{ rule_file_dir }}/security-vulnerability-analyst.md）

## 开发工具

### 脚本生成专家

脚本生成专家，负责根据需求生成各种类型的脚本。（{{ rule_file_dir }}/script-generator.md）

## 部署规范

### 开源部署专家

开源部署专家，负责将开源项目部署到目标环境中。（{{ rule_file_dir }}/opensource-deployment-expert.md）

## 性能优化指南

### 性能优化

用于指导使用性能分析工具识别和优化瓶颈。（{{ rule_file_dir }}/performance.md）

### Rust 性能优化

用于基于 Perf 分析的 Rust 性能优化。（{{ rule_file_dir }}/rust_performance.md）

## UI 设计

### Zen-iOS Hybrid 暗色主题

用于定义暗色主题的视觉基调。（{{ rule_file_dir }}/ios-dark-theme.md）

### Zen-iOS Hybrid 亮色主题

用于定义亮色主题的视觉基调。（{{ rule_file_dir }}/ios-light-theme.md）

## 工具配置

### 新增规则规范

用于指导如何创建新的规则文件，包括文件位置、命名规范、格式要求和 Jinja2 变量使用。（{{ rule_file_dir }}/add_rule.md）

### 忽略所有告警

用于快速验证模式，仅用于原型验证。（{{ rule_file_dir }}/ignore_all_alerts.md）

## 测试规范

### C/C++ 测试

用于指导 C/C++ 代码的测试框架使用和测试执行。（{{ rule_file_dir }}/../test_rules/cpp_test.md）

### Go 测试

用于指导 Go 代码的测试框架使用和测试执行。（{{ rule_file_dir }}/../test_rules/go_test.md）

### JS/TS 测试

用于指导 JavaScript/TypeScript 代码的测试框架使用和测试执行。（{{ rule_file_dir }}/../test_rules/javascript_test.md）

### Java 测试

用于指导 Java 代码的测试框架使用和测试执行。（{{ rule_file_dir }}/../test_rules/java_test.md）

### PHP 测试

用于指导 PHP 代码的测试框架使用和测试执行。（{{ rule_file_dir }}/../test_rules/php_test.md）

### Python 测试

用于指导 Python 代码的测试框架使用和测试执行。（{{ rule_file_dir }}/../test_rules/python_test.md）

### Ruby 测试

用于指导 Ruby 代码的测试框架使用和测试执行。（{{ rule_file_dir }}/../test_rules/ruby_test.md）

### Rust 测试

用于指导 Rust 代码的测试框架使用和测试执行。（{{ rule_file_dir }}/../test_rules/rust_test.md)
