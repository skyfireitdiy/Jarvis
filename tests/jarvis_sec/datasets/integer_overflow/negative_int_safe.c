/*
 * 预期检测结果: 不应报告漏洞
 * 安全实践: 使用安全的整数运算检查
 */
#include <limits.h>
#include <stdlib.h>

void safe_integer_alloc(int count, int size) {
  // 安全: 检查整数溢出
  if (count > 0 && size > 0 && count <= INT_MAX / size) {
    int total = count * size;
    char *buffer = (char *)malloc(total);
    if (buffer) {
      memset(buffer, 0, total);
      free(buffer);
    }
  }
}
