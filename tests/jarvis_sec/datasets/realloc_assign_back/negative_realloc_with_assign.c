/*
 * 反例：realloc赋回原指针
 * 预期：不应该检测到 realloc_assign_back
 */
#include <stdlib.h>
void foo() {
  char *p = malloc(100);
  p = realloc(p, 200); // 安全：赋回原指针
}
