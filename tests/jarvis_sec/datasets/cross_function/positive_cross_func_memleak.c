#include <stdlib.h>

typedef struct {
  int *data;
  size_t size;
} Buffer;

Buffer *create_buffer(size_t size) {
  Buffer *buf = (Buffer *)malloc(sizeof(Buffer));
  buf->data = (int *)malloc(size * sizeof(int));
  buf->size = size;
  return buf;
}

void use_buffer(Buffer *buf) {
  // 使用buffer但未释放
  for (size_t i = 0; i < buf->size; i++) {
    buf->data[i] = i;
  }
}

int main(void) {
  Buffer *b = create_buffer(100);
  use_buffer(b);
  // 未调用free，内存泄漏
  return 0;
}
