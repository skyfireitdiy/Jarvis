// Positive case: mem::transmute usage
use std::mem;

fn main() {
    let a: i32 = 1;
    let b: f32 = unsafe { mem::transmute(a) }; // dangerous transmute
    println!("b: {}", b);
}
