/*
 * 预期检测结果: 不应报告漏洞
 * 陷阱: 看起来像double free，但实际安全
 * 安全实践: 使用标志位或NULL检查防止double free
 */
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

void safe_free_with_flag() {
  char *ptr = (char *)malloc(100);
  bool freed = false;

  if (ptr) {
    // 使用ptr...
    free(ptr);
    ptr = NULL;
    freed = true;
  }

  // 安全: 检查标志位
  if (!freed && ptr) {
    free(ptr);
    ptr = NULL;
  }
}

void safe_conditional_free(int condition) {
  char *ptr = (char *)malloc(100);
  if (!ptr)
    return;

  if (condition) {
    free(ptr);
    ptr = NULL;
  }

  // 安全: ptr可能已被置NULL
  if (ptr) {
    free(ptr);
    ptr = NULL;
  }
}
