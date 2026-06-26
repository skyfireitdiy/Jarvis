/*
 * 预期检测结果: 应检测到缓冲区溢出风险
 * 陷阱: 看起来使用了strncpy，但长度参数错误
 * 漏洞类型: 错误使用的"安全"函数
 */
#include <stdlib.h>
#include <string.h>

void strncpy_wrong_size(char *input) {
  char buffer[50];
  // 陷阱: sizeof(input)是指针大小，不是buffer大小!
  strncpy(buffer, input, sizeof(input)); // 只复制4或8字节
  buffer[sizeof(buffer) - 1] = '\0';
}

void strncpy_off_by_one(char *input) {
  char buffer[100];
  // 陷阱: 看起来安全，但如果input很长，可能截断但不终止
  strncpy(buffer, input, 100); // 可能不终止
                               // 没有手动添加终止符!
}

void memcpy_size_confusion(char *src, size_t len) {
  char *dst = (char *)malloc(50);
  // 陷阱: len可能大于50
  if (dst) {
    memcpy(dst, src, len); // 可能溢出!
    free(dst);
  }
}
