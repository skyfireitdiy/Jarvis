/*
 * 预期检测结果: 不应报告漏洞
 * 安全实践: free后置NULL，后续使用前检查
 */
#include <stdlib.h>
#include <string.h>

void safe_free_pattern() {
  char *ptr = (char *)malloc(100);
  if (ptr == NULL)
    return;
  strcpy(ptr, "hello");
  free(ptr);
  ptr = NULL; // 安全: 置NULL

  // 安全: 使用前检查
  if (ptr != NULL) {
    printf("%s\n", ptr);
  }
}
