/*
 * 反例（绕过）：execl 第一个参数先赋值为字面量路径，后被覆盖为用户可控值
 * 预期：检测器应检测到，但 _var_assigned_literal 发现字面量赋值即认为安全，未检查覆盖
 * 漏洞：path 被外部输入覆盖后传给 execl，可执行任意程序
 */
#include <unistd.h>

char *user_ctrl = "/bin/ls";  // 全局字面量，用于让检测器认为 user_ctrl 安全

void vulnerable(user_ctrl)
char *user_ctrl;
{
    char *path = "/bin/ls";       // 字面量赋值（检测器认为安全）
    path = user_ctrl;            // 覆盖为用户可控路径
    execl(path, "arg1", NULL);   // 真实风险：执行任意程序
}
