/*
 * 反例：分配后有NULL检查再使用
 * 预期：不应该检测到 possible_null_deref
 */
#include <stdlib.h>
void foo() {
  char *p = malloc(100);
  if (p == NULL) return;
  p[0] = 'x'; // 安全：已检查NULL
}
