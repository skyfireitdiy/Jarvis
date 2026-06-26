/*
 * 正例：malloc未检查NULL
 * 预期：应该检测到 malloc_no_null_check
 */
#include <stdlib.h>
void foo() {
  char *p = malloc(100);
  p[0] = 'x'; // 真实风险：未检查malloc返回值
}
