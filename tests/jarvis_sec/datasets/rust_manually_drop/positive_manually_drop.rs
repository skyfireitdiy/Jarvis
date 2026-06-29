// Positive case: ManuallyDrop without proper cleanup
use std::mem::ManuallyDrop;

fn main() {
    let mut data = ManuallyDrop::new(Box::new(42));
    // forgot to call ManuallyDrop::drop!
}
