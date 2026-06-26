/*
 * 正例：sprintf使用
 * 预期：应该检测到 unsafe_api (sprintf)
 */
#include <stdio.h>
void foo(char *buf) {
  sprintf(buf, "%s", "hello"); // 真实风险：可能缓冲区溢出
}
