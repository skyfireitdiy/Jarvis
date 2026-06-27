#include <stdlib.h>

// 外部函数声明
extern void *allocate_memory();
extern void use_memory(void *ptr);
extern void free_memory(void *ptr);

// 主函数：演示跨文件UAF
int main() {
  void *ptr = allocate_memory(); // alloc.c
  use_memory(ptr);               // use.c - 第一次使用
  free_memory(ptr);              // free.c - 释放
  use_memory(ptr);               // use.c - UAF! 释放后使用
  return 0;
}
