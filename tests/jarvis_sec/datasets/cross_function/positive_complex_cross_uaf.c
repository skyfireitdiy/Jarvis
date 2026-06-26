#include <stdlib.h>
#include <string.h>

typedef struct Node {
  char *value;
  struct Node *next;
} Node;

Node *create_node(const char *val) {
  Node *n = (Node *)malloc(sizeof(Node));
  n->value = (char *)malloc(strlen(val) + 1);
  strcpy(n->value, val);
  n->next = NULL;
  return n;
}

void free_node_value(Node *n) {
  if (n != NULL) {
    free(n->value); // 释放value但未置NULL
  }
}

void print_node(Node *n) {
  if (n != NULL && n->value != NULL) {
    // 使用已释放的value
    printf("%s\n", n->value); // UAF
  }
}

int main(void) {
  Node *node = create_node("test");
  free_node_value(node); // 释放value
  print_node(node);      // 使用已释放的value -> UAF
  free(node->value);     // Double Free
  free(node);
  return 0;
}
