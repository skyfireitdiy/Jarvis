#include <stdlib.h>
#include <string.h>

char *create_buffer(void) {
  char *buf = (char *)malloc(100);
  if (buf == NULL) {
    return NULL; // 检查malloc返回值
  }
  return buf;
}

void safe_free_buffer(char **buf) {
  if (buf != NULL && *buf != NULL) {
    free(*buf);
    *buf = NULL; // 安全：置NULL
  }
}

void use_buffer(char *buf) {
  if (buf != NULL) {
    strcpy(buf, "hello");
  }
}

int main(void) {
  char *buffer = create_buffer();
  if (buffer == NULL) {
    return 1; // 检查返回值
  }
  use_buffer(buffer);
  safe_free_buffer(&buffer); // 安全释放并置NULL
  use_buffer(buffer);        // buffer已为NULL，安全
  return 0;
}
