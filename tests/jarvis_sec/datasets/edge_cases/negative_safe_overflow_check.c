/*
 * 预期检测结果: 不应报告漏洞
 * 陷阱: 看起来像整数溢出，但实际有完整检查
 * 安全实践: 完整的整数溢出检查
 */
#include <limits.h>
#include <stdlib.h>

void complete_overflow_check(unsigned int count, unsigned int size) {
  // 安全: 完整的溢出检查
  if (count > 0 && size > 0 && count <= UINT_MAX / size) {
    unsigned int total = count * size;
    char *buf = (char *)malloc(total);
    if (buf)
      free(buf);
  }
}

void safe_signed_check(int len) {
  // 安全: 检查加法溢出
  if (len > 0 && len < INT_MAX - 100) {
    int size = len + 100;
    char *buf = (char *)malloc(size);
    if (buf)
      free(buf);
  }
}

void safe_multiplication(int a, int b) {
  // 安全: 检查乘法溢出
  if (a > 0 && b > 0 && a <= INT_MAX / b) {
    int result = a * b;
    char *buf = (char *)malloc(result);
    if (buf)
      free(buf);
  }
}
