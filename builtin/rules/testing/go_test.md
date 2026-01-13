# Go 测试规则

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

### 标准库 testing（无需安装）

**运行命令：**

```bash
go test                 # 运行当前包的所有测试
go test ./...           # 运行所有包的测试
go test -v              # 详细输出
go test -run TestFunc   # 运行特定测试函数
go test -cover          # 显示覆盖率
go test -coverprofile=coverage.out # 生成覆盖率文件
```

## 你必须编写的测试示例

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

// 表驱动测试（推荐使用）
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

## 测试文件规范

### 文件命名

- **必须**：测试文件以 `_test.go` 结尾
- **必须**：测试文件与被测试文件在同一包中

### 函数命名

- **必须**：测试函数以 `Test` 开头
- **必须**：测试函数接受 `*testing.T` 参数

## 测试执行检查清单

在提交代码前，你必须确认：

- [ ] **编写完成后立即运行了测试**
- [ ] **所有测试都通过了**
- [ ] **如果测试失败，已修复代码直到通过**
- [ ] 测试文件以 `_test.go` 结尾
- [ ] 测试函数以 `Test` 开头
- [ ] 使用表驱动测试覆盖多个场景（如适用）
- [ ] 测试覆盖了正常、边界和异常情况
