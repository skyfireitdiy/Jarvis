/*
 * 正例：VLA使用
 * 预期：应该检测到 vla_usage
 */
void foo(int n) {
  char buf[n]; // 真实风险：VLA
}
