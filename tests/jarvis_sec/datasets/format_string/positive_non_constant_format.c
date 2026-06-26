/*
 * 正例：非常量格式化字符串
 * 预期：应该检测到 format_string
 */
#include <stdio.h>
void foo(char *fmt) {
  printf(fmt); // 真实风险：格式化字符串漏洞
}
