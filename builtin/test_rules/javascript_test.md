# JavaScript/TypeScript 测试规则

## ⚠️ 你必须遵守的核心要求

**编写完成务必执行测试，直到修复完成为止！**

### 执行要求

- **必须**：每次代码修改后，立即运行测试
- **必须**：如果测试失败，修复代码直到所有测试通过
- **禁止**：提交未通过测试的代码
- **禁止**：在测试未通过的情况下继续开发

### 工作流程

1. 编写或修改代码
2. **立即**运行测试
3. 如果测试失败，修复代码
4. 重复步骤 2-3，直到所有测试通过
5. 确认所有测试通过后，才能提交代码

## 你必须使用的测试框架

### Jest（推荐使用）

**安装命令：**

```bash
npm install --save-dev jest
```

**运行命令：**

```bash
npm test                  # 运行所有测试
npm test -- --watch       # 监视模式
npm test -- file.test.js  # 运行特定文件
npm test -- --coverage    # 显示覆盖率
```

### Mocha + Chai

**安装命令：**

```bash
npm install --save-dev mocha chai
```

**运行命令：**

```bash
npm test                  # 运行所有测试
npx mocha test/**/*.js    # 运行特定目录
```

### Vitest（Vite 项目推荐）

**安装命令：**

```bash
npm install --save-dev vitest
```

**运行命令：**

```bash
npm test                  # 运行所有测试
npm test -- --watch       # 监视模式
```

## 你必须编写的测试示例

### Jest 测试格式

```javascript
// test/calculator.test.js
const { add, divide } = require('../src/calculator');

describe('Calculator', () => {
  test('adds two numbers', () => {
    expect(add(2, 3)).toBe(5);
  });

  test('throws error on divide by zero', () => {
    expect(() => divide(10, 0)).toThrow('Division by zero');
  });
});
```

### TypeScript + Jest 测试格式

```typescript
// test/calculator.test.ts
import { add, divide } from '../src/calculator';

describe('Calculator', () => {
  it('adds two numbers', () => {
    expect(add(2, 3)).toBe(5);
  });
});
```

## 测试执行检查清单

在提交代码前，你必须确认：

- [ ] **编写完成后立即运行了测试**
- [ ] **所有测试都通过了**
- [ ] **如果测试失败，已修复代码直到通过**
- [ ] 测试覆盖了正常情况
- [ ] 测试覆盖了边界情况
- [ ] 测试覆盖了异常情况
- [ ] 使用了描述性的测试名称
