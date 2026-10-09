use std::io::{self, Read};
fn main() {
    let mut bytes = Vec::new();
    let result = io::stdin()
        .take(262144)
        .read_to_end(&mut bytes)
        .map_err(|e| e.to_string())
        .and_then(|_| serde_json::from_slice(&bytes).map_err(|e| e.to_string()))
        .and_then(weasel_computer_use_atspi::run);
    match result {
        Ok(value) => println!("{value}"),
        Err(error) => {
            println!("{}", serde_json::json!({"status":"failed","error":error}));
            std::process::exit(1);
        }
    }
}
