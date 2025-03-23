# 🚀 Jarvis Git Commit - 智能提交助手

<div align="center">
  <img src="../images/jarvis-git-commit.png" alt="Git Commit" width="250" style="margin-bottom: 20px"/>
  
  *提升您的Git提交体验*
  
  ![Version](https://img.shields.io/badge/version-0.1.x-blue)
  ![Git](https://img.shields.io/badge/git-required-orange)
</div>

## ✨ 魔法简介
Jarvis Git Commit (JGC) 是一个革命性工具，它使用AI技术自动分析您的代码变更，生成专业、清晰且符合规范的提交信息。告别无意义的提交描述和格式不一致的问题，提升团队协作效率和代码库的可维护性。

## 🌟 闪耀特性
- **智能变更分析** - 自动识别代码中的功能添加、修复或改进
- **结构化提交** - 生成符合Conventional Commits标准的提交信息
- **多语言支持** - 灵活切换中英文等多种语言的提交信息
- **自定义仓库支持** - 可指定任意Git仓库路径进行操作
- **团队风格统一** - 保持团队提交信息的一致性和专业性
- **提交前检查** - 确保提交信息质量，避免低质量提交

## 💫 使用方法
```bash
# 完整命令
jarvis-git-commit [options]

# 简写命令
jgc [options]
```

### 📋 可选参数
- `--lang <语言>` - 生成的提交信息语言（默认：Chinese）
- `--root-dir <目录>` - 指定Git仓库根目录（默认：当前目录）

5. **确认和执行**
   系统执行`git commit`操作，使用生成的信息完成提交。

## 💎 使用场景
- **日常开发提交** - 让每次提交都有清晰专业的描述
- **功能完成时** - 自动总结新功能的核心变更
- **Bug修复后** - 精确描述修复了什么问题及解决方法
- **重构代码时** - 清晰说明重构的目的和影响范围
- **团队协作中** - 统一提交信息风格，提高协作效率
- **开源项目贡献** - 符合项目规范的专业提交信息

## 🌈 提交信息结构
JGC生成的提交信息遵循结构化格式：

```
<类型>(<范围>): <简短描述>

<详细描述>

<问题引用>
```

### 常见类型标签
| 标签 | 用途 |
|------|------|
| feat | 新功能 |
| fix | 修复bug |
| docs | 文档变更 |
| style | 代码风格/格式修改 |
| refactor | 代码重构 |
| perf | 性能优化 |
| test | 添加测试 |
| build | 构建系统变更 |
| ci | CI配置变更 |

<div align="center">
  <p><i>Jarvis Git Commit - 让每一次提交都专业而有意义</i></p>
</div> 