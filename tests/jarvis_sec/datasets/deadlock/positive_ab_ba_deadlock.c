#include <pthread.h>
#include <stdio.h>
#include <unistd.h>

pthread_mutex_t lockA = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_t lockB = PTHREAD_MUTEX_INITIALIZER;

void *thread1_func(void *arg) {
  // 线程1: 先锁A，再锁B (AB顺序)
  pthread_mutex_lock(&lockA);
  printf("Thread1: lockA acquired\n");
  sleep(1); // 让线程2有机会锁住B

  pthread_mutex_lock(&lockB); // 等待lockB，但线程2已持有lockB
  printf("Thread1: lockB acquired\n");

  pthread_mutex_unlock(&lockB);
  pthread_mutex_unlock(&lockA);
  return NULL;
}

void *thread2_func(void *arg) {
  // 线程2: 先锁B，再锁A (BA顺序) - 与线程1相反，形成死锁
  pthread_mutex_lock(&lockB);
  printf("Thread2: lockB acquired\n");
  sleep(1); // 让线程1有机会锁住A

  pthread_mutex_lock(&lockA); // 等待lockA，但线程1已持有lockA
  printf("Thread2: lockA acquired\n");

  pthread_mutex_unlock(&lockA);
  pthread_mutex_unlock(&lockB);
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
