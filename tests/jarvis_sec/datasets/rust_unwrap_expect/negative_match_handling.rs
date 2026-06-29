// Negative case: proper error handling with match
fn main() {
    let option = Some(5);
    match option {
        Some(value) => println!("value: {}", value),
        None => println!("no value"),
    }
}
