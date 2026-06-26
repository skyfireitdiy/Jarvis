// Double Free反例：正确释放一次
// 不应该检测到：内存只释放一次

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char *argv[]) {
  // 分配内存
  char *buffer = (char *)malloc(256);
  if (buffer == NULL) {
    return 1;
  }

  // 使用内存
  strcpy(buffer, "Hello, World!");
  printf("Buffer: %s\n", buffer);

  // 正确：只释放一次
  free(buffer);

  // 设置为NULL防止悬空指针
  buffer = NULL;

  return 0;
}
