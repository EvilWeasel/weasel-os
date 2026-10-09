use serde_json::{json, Value};
use std::{
    io::{self, BufRead, Write},
    thread,
    time::{Duration, Instant},
};
use weasel_computer_use_keyboard::{named_evdev, Keyboard};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.first().map(String::as_str) == Some("--keymap-info") {
        println!(
            "{}",
            json!({"layout":"de","codes":{"ctrl":named_evdev("ctrl")?,"a":named_evdev("a")?,"s":named_evdev("s")?,"y":named_evdev("y")?,"z":named_evdev("z")?},"input_sent":false})
        );
        return Ok(());
    }
    let mut keyboard = Keyboard::new()?;
    if args.first().map(String::as_str) == Some("chord") {
        let codes: Vec<_> = args
            .iter()
            .skip(1)
            .map(|x| named_evdev(x))
            .collect::<Result<_, _>>()?;
        if codes.is_empty() || codes.len() > 6 {
            return Err("chord needs 1..6 key names".into());
        }
        for code in &codes {
            keyboard.key_evdev(*code, true)?;
            keyboard.sync()?;
            thread::sleep(Duration::from_millis(5));
        }
        for code in codes.iter().rev() {
            keyboard.key_evdev(*code, false)?;
            keyboard.sync()?;
        }
        keyboard.release_all()?;
        return Ok(());
    }
    for line in io::stdin().lock().lines() {
        let request: Value = serde_json::from_str(&line?)?;
        let start = Instant::now();
        let result = (|| {
            match request["op"].as_str().unwrap_or("") {
                "key" => keyboard.key_evdev(
                    request["code"].as_u64().ok_or("missing code")? as u32,
                    request["pressed"].as_bool().ok_or("missing pressed")?,
                )?,
                "named" => keyboard.key_named(
                    request["name"].as_str().ok_or("missing name")?,
                    request["pressed"].as_bool().ok_or("missing pressed")?,
                )?,
                "release_all" => keyboard.release_all()?,
                "sync" => keyboard.sync()?,
                "refresh_keymap" => keyboard.refresh_keymap()?,
                _ => return Err("unknown op".into()),
            }
            Ok::<(), Box<dyn std::error::Error>>(())
        })();
        let response = match result {
            Ok(()) => {
                json!({"id":request["id"],"ok":true,"elapsed_us":start.elapsed().as_micros(),"ui_result_verified":false})
            }
            Err(e) => {
                let _ = keyboard.release_all();
                json!({"id":request["id"],"ok":false,"error":e.to_string()})
            }
        };
        println!("{response}");
        io::stdout().flush()?;
    }
    keyboard.release_all()?;
    Ok(())
}
