// Negative case: all ManuallyDrop values are properly dropped
// No false positive here - checker correctly suppresses when all are dropped.

use std::mem::ManuallyDrop;

fn all_dropped() {
    let mut md1 = ManuallyDrop::new(Box::new(42));
    let mut md2 = ManuallyDrop::new(Box::new(99));
    // Both are properly dropped
    unsafe {
        ManuallyDrop::drop(&mut md1);
    }
    unsafe {
        ManuallyDrop::drop(&mut md2);
    }
}

fn main() {
    all_dropped();
}
