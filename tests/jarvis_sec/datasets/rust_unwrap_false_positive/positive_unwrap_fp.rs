// Positive case: unwrap false positive due to nearby match
// The checker's _is_unwrap_false_positive checks if there's a match
// in the previous 3 lines. If found, it assumes the unwrap is safe.
// But the unwrap may not be inside the Some branch of that match.

fn process(opt_a: Option<i32>, opt_b: Option<i32>) -> i32 {
    // This match handles opt_a
    match opt_a {
        Some(val) => val,
        None => 0,
    };
    // VULNERABLE: opt_b.unwrap() is NOT protected by the match above
    // But checker sees match within 3 lines and filters it out
    opt_b.unwrap()
}

fn main() {
    let result = process(Some(1), None);
    println!("result: {}", result);
}
