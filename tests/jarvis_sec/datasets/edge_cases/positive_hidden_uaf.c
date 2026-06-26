/*
 * 预期检测结果: 应检测到UAF漏洞
 * 陷阱: 看起来有NULL检查，但检查在free之前，不影响后续使用
 * 漏洞类型: 隐藏的释放后使用
 */
#include <stdlib.h>
#include <string.h>

void hidden_uaf_vuln(char *input) {
  char *buffer = (char *)malloc(100);
  if (buffer == NULL)
    return; // 看起来安全

  strcpy(buffer, input);
  free(buffer);

  // 陷阱: 这里没有置NULL，后续代码可能误用
  if (buffer != NULL) {       // 这个检查永远为真！
    printf("Buffer freed\n"); // buffer仍指向已释放内存
  }

  // 更隐蔽: 通过另一个变量
  char *ptr = buffer; // ptr现在也指向已释放内存
  if (ptr != NULL) {
    strcpy(ptr, "test"); // UAF!
  }
}
