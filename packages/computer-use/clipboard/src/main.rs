fn main() {
    if let Err(message) = weasel_computer_use_clipboard::helper_main() {
        eprintln!("clipboard helper: {message}");
        std::process::exit(1);
    }
}
