/*
 * 正例：fopen返回值未检查
 * 预期：应该检测到 unchecked_io
 */
#include <stdio.h>
void foo() {
  FILE *fp = fopen("test.txt", "r");
  char buf[100];
  fread(buf, 1, 100, fp); // 真实风险：未检查fopen返回值
}
