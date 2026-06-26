/*
 * 正例：重复free
 * 预期：应该检测到 double_free
 */
#include <stdlib.h>
void foo() {
  char *p = malloc(100);
  free(p);
  free(p); // 真实风险：double free
}
