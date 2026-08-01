// Bypass 1: format_string - 通过指针间接传格式串
// 期望：不应报 format_string（格式串来自 const char*）
void format_bypass_1(void) {
    const char *fmt = "hello %s\n";
    const char **pfmt = &fmt;
    printf(*pfmt, "world");  // 格式串是 *pfmt -> "hello %s\n"，实际安全
}

// Bypass 2: 通过结构体成员存储格式串
struct log_config {
    const char *format;
};

void format_bypass_2(struct log_config *cfg) {
    printf(cfg->format, 42);  // cfg->format 应在初始化时设为字面量
}
