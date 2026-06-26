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
  fread(buf, 1, 100, fp); // 安全：有检查
}
