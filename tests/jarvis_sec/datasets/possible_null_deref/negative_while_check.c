/*
 * 反例：while循环条件检查
 * 预期：不应该检测到 possible_null_deref
 */
void foo(char *p) {
  while (p && *p) {
    p++; // 安全：while条件检查
  }
}
