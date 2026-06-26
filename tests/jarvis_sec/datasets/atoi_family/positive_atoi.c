/*
 * 正例：atoi使用
 * 预期：应该检测到 atoi_family
 */
#include <stdlib.h>
void foo(char *s) {
  int x = atoi(s); // 真实风险：无错误检查
}
