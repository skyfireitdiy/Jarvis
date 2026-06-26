/*
 * 正例：strncpy未添加终止符
 * 预期：应该检测到 strncpy_no_nullterm
 */
#include <string.h>
void foo(char *dst, const char *src, size_t n) {
  strncpy(dst, src, n); // 真实风险：未添加终止符
}
