/*
 * 预期检测结果: 应检测到整数溢出
 * 陷阱: 看起来有检查，但检查不完整
 * 漏洞类型: 不完整的整数溢出检查
 */
#include <limits.h>
#include <stdlib.h>

void incomplete_overflow_check(unsigned int count, unsigned int size) {
  // 陷阱: 只检查了count，没检查乘法溢出
  if (count > 0 && size > 0) {         // 看起来有检查
    unsigned int total = count * size; // 仍可能溢出!
    char *buf = (char *)malloc(total);
    if (buf)
      free(buf);
  }
}

void signed_overflow_trap(int len) {
  // 陷阱: len为负数时，len + 100可能变成很小的数
  if (len > 0) {          // 看起来检查了
    int size = len + 100; // 如果len接近INT_MAX，会溢出
    char *buf = (char *)malloc(size);
    if (buf)
      free(buf);
  }
}

void multiplication_overflow(int a, int b) {
  // 陷阱: 看起来安全，但a*b可能溢出
  if (a > 0 && b > 0) {
    int result = a * b; // 可能溢出
    char *buf = (char *)malloc(result);
    if (buf)
      free(buf);
  }
}
