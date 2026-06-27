#include <stdlib.h>

/**
 * 分配内存
 * @return 指向分配内存的指针
 */
void *allocate_memory() {
  void *ptr = malloc(100);
  return ptr;
}
