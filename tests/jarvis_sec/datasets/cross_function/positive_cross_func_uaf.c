#include <stdlib.h>
#include <string.h>

char *create_buffer(void) {
  char *buf = (char *)malloc(100);
  return buf;
}

void free_buffer(char *buf) {
  free(buf);
  // 释放后未置NULL
}

void use_buffer(char *buf) {
  strcpy(buf, "hello"); // UAF: 调用者可能在free后继续使用
}

int main(void) {
  char *buffer = create_buffer();
  free_buffer(buffer);
  use_buffer(buffer); // 释放后使用
  return 0;
}
