# Builtin Rules 入口

本目录包含 JARVIS 内置规则的所有规则文件。

## 规则列表

1. SOLID 设计原则规则，用于指导面向对象设计的五大原则。（{{ rule_file_dir }}/solid.md）
2. 整洁架构规则，用于指导构建可维护、可测试的架构。（{{ rule_file_dir }}/clean_architecture.md）
3. 整洁代码规则，用于强调可读性优先和单一职责原则。（{{ rule_file_dir }}/clean_code.md）
4. 代码审查规则，用于提供功能正确性、代码质量的审查标准。（{{ rule_file_dir }}/code_review.md）
5. 文档编写规则，用于定义清晰性和完整性原则。（{{ rule_file_dir }}/documentation.md）
6. 规则生成指南，用于指导从项目实际代码中提炼开发规则。（{{ rule_file_dir }}/generate_rules.md）
7. 忽略所有告警规则，用于快速验证模式，仅用于原型验证。（{{ rule_file_dir }}/ignore_all_alerts.md）
8. Zen-iOS Hybrid 暗色主题设计指南，用于定义暗色主题的视觉基调。（{{ rule_file_dir }}/ios-dark-theme.md）
9. Zen-iOS Hybrid 前端设计风格指南，用于定义亮色主题的视觉基调。（{{ rule_file_dir }}/ios-light-theme.md）
10. 性能优化规则，用于指导使用性能分析工具识别和优化瓶颈。（{{ rule_file_dir }}/performance.md）
11. 重构规则，用于定义小步快跑和保持功能不变原则。（{{ rule_file_dir }}/refactoring.md）
12. Rust 性能优化规则，用于基于 Perf 分析的 Rust 性能优化。（{{ rule_file_dir }}/rust_performance.md）
13. Spec 驱动开发 (SDD) 规则，用于定义 Spec-实现-验证循环。（{{ rule_file_dir }}/sdd.md）
14. 安全编码规则，用于定义输入验证和最小权限原则。（{{ rule_file_dir }}/security.md）
15. 测试驱动开发 (TDD) 规则，用于定义红-绿-重构循环。（{{ rule_file_dir }}/tdd.md）

---

## 使用说明

### 如何使用规则

- **查看规则详情**: 点击上方路径查看具体规则内容
- **动态路径**: 所有路径使用 `{{ rule_file_dir }}` 变量动态生成
- **规则加载**: 详见 [规则系统最佳实践](../../docs/best_practices/rules_best_practices.md)

### 可用的 Jinja2 变量

- `{{ rule_file_dir }}`: 规则文件所在目录（动态生成）
- 其他可用变量：`{{ current_dir }}`, `{{ script_dir }}`, `{{ git_root_dir }}` 等

详细信息请参考 [规则占位符使用](../../docs/best_practices/rules_best_practices.md#-规则占位符的使用)
