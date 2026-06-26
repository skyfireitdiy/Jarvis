/*
 * 预期检测结果: 应检测到 use_after_free 漏洞
 * 漏洞类型: 释放后使用 (UAF)
 * 描述: free后继续使用指针
 */
#include <stdlib.h>
#include <string.h>

void use_after_free_basic() {
  char *ptr = (char *)malloc(100);
  strcpy(ptr, "hello");
  free(ptr);
  // 释放后继续使用 - 严重漏洞
  printf("%s\n", ptr);  // UAF: 读取已释放内存
  strcpy(ptr, "world"); // UAF: 写入已释放内存
}
