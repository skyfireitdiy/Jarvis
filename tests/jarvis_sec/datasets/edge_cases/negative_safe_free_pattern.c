/*
 * 预期检测结果: 不应报告漏洞
 * 陷阱: 看起来像UAF，但实际是安全的
 * 安全实践: free后立即置NULL，后续检查有效
 */
#include <stdlib.h>
#include <string.h>

void safe_free_with_null() {
  char *buffer = (char *)malloc(100);
  if (buffer == NULL)
    return;

  strcpy(buffer, "data");
  free(buffer);
  buffer = NULL; // 关键: 立即置NULL

  // 安全: buffer为NULL，不会执行
  if (buffer != NULL) {
    printf("%s\n", buffer); // 不会执行
  }

  // 安全: strcpy检查NULL
  if (buffer) {
    strcpy(buffer, "test"); // 不会执行
  }
}

void safe_free_early_return() {
  char *ptr = (char *)malloc(50);
  if (!ptr)
    return;

  // 使用ptr
  memset(ptr, 0, 50);

  free(ptr);
  ptr = NULL;
  return; // 提前返回，后续代码不会执行

  // 死代码，不会执行
  strcpy(ptr, "dead");
}
