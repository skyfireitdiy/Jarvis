/*
 * 正例：reinterpret_cast使用
 * 预期：应该检测到 reinterpret_cast_unsafe
 */
void foo() {
  int x = 42;
  char *p = reinterpret_cast<char *>(&x); // 真实风险：类型转换
}
