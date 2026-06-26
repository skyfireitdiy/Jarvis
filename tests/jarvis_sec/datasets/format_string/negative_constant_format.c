/*
 * 反例：常量格式化字符串
 * 预期：不应该检测到 format_string
 */
#include <stdio.h>
void foo(int x) {
  printf("%d\n", x); // 安全：常量格式
}
