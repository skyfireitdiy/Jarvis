/*
 * 反例（绕过）：mysql_query 使用多级指针间接引用用户输入
 * 预期：检测器应检测到，但：
 * 1) K&R 风格参数定义使污点分析无法识别用户输入 source
 * 2) *query 间接引用使启发式正则 mysql_query\([^,]+,\s*(\w+) 无法匹配变量名
 * 漏洞：query 是用户可控的 SQL 字符串，直接执行任意 SQL
 */

void vulnerable(conn, query)
void *conn;
char **query;
{
    mysql_query(conn, *query);  /* 直接执行用户可控SQL */
}
