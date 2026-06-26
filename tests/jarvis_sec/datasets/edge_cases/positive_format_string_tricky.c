/*
 * 预期检测结果: 应检测到格式化字符串漏洞
 * 陷阱: 看起来有格式字符串，但用户输入仍在格式位置
 * 漏洞类型: 隐藏的格式化字符串漏洞
 */
#include <stdio.h>
#include <string.h>

void tricky_format_string(char *user_input) {
  char buffer[256];
  // 陷阱: 看起来有"%s"，但user_input在格式字符串位置
  snprintf(buffer, sizeof(buffer), user_input); // 危险!
}

void format_with_concat(char *user_input) {
  char fmt[100];
  // 陷阱: 构造的格式字符串包含用户输入
  snprintf(fmt, sizeof(fmt), "Error: %s", user_input);
  printf(fmt); // 如果user_input包含%格式符，危险!
}

void syslog_format_vuln(char *msg) {
  // 陷阱: syslog的格式字符串参数
  syslog(LOG_ERR, msg); // 危险!
}
