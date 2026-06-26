#include <pthread.h>
#include <stdio.h>
#include <unistd.h>

pthread_mutex_t lockA = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_t lockB = PTHREAD_MUTEX_INITIALIZER;

void acquire_b_then_a() {
  // 函数1: 先锁B，再锁A (BA顺序)
  pthread_mutex_lock(&lockB);
  printf("acquire_b_then_a: lockB acquired\n");
  sleep(1);

  pthread_mutex_lock(&lockA); // 等待lockA
  printf("acquire_b_then_a: lockA acquired\n");

  pthread_mutex_unlock(&lockA);
  pthread_mutex_unlock(&lockB);
}

void acquire_a_then_b() {
  // 函数2: 先锁A，再锁B (AB顺序)
  pthread_mutex_lock(&lockA);
  printf("acquire_a_then_b: lockA acquired\n");
  sleep(1);

  pthread_mutex_lock(&lockB); // 等待lockB
  printf("acquire_a_then_b: lockB acquired\n");

  pthread_mutex_unlock(&lockB);
  pthread_mutex_unlock(&lockA);
}

void *thread1_func(void *arg) {
  acquire_a_then_b(); // AB顺序
  return NULL;
}

void *thread2_func(void *arg) {
  acquire_b_then_a(); // BA顺序，与thread1相反
  return NULL;
}

int main() {
  pthread_t t1, t2;
  pthread_create(&t1, NULL, thread1_func, NULL);
  pthread_create(&t2, NULL, thread2_func, NULL);

  pthread_join(t1, NULL);
  pthread_join(t2, NULL);
  return 0;
}
