/*
 * 预期检测结果: 应检测到整数溢出导致缓冲区溢出漏洞
 * 漏洞类型: CWE-680: Integer Overflow to Buffer Overflow
 * 描述: 整数溢出导致缓冲区分配不足，后续写入造成溢出
 */
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

// 场景1: 乘法溢出导致分配不足
void multiply_overflow_alloc(size_t count, size_t elem_size) {
    // 漏洞: count * elem_size 可能溢出，导致分配过小的缓冲区
    size_t total = count * elem_size;
    char *buffer = (char *)malloc(total);
    if (buffer) {
        // 后续写入时假设有count个元素的空间，实际可能溢出后很小
        for (size_t i = 0; i < count; i++) {
            buffer[i * elem_size] = 'x';  // 可能越界写入
        }
        free(buffer);
    }
}

// 场景2: 加法溢出导致分配不足
void add_overflow_alloc(size_t base_size, size_t extra) {
    // 漏洞: base_size + extra 可能溢出
    size_t total = base_size + extra;
    char *buffer = (char *)malloc(total);
    if (buffer) {
        // 写入base_size字节，但实际分配可能很小
        memset(buffer, 'A', base_size);  // 可能越界写入
        free(buffer);
    }
}

// 场景3: size_t回绕导致分配0字节
void wraparound_alloc(size_t user_size) {
    // 漏洞: user_size + 1 可能回绕到0
    size_t alloc_size = user_size + 1;
    char *buffer = (char *)malloc(alloc_size);  // 可能分配0字节
    if (buffer) {
        // 写入user_size字节，但缓冲区实际为0
        memset(buffer, 'B', user_size);  // 必定越界写入
        free(buffer);
    }
}

// 场景4: 数组索引计算溢出
void index_overflow_alloc(int index, int offset) {
    // 漏洞: index + offset 可能溢出
    int target = index + offset;
    char buffer[100];
    if (target >= 0 && target < 100) {
        buffer[target] = 'C';  // 检查可能通过，但target实际可能溢出
    }
}
