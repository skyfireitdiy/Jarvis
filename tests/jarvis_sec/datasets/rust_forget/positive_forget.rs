// Positive case: mem::forget causing resource leak
use std::mem;

fn main() {
    let data = Box::new(42);
    mem::forget(data); // memory leak!
}
