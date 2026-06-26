/*
 * 反例：有return防御
 * 预期：不应该检测到 possible_null_deref
 */
void foo(char *p) {
  if (!p)
    return;
  *p = 'x'; // 安全：有return防御
}
