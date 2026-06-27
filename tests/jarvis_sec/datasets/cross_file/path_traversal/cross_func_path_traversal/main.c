/*
 * 跨文件路径遍历 - 主入口
 * 漏洞类型：path_traversal (跨文件)
 * 漏报原因：用户输入跨文件传播到文件操作，
 *          c_checker的_rule_path_traversal仅检测单文件内strcat+fopen的3行窗口
 * 数据流：main.c -> input.c(get_filename) -> path_builder.c(build_path) -> file_opener.c(open_file_read)
 * 预期：应检测到path_traversal，但当前版本因跨文件分析限制而漏报
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern const char *get_filename(void);
extern void build_path(char *fullpath, size_t len, const char *filename);
extern FILE *open_file_read(const char *path);

int main(void) {
    char path[512];

    /* 跨文件路径遍历数据流 */
    const char *filename = get_filename();    /* input.c: 获取用户输入 */
    build_path(path, sizeof(path), filename); /* path_builder.c: 拼接路径 */
    FILE *fp = open_file_read(path);          /* file_opener.c: 打开文件 */

    if (fp) {
        char buf[128];
        fgets(buf, sizeof(buf), fp);
        fclose(fp);
    }

    return 0;
}
