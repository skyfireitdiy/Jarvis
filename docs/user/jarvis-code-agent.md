# Jarvis Code Agent - 代码助手

## 工具介绍
Jarvis Code Agent 是一个专注于代码操作和修改的智能助手，提供代码分析、重构和验证功能。它严格遵循代码修改协议，确保代码变更的安全性和准确性。

## 主要功能
- 代码分析和理解
- 安全代码重构
- 代码变更验证
- 自动生成代码补丁
- 代码变更文档生成

## 使用场景
- 代码库维护和优化
- 自动化代码重构
- 代码变更验证
- 代码审查辅助
- 代码文档生成

## 使用方法
```bash
jarvis-code-agent [options]
jca [options]  # 快捷方式
```

### 核心功能
- **代码分析**：使用 LSP 工具理解代码结构和依赖关系
- **代码修改**：生成安全、准确的代码补丁
- **变更验证**：确保代码变更的正确性和兼容性
- **文档生成**：自动生成详细的代码变更文档

## 技术实现
- 集成 LSP 工具进行代码分析
- 使用 git 进行版本控制
- 遵循严格的代码修改协议
- 支持多种代码操作工具

## 使用示例
1. 分析代码文件：
```bash
jarvis-code-agent --file example.py --language python
```

2. 安全重构代码：
```bash
jca --file example.py --language python --refactor
```

3. 验证代码变更：
```bash
jarvis-code-agent --file example.py --language python --verify
```

## 相关文档
- [代码修改协议](code-modification-protocol.md)
- [代码重构指南](code-refactoring.md)
- [代码验证最佳实践](code-verification.md)
