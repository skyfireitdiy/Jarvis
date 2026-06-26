/*
 * 预期检测结果: 应检测到double free
 * 陷阱: 看起来有检查，但检查无效
 * 漏洞类型: 隐藏的double free
 */
#include <stdlib.h>
#include <string.h>

void hidden_double_free(char *input) {
  char *ptr = (char *)malloc(100);
  if (!ptr)
    return;

  strcpy(ptr, input);
  free(ptr);

  // 陷阱: 条件可能为真，导致double free
  if (strlen(input) > 0) {
    free(ptr); // double free!
  }
}

void double_free_via_alias() {
  char *a = (char *)malloc(50);
  char *b = a; // b是a的别名

  free(a);
  // 陷阱: 看起来free的是b，实际是同一块内存
  free(b); // double free!
}
