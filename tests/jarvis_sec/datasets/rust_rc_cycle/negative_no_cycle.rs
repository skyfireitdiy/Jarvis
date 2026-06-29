// Negative case: Weak references break the cycle
// Using Weak to break reference cycles, allowing proper deallocation.

use std::cell::RefCell;
use std::rc::{Rc, Weak};

struct Node {
    value: i32,
    next: Option<Rc<RefCell<Node>>>,
    prev: Option<Weak<RefCell<Node>>>, // Weak breaks the cycle
}

fn create_list() {
    let a = Rc::new(RefCell::new(Node {
        value: 1,
        next: None,
        prev: None,
    }));
    let b = Rc::new(RefCell::new(Node {
        value: 2,
        next: None,
        prev: Some(Rc::downgrade(&a)), // Weak reference
    }));
    a.borrow_mut().next = Some(b.clone());
}

fn main() {
    create_list();
    // No cycle: a -> b, b -weak-> a
    // Both will be properly dropped
}
