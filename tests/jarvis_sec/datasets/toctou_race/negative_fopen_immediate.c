/*
 * 误报测试：TOCTOU - access后立即open（3行内，应被检测到）
 * 漏洞类型：toctou_race
 * 说明：access和open间隔在5行窗口内，应被正确检测
 * 预期：应检测到toctou_race（这是真正的TOCTOU漏洞）
 */
#include <unistd.h>
#include <fcntl.h>

void check_and_open_immediate(const char *filename) {
    if (access(filename, R_OK) == 0) {
        int fd = open(filename, O_RDONLY);  /* 紧跟access，在5行窗口内 */
        if (fd >= 0) close(fd);
    }
}
