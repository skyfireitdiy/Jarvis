/*
 * 预期检测结果: 不应报告漏洞
 * 安全实践: 使用安全的整数运算检查，防止溢出
 * 注意: 当前检测器可能对此案例产生误报，这暴露了检测器的改进空间
 */
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <limits.h>

// 安全版本1: 乘法溢出检查
void safe_multiply_alloc(size_t count, size_t elem_size) {
    // 安全: 检查乘法是否会溢出
    if (count > 0 && elem_size > 0 && count <= SIZE_MAX / elem_size) {
        size_t total = count * elem_size;
        char *buffer = (char *)malloc(total);
        if (buffer) {
            for (size_t i = 0; i < count; i++) {
                buffer[i * elem_size] = 'x';
            }
            free(buffer);
        }
    }
}

// 安全版本2: 加法溢出检查
void safe_add_alloc(size_t base_size, size_t extra) {
    // 安全: 检查加法是否会溢出
    if (base_size <= SIZE_MAX - extra) {
        size_t total = base_size + extra;
        char *buffer = (char *)malloc(total);
        if (buffer) {
            memset(buffer, 'A', base_size);
            free(buffer);
        }
    }
}

// 安全版本3: 使用calloc避免溢出
void safe_calloc_alloc(size_t count, size_t elem_size) {
    // 安全: calloc内部会检查溢出
    char *buffer = (char *)calloc(count, elem_size);
    if (buffer) {
        for (size_t i = 0; i < count; i++) {
            buffer[i * elem_size] = 'x';
        }
        free(buffer);
    }
}

// 安全版本4: 使用安全的API（如reallocarray）
void safe_reallocarray_alloc(size_t count, size_t elem_size) {
    // 安全: reallocarray会检查乘法溢出
    char *buffer = NULL;
    // 模拟reallocarray的安全检查
    if (count > 0 && elem_size > 0 && count <= SIZE_MAX / elem_size) {
        buffer = (char *)malloc(count * elem_size);
        if (buffer) {
            memset(buffer, 0, count * elem_size);
            free(buffer);
        }
    }
}
