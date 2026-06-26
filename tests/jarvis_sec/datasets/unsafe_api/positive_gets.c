/*
 * 正例：gets使用
 * 预期：应该检测到 unsafe_api (gets)
 */
#include <stdio.h>
void foo() {
  char buf[100];
  gets(buf); // 真实风险：极度危险
}
