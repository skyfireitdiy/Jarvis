/*
 * 反例：C++ this指针
 * 预期：不应该检测到 possible_null_deref
 */
class Foo {
  int x;
  void bar() {
    this->x = 10; // 安全：this指针
  }
};
