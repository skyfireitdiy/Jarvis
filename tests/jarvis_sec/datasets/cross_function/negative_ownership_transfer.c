#include <stdlib.h>

int *create_data(void) {
  int *data = (int *)malloc(sizeof(int) * 10);
  if (data == NULL) {
    return NULL; // 检查malloc返回值
  }
  return data; // 所有权转移给调用者
}

void process_and_free(int *data) {
  if (data == NULL) {
    return; // 检查NULL
  }
  // 处理数据
  for (int i = 0; i < 10; i++) {
    data[i] = i * 2;
  }
  free(data); // 正确：函数负责释放
}

int main(void) {
  int *d = create_data();
  if (d == NULL) {
    return 1; // 检查返回值
  }
  process_and_free(d); // 所有权转移，正确释放
  // d不再有效，但未使用
  return 0;
}
