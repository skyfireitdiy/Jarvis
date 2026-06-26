/*
 * 预期检测结果: 不应报告漏洞
 * 安全实践: 使用固定格式化字符串
 */
#include <stdio.h>

void safe_format_string(char *user_input) {
  // 安全: 使用固定格式化字符串
  printf("%s", user_input);
  fprintf(stderr, "Error: %s", user_input);
}

void safe_format_string2(char *user_input) {
  char buffer[256];
  // 安全: 使用固定格式化字符串
  snprintf(buffer, sizeof(buffer), "Message: %s", user_input);
}
