/*
 * 反例：有goto错误处理
 * 预期：不应该检测到 possible_null_deref
 */
void foo(char *p) {
  if (!p)
    goto error;
  *p = 'x'; // 安全：有goto防御
error:
  return;
}
