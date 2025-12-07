# JavaScript/TypeScript 测试规则

## ⚠️ 核心要求

**编写完成务必执行测试，直到修复完成为止！**

- 每次代码修改后，必须立即运行测试
- 如果测试失败，必须修复代码直到所有测试通过
- 不允许提交未通过测试的代码

## 测试框架

### Jest（推荐）

```bash
npm test                  # 运行所有测试
npm test -- --watch       # 监视模式
npm test -- file.test.js  # 运行特定文件
npm test -- --coverage    # 显示覆盖率
```

### Mocha + Chai

```bash
npm test                  # 运行所有测试
npx mocha test/**/*.js    # 运行特定目录
```

### Vitest（Vite 项目）

```bash
npm test                  # 运行所有测试
npm test -- --watch       # 监视模式
```

## 测试示例

### Jest

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

### TypeScript + Jest

```typescript
// test/calculator.test.ts
import { add, divide } from '../src/calculator';

describe('Calculator', () => {
  it('adds two numbers', () => {
    expect(add(2, 3)).toBe(5);
  });
});
```

## 检查清单

- [ ] **编写完成后立即运行测试**
- [ ] **所有测试通过后才提交代码**
- [ ] **测试失败时，修复代码直到通过**
- [ ] 测试覆盖正常、边界和异常情况
- [ ] 使用描述性的测试名称
