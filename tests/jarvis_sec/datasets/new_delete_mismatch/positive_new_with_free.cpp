/*
 * 正例：new配free
 * 预期：应该检测到 new_delete_mismatch
 */
void foo() {
  int *p = new int(42);
  free(p); // 真实风险：new/delete不匹配
}
