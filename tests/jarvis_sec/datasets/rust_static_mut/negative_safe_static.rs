// Negative case: thread-safe alternatives to static mut
// Using AtomicU64 for thread-safe global state without unsafe.

use std::sync::atomic::{AtomicU64, Ordering};

static COUNTER: AtomicU64 = AtomicU64::new(0);

fn increment() {
    COUNTER.fetch_add(1, Ordering::SeqCst);
}

fn read_counter() -> u64 {
    COUNTER.load(Ordering::SeqCst)
}

fn main() {
    increment();
    let val = read_counter();
    println!("counter: {}", val);
}
