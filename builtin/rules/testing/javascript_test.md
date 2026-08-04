---
name: javascript_test
description: 当需要为JavaScript/TypeScript项目编写测试或配置测试框架时触发。每当用户提及"JavaScript测试"、"TypeScript测试"、"前端测试"、"Jest"、"Mocha"、"Vitest"时触发。不触发：非JS/TS项目测试；代码审查；性能优化。
---

# JavaScript/TypeScript 测试之规

## ⚠ 要

**写毕必行测试，至修毕乃止！**

### 行要

- **必**：每改码后，即行测试
- **必**：若测试败，修码至全过
- **禁**：提交未过之码
- **禁**：于测试未过之际续行开发

### 流程

1. 写或改码
2. **即**行测试
3. 若败，修之
4. 复步 2-3，至全过
5. 全过之后，方得提交

## 汝必用之测架

### Jest（荐）

**安装命令：**

```bash
npm install --save-dev jest
```

**运行命令：**

```bash
npm test                  # 行全测
npm test -- --watch       # 监视模
npm test -- file.test.js  # 行特文件
npm test -- --coverage    # 示覆盖率
```

### Mocha + Chai

**安装命令：**

```bash
npm install --save-dev mocha chai
```

**运行命令：**

```bash
npm test                  # 行全测
npx mocha test/**/*.js    # 行特目录
```

### Vitest（Vite 项目荐）

**安装命令：**

```bash
npm install --save-dev vitest
```

**运行命令：**

```bash
npm test                  # 行全测
npm test -- --watch       # 监视模
```

## 汝必写之测例

### Jest 测例

```javascript
// test/calculator.test.js
const { add, divide } = require("../src/calculator");

describe("Calculator", () => {
  test("adds two numbers", () => {
    expect(add(2, 3)).toBe(5);
  });

  test("throws error on divide by zero", () => {
    expect(() => divide(10, 0)).toThrow("Division by zero");
  });
});
```

### TypeScript + Jest 测例

```typescript
// test/calculator.test.ts
import { add, divide } from "../src/calculator";

describe("Calculator", () => {
  it("adds two numbers", () => {
    expect(add(2, 3)).toBe(5);
  });
});
```

## 测试行检单

提交码前，汝必确：

- [ ] **写毕即行测试矣**
- [ ] **全测皆过矣**
- [ ] **若败，已修至过矣**
- [ ] 测覆正常之情
- [ ] 测覆边界之情
- [ ] 测覆异常之情
- [ ] 用描述性之测试名
