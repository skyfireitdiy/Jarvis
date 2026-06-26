/*
 * 正例：get()结果被存储
 * 预期：应该检测到 smart_ptr_get_unsafe
 */
#include <memory>
void foo() {
  auto p = std::make_shared<int>(42);
  int *raw = p.get();
  *raw = 100; // 真实风险：裸指针存储
}
