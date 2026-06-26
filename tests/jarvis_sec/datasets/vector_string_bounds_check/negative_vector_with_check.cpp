/*
 * 反例：vector访问有检查
 * 预期：不应该检测到 vector_string_bounds_check
 */
#include <vector>
void foo() {
  std::vector<int> v;
  if (!v.empty()) {
    v[0] = 42; // 安全：有检查
  }
}
