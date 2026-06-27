/*
 * 跨文件SQL注入 - SQL拼接模块
 * 用户输入在此文件被拼接到SQL语句中
 */
#include <string.h>
#include <stdio.h>

/* 使用strcat拼接SQL - 漏报点：c_checker仅检测sprintf/snprintf */
void build_select_query(char *sql, const char *username) {
    strcpy(sql, "SELECT * FROM users WHERE name='");
    strcat(sql, username);  /* 用户输入直接拼接 */
    strcat(sql, "'");
}

/* 使用snprintf拼接SQL */
void build_delete_query(char *sql, size_t len, const char *record_id) {
    snprintf(sql, len, "DELETE FROM records WHERE id=%s", record_id);
}
