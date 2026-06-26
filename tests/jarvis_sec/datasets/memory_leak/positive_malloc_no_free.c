// 内存泄漏正例：malloc后未释放
// 应该检测到：动态分配的内存未释放

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

char *create_string(const char *input) {
  // 分配内存
  char *buffer = (char *)malloc(256);
  if (buffer == NULL) {
    return NULL;
  }

  // 使用内存
  strncpy(buffer, input, 255);
  buffer[255] = '\0';

  // 内存泄漏：函数返回前未释放buffer
  // 但返回了指针，调用者需要负责释放
  return buffer;
}

int main(int argc, char *argv[]) {
  char *str1 = create_string("Hello");
  char *str2 = create_string("World");

  printf("%s %s\n", str1, str2);

  // 内存泄漏：str1和str2未释放
  // 应该检测到内存泄漏

  return 0;
}
