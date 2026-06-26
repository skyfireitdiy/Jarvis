/*
 * 预期检测结果: 不应报告漏洞
 * 陷阱: 看起来像格式化字符串漏洞，但实际安全
 * 安全实践: 用户输入作为参数，不是格式字符串
 */
#include <stdio.h>
#include <string.h>

void safe_format_with_input(char *user_input) {
  char buffer[256];
  // 安全: user_input作为参数，不是格式字符串
  snprintf(buffer, sizeof(buffer), "Message: %s", user_input);
}

void safe_printf_pattern(char *msg) {
  // 安全: 固定格式字符串
  printf("Log: %s\n", msg);
}

void safe_syslog_pattern(char *msg) {
  // 安全: syslog使用固定格式
  syslog(LOG_ERR, "Error occurred: %s", msg);
}
