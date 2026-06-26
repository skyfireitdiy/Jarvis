#include <stdlib.h>

void allocate_and_free(int **ptr, int should_free) {
  *ptr = (int *)malloc(sizeof(int));
  if (should_free) {
    free(*ptr);
    // 释放后未置NULL
  }
}

void process_ptr(int *ptr) {
  // 可能再次释放
  free(ptr); // Double Free风险
}

int main(void) {
  int *data = NULL;
  allocate_and_free(&data, 1); // 内部已释放
  process_ptr(data);           // 再次释放 -> Double Free
  return 0;
}
