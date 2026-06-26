/*
 * 反例：fopen返回值已检查
 * 预期：不应该检测到 unchecked_io
 */
#include <stdio.h>
void foo() {
  FILE *fp = fopen("test.txt", "r");
  if (fp == NULL)
    return;
  char buf[100];
  size_t n = fread(buf, 1, 100, fp); // 安全：有检查
  if (n < 100) {
    // 处理读取不完整的情况
  }
}
