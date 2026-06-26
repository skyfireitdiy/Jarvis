/*
 * 正例：vector访问无检查
 * 预期：应该检测到 vector_string_bounds_check
 */
#include <vector>
void foo() {
  std::vector<int> v;
  v[0] = 42; // 真实风险：无边界检查
}
