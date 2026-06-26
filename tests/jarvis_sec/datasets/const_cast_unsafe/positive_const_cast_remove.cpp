/*
 * 正例：const_cast移除const
 * 预期：应该检测到 const_cast_unsafe
 */
void foo(const int *p) {
  int *q = const_cast<int *>(p);
  *q = 100; // 真实风险：移除const
}
