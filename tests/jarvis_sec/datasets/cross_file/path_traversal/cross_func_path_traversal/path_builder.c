/*
 * 跨文件路径遍历 - 路径拼接模块
 * 用户输入在此文件被拼接到文件路径中
 * 漏报点：c_checker的_rule_path_traversal仅检测strcat/strncat+fopen的3行窗口
 */
#include <string.h>
#include <stdio.h>

/* 使用snprintf拼接路径 - 漏报点 */
void build_path(char *fullpath, size_t len, const char *filename) {
    snprintf(fullpath, len, "/var/data/%s", filename);  /* 用户输入可能包含"../" */
}

/* 使用strcat拼接路径 */
void append_subdir(char *path, const char *subdir) {
    strcat(path, "/");
    strcat(path, subdir);  /* 用户输入直接拼接到路径 */
}
