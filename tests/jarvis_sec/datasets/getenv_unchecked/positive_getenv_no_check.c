/*
 * 正例：getenv返回值未检查
 * 预期：应该检测到 getenv_unchecked
 */
#include <stdio.h>
#include <stdlib.h>
void foo() {
  char *home = getenv("HOME");
  printf("%s\n", home); // 真实风险：未检查返回值
}
