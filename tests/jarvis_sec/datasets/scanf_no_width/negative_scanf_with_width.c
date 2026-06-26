/*
 * 反例：scanf有宽度限制
 * 预期：不应该检测到 scanf_no_width
 */
#include <stdio.h>
void foo() {
  char buf[100];
  scanf("%99s", buf); // 安全：有宽度限制
}
