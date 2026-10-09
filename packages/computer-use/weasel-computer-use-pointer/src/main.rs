use serde::Deserialize;
use serde_json::{json, Value};
use std::{
    io::{self, BufRead, Write},
    time::Instant,
};
use weasel_computer_use_pointer::{Button, Pointer, PointerError};

#[derive(Deserialize)]
struct Request {
    #[serde(default)]
    id: Value,
    #[serde(flatten)]
    action: Action,
}
#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
enum Action {
    Capabilities,
    Move {
        output: String,
        x: f64,
        y: f64,
        width: u32,
        height: u32,
    },
    Button {
        button: String,
        pressed: bool,
    },
    Click {
        output: String,
        x: f64,
        y: f64,
        width: u32,
        height: u32,
        button: String,
    },
    Scroll {
        dx: f64,
        dy: f64,
    },
    ScrollSteps {
        dx: i32,
        dy: i32,
    },
    ReleaseAll,
    Sync,
}
fn button(name: &str) -> Result<Button, PointerError> {
    match name {
        "left" => Ok(Button::Left),
        "right" => Ok(Button::Right),
        "middle" => Ok(Button::Middle),
        _ => Err(PointerError("button must be left, right, or middle".into())),
    }
}
fn act(pointer: &mut Pointer, action: Action) -> Result<Value, PointerError> {
    match action {
        Action::Capabilities => {
            return Ok(
                json!({"capabilities": pointer.capabilities(), "outputs": pointer.outputs()}),
            )
        }
        Action::Move {
            output,
            x,
            y,
            width,
            height,
        } => pointer.move_to(&output, x, y, width, height)?,
        Action::Button {
            button: name,
            pressed,
        } => pointer.button(button(&name)?, pressed)?,
        Action::Click {
            output,
            x,
            y,
            width,
            height,
            button: name,
        } => {
            let b = button(&name)?;
            pointer.move_to(&output, x, y, width, height)?;
            pointer.button(b, true)?;
            pointer.button(b, false)?;
        }
        Action::Scroll { dx, dy } => pointer.scroll(dx, dy)?,
        Action::ScrollSteps { dx, dy } => pointer.scroll_steps(dx, dy)?,
        Action::ReleaseAll => pointer.release_all()?,
        Action::Sync => pointer.sync()?,
    }
    Ok(json!({"ack":"sent", "ui_result_verified": false}))
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut pointer = Pointer::new()?;
    if std::env::args().skip(1).any(|a| a == "--capabilities") {
        println!(
            "{}",
            json!({"capabilities": pointer.capabilities(), "outputs": pointer.outputs()})
        );
        return Ok(());
    }
    let mut stdout = io::stdout().lock();
    for line in io::stdin().lock().lines() {
        let line = line?;
        let started = Instant::now();
        let response = match serde_json::from_str::<Request>(&line) {
            Ok(request) => match act(&mut pointer, request.action) {
                Ok(result) => {
                    json!({"id":request.id,"ok":true,"elapsed_us":started.elapsed().as_micros(),"result":result})
                }
                Err(err) => {
                    let release_error = pointer.release_all().err().map(|e| e.to_string());
                    json!({"id":request.id,"ok":false,"elapsed_us":started.elapsed().as_micros(),"error":err.to_string(),"release_error":release_error})
                }
            },
            Err(err) => {
                json!({"id":null,"ok":false,"error":format!("invalid JSON request: {err}")})
            }
        };
        writeln!(stdout, "{response}")?;
        stdout.flush()?;
    }
    pointer.release_all()?;
    Ok(())
}
