// Positive case: unwrap false positive due to is_some on different variable
// The checker's _is_unwrap_false_positive checks if there's an is_some
// in the previous 5 lines. If found, it assumes the unwrap is safe.
// But the is_some may be checking a different variable.

fn process(opt_a: Option<i32>, opt_b: Option<i32>) -> i32 {
    // This is_some checks opt_a, NOT opt_b
    if opt_a.is_some() {
        println!("opt_a exists");
    }
    // VULNERABLE: opt_b.unwrap() is NOT protected by opt_a.is_some()
    // But checker sees is_some within 5 lines and filters it out
    opt_b.unwrap()
}

fn main() {
    let result = process(Some(1), None);
    println!("result: {}", result);
}
