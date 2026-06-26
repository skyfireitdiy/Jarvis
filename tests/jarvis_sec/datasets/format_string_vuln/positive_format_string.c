/*
 * 预期检测结果: 应检测到格式化字符串漏洞
 * 漏洞类型: 用户输入作为格式化字符串
 */
#include <stdio.h>

void format_string_vuln(char *user_input) {
  // 格式化字符串漏洞: user_input 可能包含 %n %s 等
  printf(user_input);          // 危险!
  fprintf(stderr, user_input); // 危险!
}

void format_string_vuln2(char *user_input) {
  char buffer[256];
  // 格式化字符串漏洞
  sprintf(buffer, user_input); // 危险!
}
