/*
 * 反例：有if语句检查
 * 预期：不应该检测到 possible_null_deref
 */
void foo(char *p) {
  if (p != NULL) {
    *p = 'x'; // 安全：有检查
  }
}
