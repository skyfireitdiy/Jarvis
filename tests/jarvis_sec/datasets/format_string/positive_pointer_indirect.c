/*
 * 反例（绕过）：变量先赋值为字面量，后被覆盖为用户可控值
 * 预期：检测器应检测到，但启发式只看是否存在字面量赋值而不检查覆盖
 * 漏洞：fmt 被赋值为外部参数（用户可控），printf(fmt) 触发格式化字符串漏洞
 */
#include <stdio.h>

void vulnerable(const char *user_input) {
    char *fmt = "%d";            // 第1次赋值：字面量（检测器看到这个就认为安全）
    fmt = (char *)user_input;     // 覆盖为外部输入
    printf(fmt);                  // 真实风险：fmt 现在是用户可控的格式串
}
