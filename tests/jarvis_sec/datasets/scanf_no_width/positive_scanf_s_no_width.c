/*
 * 正例：scanf %s无宽度
 * 预期：应该检测到 scanf_no_width
 */
#include <stdio.h>
void foo() {
  char buf[100];
  scanf("%s", buf); // 真实风险：缓冲区溢出
}
