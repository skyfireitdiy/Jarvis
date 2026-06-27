#include <stddef.h>

/**
 * 使用内存
 * @param ptr 指向内存的指针
 */
void use_memory(void *ptr) {
  if (ptr != NULL) {
    // 使用内存进行某些操作
    char *data = (char *)ptr;
    data[0] = 'A';
  }
}
