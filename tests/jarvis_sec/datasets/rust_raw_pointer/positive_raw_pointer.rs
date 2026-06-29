// Positive case: raw pointer usage
fn main() {
    let mut num = 5;
    let ptr = &mut num as *mut i32;
    unsafe {
        *ptr = 10;
    }
}
