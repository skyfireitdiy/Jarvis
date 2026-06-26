/*
 * 预期检测结果: 应检测到整数溢出风险
 * 漏洞类型: 整数溢出导致缓冲区分配不足
 */
#include <stdlib.h>
#include <string.h>

void integer_overflow_vuln(int count, int size) {
  // 整数溢出风险: count * size 可能溢出
  int total = count * size;
  char *buffer = (char *)malloc(total); // 可能分配过小
  if (buffer) {
    memset(buffer, 0, total);
  }
}

void integer_overflow_vuln2(unsigned int len) {
  // 整数溢出: len + 1 可能回绕
  char *buf = (char *)malloc(len + 1);
  if (buf) {
    memcpy(buf, "data", len); // 可能越界写入
  }
}
