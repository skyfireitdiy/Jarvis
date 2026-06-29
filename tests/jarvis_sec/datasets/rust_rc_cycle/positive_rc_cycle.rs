// Positive case: Rc reference cycle causing memory leak
// Rc does not support weak references for cycle breaking automatically.
// When nodes form a cycle via Rc, reference counts never reach zero,
// causing a memory leak that the checker cannot detect.

use std::cell::RefCell;
use std::rc::Rc;

struct Node {
    value: i32,
    next: Option<Rc<RefCell<Node>>>,
}

fn create_cycle() {
    let a = Rc::new(RefCell::new(Node {
        value: 1,
        next: None,
    }));
    let b = Rc::new(RefCell::new(Node {
        value: 2,
        next: Some(a.clone()),
    }));
    // VULNERABLE: creates a cycle, memory will never be freed
    a.borrow_mut().next = Some(b.clone());
}

fn main() {
    create_cycle();
    // a and b form a cycle: a -> b -> a
    // Neither will be dropped, memory is leaked
}
