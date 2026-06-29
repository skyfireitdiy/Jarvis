// Negative case: proper ManuallyDrop cleanup
use std::mem::ManuallyDrop;

fn main() {
    let mut data = ManuallyDrop::new(Box::new(42));
    unsafe {
        ManuallyDrop::drop(&mut data); // proper cleanup
    }
}
