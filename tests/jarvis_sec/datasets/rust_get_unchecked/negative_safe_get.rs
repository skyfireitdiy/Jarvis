// Negative case: safe get with bounds check
fn main() {
    let v = vec![1, 2, 3, 4, 5];
    if let Some(elem) = v.get(10) {
        println!("elem: {}", elem);
    } else {
        println!("index out of bounds");
    }
}
