/*
 * 正例：time函数使用
 * 预期：应该检测到 time_apis_not_threadsafe
 */
#include <time.h>
void foo() {
  time_t t = time(NULL); // 真实风险：不线程安全
}
