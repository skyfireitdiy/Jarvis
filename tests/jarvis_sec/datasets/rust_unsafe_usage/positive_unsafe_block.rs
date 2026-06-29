// Positive case: unsafe block without SAFETY comment
fn main() {
    let mut num = 5;
    unsafe {
        let ptr = &mut num as *mut i32;
        *ptr = 10;
    }
    println!("num: {}", num);
}
