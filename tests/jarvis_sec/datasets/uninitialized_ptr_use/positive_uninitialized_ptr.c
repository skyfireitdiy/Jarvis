/*
 * 正例：未初始化指针使用
 * 预期：应该检测到 uninitialized_ptr_use
 */
void foo() {
  char *p;
  *p = 'x'; // 真实风险：未初始化
}
