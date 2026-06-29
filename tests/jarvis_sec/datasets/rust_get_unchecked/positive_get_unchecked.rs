// Positive case: get_unchecked without bounds check
fn main() {
    let v = vec![1, 2, 3, 4, 5];
    unsafe {
        let elem = v.get_unchecked(10); // out of bounds!
        println!("elem: {}", elem);
    }
}
