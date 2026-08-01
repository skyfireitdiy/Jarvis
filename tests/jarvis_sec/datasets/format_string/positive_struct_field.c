/*
 * 反例（绕过）：格式化字符串存储在结构体字段中，先赋值为字面量再覆盖
 * 预期：检测器应检测到，但_var_assigned_literal回看发现字面量赋值即认为安全
 * 漏洞：cfg->format 可能是用户可控的格式串
 */
#include <stdio.h>

typedef struct {
    char *format;
} Config;

void vulnerable(Config *cfg) {
    if (cfg == NULL) return;
    char *fmt = "%d";        // 字面量赋值（检测器认为安全）
    fmt = cfg->format;        // 覆盖为用户可控值
    printf(fmt);              // 真实风险：fmt 现在是用户可控的格式串
}
