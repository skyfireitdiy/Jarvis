/*
 * 正例：realloc未赋回原指针
 * 预期：应该检测到 realloc_assign_back
 */
#include <stdlib.h>
void foo() {
  char *p = malloc(100);
  realloc(p, 200); // 真实风险：未赋回
}
