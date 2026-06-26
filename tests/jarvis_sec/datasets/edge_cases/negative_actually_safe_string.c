/*
 * 预期检测结果: 不应报告漏洞
 * 陷阱: 看起来危险，但实际安全
 * 安全实践: 正确使用字符串函数
 */
#include <stdlib.h>
#include <string.h>

void actually_safe_strncpy(char *input) {
  char buffer[100];
  // 安全: 正确使用sizeof(buffer) - 1
  strncpy(buffer, input, sizeof(buffer) - 1);
  buffer[sizeof(buffer) - 1] = '\0'; // 确保终止
}

void safe_memcpy_with_check(char *src, size_t len) {
  char *dst = (char *)malloc(100);
  // 安全: 检查长度
  if (dst && len < 100) {
    memcpy(dst, src, len);
    dst[len] = '\0';
    free(dst);
  } else if (dst) {
    free(dst);
  }
}

void safe_snprintf(char *input) {
  char buffer[256];
  // 安全: 使用snprintf并指定正确大小
  snprintf(buffer, sizeof(buffer), "Input: %s", input);
}
