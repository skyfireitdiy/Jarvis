/*
 * 反例：getenv返回值已检查
 * 预期：不应该检测到 getenv_unchecked
 */
#include <stdio.h>
#include <stdlib.h>
void foo() {
  char *home = getenv("HOME");
  if (home == NULL)
    return;
  printf("%s\n", home); // 安全：有检查
}
