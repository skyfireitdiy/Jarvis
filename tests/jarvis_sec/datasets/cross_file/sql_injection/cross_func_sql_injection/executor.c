/*
 * 跨文件SQL注入 - SQL执行模块
 * 拼接后的SQL在此文件被执行
 */
#include <mysql/mysql.h>

/* 执行SQL查询 */
void execute_query(MYSQL *conn, const char *sql) {
    mysql_query(conn, sql);  /* 执行可能被注入的SQL */
}

/* 执行SQLite查询 - 漏报点：c_checker未覆盖sqlite3_exec */
void execute_sqlite(void *db, const char *sql) {
    sqlite3_exec((sqlite3*)db, sql, NULL, NULL, NULL);
}
