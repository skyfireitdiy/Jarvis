/*
 * 跨文件路径遍历 - 文件操作模块
 * 拼接后的路径在此文件被用于打开文件
 */
#include <stdio.h>
#include <fcntl.h>

/* 使用fopen打开文件 */
FILE *open_file_read(const char *path) {
    return fopen(path, "r");  /* 打开可能被遍历的路径 */
}

/* 使用open打开文件 */
int open_file_fd(const char *path) {
    return open(path, O_RDONLY);  /* 打开可能被遍历的路径 */
}
