/**
 * negative_cross_func.c
 * 
 * 绕过策略：通过全局变量和跨函数赋值，使空指针通过全局变量传递。
 * 检测器 _ast_null_deref_check 对全局变量直接跳过（第5616行：if var_name in global_vars: continue），
 * 不检查全局变量是否可能为NULL。
 * 
 * 漏洞位置：main() 中 global_item->value = 42，其中 global_item 在 init_global() 中被设为 NULL，
 * 实际运行时必然崩溃。
 */

#include <stdio.h>
#include <stdlib.h>

typedef struct {
    int value;
} Item;

// 全局变量，AST检测器视为"安全"（不会为NULL）
Item *global_item;

void init_global() {
    global_item = NULL;  // 将全局变量设为NULL
}

int main(int argc, char **argv) {
    init_global();  // 跨函数：在另一个函数中设置全局变量为NULL
    global_item->value = 42;  // 解引用NULL，但global_vars直接跳过，不产生告警
    printf("value=%d\n", global_item->value);
    return 0;
}
