// Positive case: unwrap without check
fn main() {
    let option = Some(5);
    let value = option.unwrap();
    println!("value: {}", value);
}
