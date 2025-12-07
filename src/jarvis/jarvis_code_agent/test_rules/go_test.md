# Go 测试规则

## ⚠️ 核心要求

**编写完成务必执行测试，直到修复完成为止！**

- 每次代码修改后，必须立即运行测试
- 如果测试失败，必须修复代码直到所有测试通过
- 不允许提交未通过测试的代码

## 测试框架

### 标准库 testing

```bash
go test                 # 运行当前包的所有测试
go test ./...           # 运行所有包的测试
go test -v              # 详细输出
go test -run TestFunc   # 运行特定测试函数
go test -cover          # 显示覆盖率
go test -coverprofile=coverage.out # 生成覆盖率文件
```

## 测试示例

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

// 表驱动测试
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

## 检查清单

- [ ] **编写完成后立即运行测试**
- [ ] **所有测试通过后才提交代码**
- [ ] **测试失败时，修复代码直到通过**
- [ ] 测试文件以 `_test.go` 结尾
- [ ] 测试函数以 `Test` 开头
- [ ] 使用表驱动测试覆盖多个场景
