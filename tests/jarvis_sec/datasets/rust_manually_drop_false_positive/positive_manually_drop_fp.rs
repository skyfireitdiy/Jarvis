// Positive case: ManuallyDrop false positive
// The checker suppresses ALL ManuallyDrop warnings if ANY ManuallyDrop::drop
// exists in the file. This means leaked ManuallyDrop values are not reported.
// This file should report the leaked value but currently doesn't.

use std::mem::ManuallyDrop;

fn good_usage() {
    let mut md = ManuallyDrop::new(Box::new(42));
    // This one is properly dropped - should NOT be reported
    unsafe {
        ManuallyDrop::drop(&mut md);
    }
}

fn bad_usage() -> *mut i32 {
    let md = ManuallyDrop::new(Box::new(99));
    // VULNERABLE: this ManuallyDrop is NEVER dropped - memory leak
    // But checker suppresses it because good_usage() has ManuallyDrop::drop
    let ptr = &**md as *const i32 as *mut i32;
    ptr
}

fn main() {
    good_usage();
    let leaked = bad_usage();
}
