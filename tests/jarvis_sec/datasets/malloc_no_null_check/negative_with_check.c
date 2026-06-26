/*
 * 反例：malloc有检查
 * 预期：不应该检测到 malloc_no_null_check
 */
#include <stdlib.h>
void foo() {
  char *p = malloc(100);
  if (p == NULL)
    return;
  p[0] = 'x'; // 安全：有检查
}
