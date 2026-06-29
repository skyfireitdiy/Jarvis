// Negative case: unsafe block with SAFETY comment
fn main() {
    let mut num = 5;
    // SAFETY: ptr is valid and points to initialized memory
    unsafe {
        let ptr = &mut num as *mut i32;
        *ptr = 10;
    }
    println!("num: {}", num);
}
