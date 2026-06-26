/*
 * 正例：strcpy使用
 * 预期：应该检测到 unsafe_api (strcpy)
 */
#include <string.h>
void foo(char *dst, const char *src) {
  strcpy(dst, src); // 真实风险：可能缓冲区溢出
}
