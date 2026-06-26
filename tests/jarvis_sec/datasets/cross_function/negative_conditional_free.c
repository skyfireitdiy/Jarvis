#include <stdlib.h>

void maybe_free(int **ptr, int condition) {
  if (ptr == NULL || *ptr == NULL) {
    return; // 检查NULL
  }
  if (condition) {
    free(*ptr);
    *ptr = NULL;
  }
}

int main(void) {
  int *data = (int *)malloc(sizeof(int));
  if (data == NULL) {
    return 1; // 检查malloc返回值
  }
  *data = 42;

  maybe_free(&data, 1); // 条件释放

  if (data == NULL) {
    // 正确：检查后使用
    return 0;
  }

  *data = 100; // 只有data不为NULL时才执行
  free(data);
  return 0;
}
