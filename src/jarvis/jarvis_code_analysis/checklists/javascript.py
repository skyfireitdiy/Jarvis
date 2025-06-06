# -*- coding: utf-8 -*-
"""
JavaScript/TypeScript language-specific code review checklist.
"""

CHECKLIST = """
## JavaScript/TypeScript 代码审查检查清单

### 代码风格和格式
- [ ] 是否遵循一致的命名约定 (camelCase、PascalCase)
- [ ] 是否使用 ESLint/TSLint 进行代码规范检查
- [ ] 缩进和格式是否一致
- [ ] 是否避免了过长的函数和过深的嵌套

### 类型安全 (TypeScript)
- [ ] 是否使用了适当的类型注解
- [ ] 是否避免了过度使用 any 类型
- [ ] 是否正确使用接口和类型别名
- [ ] 泛型使用是否合理
- [ ] 是否正确处理可能为 null/undefined 的值

### 异步编程
- [ ] Promise 异常是否被正确捕获和处理
- [ ] async/await 是否使用得当
- [ ] 是否避免了回调地狱
- [ ] 是否正确处理异步操作的竞态条件
- [ ] 是否合理使用 Promise.all/Promise.race

### 性能优化
- [ ] 是否避免了不必要的重新渲染
- [ ] 是否避免了内存泄漏 (闭包、事件监听器等)
- [ ] 是否适当使用了记忆化和缓存
- [ ] 循环和数据处理是否高效
- [ ] 是否避免了过度的DOM操作

### 安全性
- [ ] 是否防范了 XSS 攻击
- [ ] 是否防范了 CSRF 攻击
- [ ] 敏感数据是否安全处理
- [ ] 是否正确验证用户输入
- [ ] 是否避免使用 eval 和不安全的 DOM API

### 浏览器兼容性
- [ ] 是否考虑了目标浏览器的支持程度
- [ ] 是否使用了适当的垫片 (polyfills)
- [ ] 是否测试了不同浏览器下的表现

### 模块化和依赖管理
- [ ] 模块划分是否合理
- [ ] 是否避免了循环依赖
- [ ] 依赖版本是否固定
- [ ] 第三方库使用是否恰当
- [ ] 是否避免了过度依赖

### 测试
- [ ] 是否有单元测试覆盖核心功能
- [ ] 是否测试了组件渲染和交互
- [ ] 测试用例是否覆盖边界条件
- [ ] 是否有集成测试和端到端测试

### 可访问性 (对于前端代码)
- [ ] 是否遵循 ARIA 最佳实践
- [ ] 是否使用语义化 HTML
- [ ] 是否支持键盘导航
- [ ] 颜色对比度是否符合标准
- [ ] 是否兼容屏幕阅读器

### 可维护性
- [ ] 代码结构是否清晰
- [ ] 是否有充分的注释和文档
- [ ] 复杂逻辑是否抽象成可测试的函数
- [ ] 是否遵循 DRY 原则
- [ ] 状态管理是否合理
"""
