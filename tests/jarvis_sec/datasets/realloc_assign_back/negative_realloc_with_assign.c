/*
 * 反例：realloc使用临时变量接收并检查NULL
 * 预期：不应该检测到 realloc_assign_back
 */
#include <stdlib.h>
void foo() {
  char *p = malloc(100);
  char *tmp = realloc(p, 200); // 安全：使用临时变量
  if (tmp != NULL) {
    p = tmp; // 只有成功时才赋值
  } else {
    // 失败时p仍然有效，可以继续使用或释放
    free(p);
  }
}
