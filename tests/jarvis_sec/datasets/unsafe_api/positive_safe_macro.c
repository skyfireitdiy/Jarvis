/*
 * 反例（绕过）：实际不安全的 strcpy 被包装在名为 SAFE_COPY 的宏中
 * 预期：检测器应检测到 strcpy，但 DataCollector 只记录 SAFE_COPY 调用（不属于 UNSAFE_APIS）
 * 漏洞：src 为用户可控内存，strcpy 无边界检查，可导致缓冲区溢出
 */
#include <string.h>

#define SAFE_COPY(dst, src) strcpy((dst), (src))

void test(char *dst, const char *user_input) {
    if (dst == NULL) return;
    SAFE_COPY(dst, user_input);  /* 宏展开后为 strcpy(dst, user_input) */
}
