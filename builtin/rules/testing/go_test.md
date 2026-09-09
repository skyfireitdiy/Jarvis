---
name: go_test
description: 当需要为Go项目编写测试或配置测试框架时触发。每当用户提及"Go测试"、"表格驱动测试"、"go test"时触发。不触发：非Go项目测试；代码审查；性能优化。
---

# Go 测试规范

## 要点

**写完务必立刻运行测试，直到全部通过！**

### 执行要点

- **必须**：每改码后，即行测试
- **必须**：若测试败，修码至全过
- **禁止**：提交未过的码
- **禁止**：于测试未过的际续行开发

### 流程

1. 写或改码
2. **即**行测试
3. 若败，修的
4. 复步 2-3，至全过
5. 全过的后，方得提交

## 必须用的测架

### 标准库 testing（无需安装）

**运行命令：**

```bash
go test                 # 行当前包之全测
go test ./...           # 行全包之测
go test -v              # 详出
go test -run TestFunc   # 行特测函数
go test -cover          # 示覆盖率
go test -coverprofile=coverage.out # 生覆盖率文件
```

## 必须写的测例

```go
// calculator_test.go
package calculator

import "testing"

func TestAdd(t *testing.T) {
    result := Add(2, 3)
    if result != 5 {
        t.Errorf("Add(2, 3) = %d; want 5", result)
    }
}

func TestDivideByZero(t *testing.T) {
    _, err := Divide(10, 0)
    if err == nil {
        t.Error("Divide(10, 0) should return error")
    }
}

// 表驱动测试（荐）
func TestAddTable(t *testing.T) {
    tests := []struct {
        a, b, want int
    }{
        {2, 3, 5},
        {0, 0, 0},
        {-1, 1, 0},
    }
    for _, tt := range tests {
        if got := Add(tt.a, tt.b); got != tt.want {
            t.Errorf("Add(%d, %d) = %d; want %d", tt.a, tt.b, got, tt.want)
        }
    }
}
```

## 测试文件规

### 文件命名

- **必须**：测试文件以 `_test.go` 结尾
- **必须**：测试文件与被测文件同包

### 函数命名

- **必须**：测试函数以 `Test` 开头
- **必须**：测试函数接受 `*testing.T` 参数

## 测试行检单

提交码前，必须确：

- [ ] **写完立刻运行测试**
- [ ] **所有测试都通过**
- [ ] **若失败，就修复到通过**
- [ ] 测试文件以 `_test.go` 结尾
- [ ] 测试函数以 `Test` 开头
- [ ] 用表驱动测试覆多场景（如适用）
- [ ] 测覆正常、边界与异常的情
