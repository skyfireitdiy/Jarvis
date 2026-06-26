/*
 * 正例：shared_ptr循环引用
 * 预期：应该检测到 smart_ptr_cycle
 */
#include <memory>
class A {
  std::shared_ptr<A> next;
};
void foo() {
  auto a = std::make_shared<A>();
  a->next = a; // 真实风险：循环引用
}
