#include <stdlib.h>

void* get_buffer() {
    return malloc(100);
}

void use_buffer(void* buf) {
    // 使用内存
}

void release_buffer(void* buf) {
    free(buf);
}
