/*
 * 正例：free后使用
 * 预期：应该检测到 uaf_suspect
 */
#include <stdlib.h>
void foo() {
  char *p = malloc(100);
  free(p);
  p[0] = 'x'; // 真实风险：UAF
}
