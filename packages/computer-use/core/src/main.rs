mod global_keyboard;
mod takeover;
use base64::{engine::general_purpose::STANDARD, Engine};
use keyboard::Keyboard;
use pointer::{Button, Pointer};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    cell::RefCell,
    collections::HashMap,
    env, fs,
    io::{self, BufRead, BufReader, Read, Write},
    os::{
        fd::AsRawFd,
        unix::{
            fs::{FileTypeExt, MetadataExt, OpenOptionsExt, PermissionsExt},
            net::{UnixListener, UnixStream},
            process::CommandExt,
        },
    },
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{
        atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering},
        Arc, Mutex,
    },
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

type R<T> = Result<T, String>;
const MAX_REQUEST: u64 = 262_144;
const MAX_AGE: Duration = Duration::from_secs(60);
thread_local! {static CURRENT_CANCEL_FLAG: RefCell<Option<Arc<AtomicBool>>> = const { RefCell::new(None) };}
thread_local! {static CURRENT_DEADLINE: RefCell<Option<Instant>> = const { RefCell::new(None) };}
fn own_canceled() -> bool {
    CURRENT_CANCEL_FLAG.with(|f| {
        f.borrow()
            .as_ref()
            .is_some_and(|v| v.load(Ordering::SeqCst))
    })
}
struct DeadlineGuard(Option<Instant>);
impl DeadlineGuard {
    fn set(deadline: Option<Instant>) -> Self {
        Self(CURRENT_DEADLINE.with(|d| d.replace(deadline)))
    }
}
impl Drop for DeadlineGuard {
    fn drop(&mut self) {
        CURRENT_DEADLINE.with(|d| *d.borrow_mut() = self.0);
    }
}
fn deadline_elapsed() -> bool {
    CURRENT_DEADLINE.with(|d| d.borrow().is_some_and(|until| Instant::now() >= until))
}
fn remaining_timeout(max: Duration) -> Duration {
    CURRENT_DEADLINE.with(|d| {
        d.borrow()
            .map(|until| max.min(until.saturating_duration_since(Instant::now())))
            .unwrap_or(max)
    })
}

#[derive(Clone)]
struct Observation {
    id: String,
    at: Instant,
    epoch: u64,
    output: String,
    output_geometry: Value,
    focused_window: Option<Value>,
    focus_output: Option<String>,
    image_width: u32,
    image_height: u32,
    image: PathBuf,
    view: Crop,
    view_image: PathBuf,
}
#[derive(Clone, Deserialize, Serialize)]
struct Crop {
    x: u32,
    y: u32,
    width: u32,
    height: u32,
}
#[derive(Clone)]
struct SemanticTarget {
    at: Instant,
    epoch: u64,
    window: Value,
    snapshot: Arc<atspi::Snapshot>,
    object: atspi::Object,
}

struct State {
    started: Instant,
    session_id: String,
    epoch: AtomicU64,
    serial: AtomicU64,
    queued: AtomicUsize,
    takeover: AtomicBool,
    takeover_marker: Mutex<takeover::Latch>,
    last_human_ms: AtomicU64,
    human_monitor: Mutex<Value>,
    release_confirmed: AtomicBool,
    capture_available: AtomicBool,
    active: Mutex<Value>,
    last_result: Mutex<Value>,
    observations: Mutex<HashMap<String, Observation>>,
    semantic_targets: Mutex<HashMap<String, SemanticTarget>>,
    actor: Mutex<Option<Pointer>>,
    keyboard: Mutex<Option<Keyboard>>,
    global_keyboard: Mutex<Option<global_keyboard::GlobalKeyboard>>,
    image_dir: PathBuf,
    log: Mutex<fs::File>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "snake_case")]
enum TextMethod {
    Auto,
    Keyboard,
    Clipboard,
}
fn default_text_method() -> TextMethod {
    TextMethod::Auto
}
#[derive(Debug, Deserialize, Default, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum KeyScope {
    #[default]
    App,
    Compositor,
}
#[derive(Debug, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
enum Action {
    Focus {
        window_id: u64,
    },
    Move {
        x: f64,
        y: f64,
    },
    Click {
        x: f64,
        y: f64,
        #[serde(default)]
        button: Option<String>,
        #[serde(default)]
        count: Option<u8>,
    },
    Scroll {
        x: f64,
        y: f64,
        #[serde(default)]
        dx: i32,
        #[serde(default)]
        dy: i32,
    },
    Drag {
        x: f64,
        y: f64,
        to_x: f64,
        to_y: f64,
        #[serde(default)]
        duration_ms: Option<u64>,
    },
    Type {
        text: String,
        #[serde(default = "default_text_method")]
        text_method: TextMethod,
    },
    Paste {
        text: String,
        #[serde(default = "default_restore_clipboard")]
        restore_clipboard: bool,
    },
    Key {
        keys: Vec<String>,
        #[serde(default)]
        key_scope: KeyScope,
    },
    SemanticSetValue {
        handle_id: String,
        text: String,
        #[serde(default)]
        expected_text: Option<String>,
    },
    SemanticClick {
        handle_id: String,
        action_name: String,
    },
    Wait {
        ms: u64,
    },
}
fn default_restore_clipboard() -> bool {
    true
}

impl Action {
    fn name(&self) -> &'static str {
        match self {
            Self::Focus { .. } => "focus",
            Self::Move { .. } => "move",
            Self::Click { .. } => "click",
            Self::Scroll { .. } => "scroll",
            Self::Drag { .. } => "drag",
            Self::Type { .. } => "type",
            Self::Paste { .. } => "paste",
            Self::Key { .. } => "key",
            Self::SemanticSetValue { .. } => "semantic_set_value",
            Self::SemanticClick { .. } => "semantic_click",
            Self::Wait { .. } => "wait",
        }
    }
    fn pointer(&self) -> bool {
        matches!(
            self,
            Self::Move { .. } | Self::Click { .. } | Self::Scroll { .. } | Self::Drag { .. }
        )
    }
}

const GLOBAL_ROUTING_REVISION: u32 = 2;
fn global_keyboard_capability() -> Value {
    json!({"routing_revision":GLOBAL_ROUTING_REVISION,"key_scope":["app","compositor"],"super_implies_compositor":true,"transport":"owned_uinput","device_creation":"only during guarded action preparation","readiness":"authenticated Niri peer has own exact event node open; not proof of configured/UI acceptance","ui_success_requires_verification":true,"fallback":false})
}
#[derive(Deserialize)]
struct GlobalBackendGuard {
    routing_revision: u32,
    session_id: String,
    epoch: u64,
}
#[derive(Deserialize)]
struct ActArgs {
    observation_id: String,
    #[serde(default)]
    window_id: Option<u64>,
    #[serde(default)]
    task_id: Option<String>,
    actions: Vec<Action>,
    // Added by new proxies after a fresh capability check. An old proxy can
    // still send Super safely: this core always routes it to owned uinput.
    #[serde(default)]
    expected_global_backend: Option<GlobalBackendGuard>,
    #[serde(default)]
    timeout_ms: Option<u64>,
    #[serde(default = "default_observe_after")]
    observe_after: bool,
    #[serde(default = "default_observe_after")]
    include_image: bool,
    #[serde(default = "default_settle_ms")]
    settle_ms: u64,
}
fn default_observe_after() -> bool {
    true
}
fn default_settle_ms() -> u64 {
    80
}

fn uid() -> u32 {
    fs::read_to_string("/proc/self/status")
        .ok()
        .and_then(|s| {
            s.lines()
                .find(|l| l.starts_with("Uid:"))
                .and_then(|l| l.split_whitespace().nth(2))
                .and_then(|n| n.parse().ok())
        })
        .unwrap_or(1000)
}

fn private_dir(path: &Path) -> R<()> {
    if path.exists() {
        let m = fs::symlink_metadata(path).map_err(|e| e.to_string())?;
        if !m.is_dir() || m.file_type().is_symlink() || m.uid() != uid() {
            return Err("Private state directory must be a nonsymlink owned directory".into());
        }
    } else {
        fs::create_dir_all(path).map_err(|e| e.to_string())?;
    }
    fs::set_permissions(path, fs::Permissions::from_mode(0o700)).map_err(|e| e.to_string())
}

fn check_epoch(state: &State, epoch: Option<u64>) -> R<()> {
    if own_canceled() {
        return Err(
            "This client request was canceled or disconnected; its pending actions stopped".into(),
        );
    }
    if deadline_elapsed() {
        return Err("Action batch deadline elapsed; pending dispatch/capture stopped".into());
    }
    if epoch.is_some_and(|e| state.epoch.load(Ordering::SeqCst) != e) {
        Err("Canceled or desktop taken over; queued actions discarded".into())
    } else {
        Ok(())
    }
}

fn human_monitor(state: Arc<State>) {
    struct Device {
        path: PathBuf,
        file: fs::File,
        simulation: bool,
    }
    // Private integration-test hook: only a deliberately created, uniquely named
    // uinput device may exercise the real evdev monitor. Never configured in the
    // production service, and always reported as controlled simulation.
    let test_device = env::var("WEASEL_COMPUTER_USE_TEST_INPUT_DEVICE")
        .ok()
        .filter(|name| {
            name.starts_with("weasel-cua-takeover-test-")
                && name.len() <= 80
                && !name.chars().any(|c| c.is_control())
        });
    let mut devices: Vec<Device> = Vec::new();
    let mut scan_at = Instant::now() - Duration::from_secs(3);
    loop {
        if scan_at.elapsed() > Duration::from_secs(2) {
            scan_at = Instant::now();
            let mut denied = 0usize;
            if let Ok(entries) = fs::read_dir("/sys/class/input") {
                for entry in entries.flatten() {
                    let name = entry.file_name().to_string_lossy().into_owned();
                    if !name.starts_with("event") {
                        continue;
                    }
                    let syspath = match (entry.path().join("device")).canonicalize() {
                        Ok(p) => p,
                        Err(_) => continue,
                    };
                    // Bluetooth UHID devices under virtual/misc are physical user input;
                    // only direct kernel virtual/input devices are synthetic uinput.
                    let virtual_input = syspath.starts_with("/sys/devices/virtual/input");
                    let simulation = virtual_input
                        && test_device.as_ref().is_some_and(|expected| {
                            fs::read_to_string(syspath.join("name"))
                                .is_ok_and(|name| name.trim() == expected)
                        });
                    if virtual_input && !simulation {
                        continue;
                    }
                    let mask = fs::read_to_string(syspath.join("capabilities/ev"))
                        .ok()
                        .and_then(|s| {
                            u64::from_str_radix(
                                s.trim().split_whitespace().last().unwrap_or("0"),
                                16,
                            )
                            .ok()
                        })
                        .unwrap_or(0);
                    if mask & ((1 << 1) | (1 << 2) | (1 << 3)) == 0 {
                        continue;
                    }
                    let path = PathBuf::from("/dev/input").join(name);
                    if devices.iter().any(|d| d.path == path) {
                        continue;
                    }
                    match fs::OpenOptions::new()
                        .read(true)
                        .custom_flags(libc::O_NONBLOCK | libc::O_CLOEXEC)
                        .open(&path)
                    {
                        Ok(file) => devices.push(Device {
                            path,
                            file,
                            simulation,
                        }),
                        Err(_) => denied += 1,
                    }
                }
            }
            if let Ok(mut status) = state.human_monitor.lock() {
                *status = json!({"available":!devices.is_empty(),"watched_devices":devices.len(),"permission_denied_devices":denied,"event_data_retained":false,"source":"physical evdev activity; excludes direct uinput; includes Bluetooth UHID","controlled_simulation_device_enabled":test_device.is_some(),"watched_simulation_devices":devices.iter().filter(|d|d.simulation).count(),"poll_interval_ms":5});
            }
        }
        let mut remove = Vec::new();
        for (idx, device) in devices.iter_mut().enumerate() {
            let mut buf = [0u8; 24 * 32];
            match device.file.read(&mut buf) {
                Ok(0) => remove.push(idx),
                Ok(n) => {
                    // Linux x86_64 input_event: timeval16 + type2 + code2 + value4.
                    // Code and value are never logged, persisted, or returned.
                    let activity = buf[..n].chunks_exact(24).any(|ev| {
                        let kind = u16::from_ne_bytes([ev[16], ev[17]]);
                        let value = i32::from_ne_bytes(ev[20..24].try_into().unwrap());
                        (kind == 1 && value > 0) || (kind == 2 && value != 0) || kind == 3
                    });
                    if activity {
                        let now = state.started.elapsed().as_millis() as u64;
                        state.last_human_ms.store(now.max(1), Ordering::SeqCst);
                        let newly_latched = !state.takeover.swap(true, Ordering::SeqCst);
                        // Cancel in-flight work before filesystem I/O. Startup is
                        // always latched, so a failed write cannot permit restart.
                        let epoch = if newly_latched {
                            state.epoch.fetch_add(1, Ordering::SeqCst) + 1
                        } else {
                            state.epoch.load(Ordering::SeqCst)
                        };
                        let source = if device.simulation {
                            "controlled_evdev_simulation"
                        } else {
                            "physical_input_activity"
                        };
                        match state.takeover_marker.lock() {
                            Ok(mut marker) => match marker.set(source, &state.session_id) {
                                Ok(changed) => {
                                    if newly_latched || changed {
                                        record(
                                            &state,
                                            "human_takeover",
                                            json!({"epoch":epoch,"source":source,"takeover_persisted":true}),
                                        );
                                    }
                                }
                                Err(error) => record(
                                    &state,
                                    "takeover_persistence_failed",
                                    json!({"source":source,"error":error,"input_remains_latched":true,"backend_restart_requires_resume":true}),
                                ),
                            },
                            Err(_) => record(
                                &state,
                                "takeover_persistence_failed",
                                json!({"source":source,"error":"Takeover marker lock poisoned","input_remains_latched":true}),
                            ),
                        }
                    }
                }
                Err(e) if e.kind() == io::ErrorKind::WouldBlock => {}
                Err(_) => remove.push(idx),
            }
        }
        for idx in remove.into_iter().rev() {
            devices.remove(idx);
        }
        thread::sleep(Duration::from_millis(5));
    }
}

fn bounded_command(
    state: &State,
    program: &str,
    args: &[String],
    input: Option<&[u8]>,
    timeout: Duration,
    epoch: Option<u64>,
) -> R<Vec<u8>> {
    check_epoch(state, epoch)?;
    let mut cmd = Command::new(program);
    // wl-copy intentionally forks a persistent selection owner. Its child keeps
    // inherited output FDs, so pipe EOF is not an acknowledgement of the setter.
    // This command has no consumed output; ordinary commands retain drained pipes.
    let background_output = program == "wl-copy";
    cmd.args(args)
        .env_remove("NO_AT_BRIDGE")
        .env_remove("ELECTRON_RUN_AS_NODE")
        .process_group(0)
        .stdin(if input.is_some() {
            Stdio::piped()
        } else {
            Stdio::null()
        })
        .stdout(if background_output {
            Stdio::null()
        } else {
            Stdio::piped()
        })
        .stderr(if background_output {
            Stdio::null()
        } else {
            Stdio::piped()
        });
    let mut child = cmd
        .spawn()
        .map_err(|e| format!("{program} unavailable: {e}"))?;
    let pid = child.id();
    let writer = if let Some(bytes) = input {
        let mut p = child.stdin.take().ok_or("Missing child stdin")?;
        let bytes = bytes.to_vec();
        Some(thread::spawn(move || p.write_all(&bytes)))
    } else {
        None
    };
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let out = thread::spawn(move || {
        let mut bytes = Vec::new();
        if let Some(stdout) = stdout {
            stdout.take(32 * 1024 * 1024).read_to_end(&mut bytes)?;
        }
        Ok::<Vec<u8>, io::Error>(bytes)
    });
    let err = thread::spawn(move || {
        let mut bytes = Vec::new();
        if let Some(stderr) = stderr {
            stderr.take(1024 * 1024).read_to_end(&mut bytes)?;
        }
        Ok::<Vec<u8>, io::Error>(bytes)
    });
    let start = Instant::now();
    let mut exit = None;
    let status = loop {
        if let Err(e) = check_epoch(state, epoch) {
            unsafe {
                libc::kill(-(pid as i32), libc::SIGKILL);
            }
            let _ = child.kill();
            let _ = child.wait();
            return Err(e);
        }
        if start.elapsed() > timeout {
            unsafe {
                libc::kill(-(pid as i32), libc::SIGKILL);
            }
            let _ = child.kill();
            let _ = child.wait();
            return Err(format!("{program} timed out"));
        }
        if exit.is_none() {
            exit = child.try_wait().map_err(|e| e.to_string())?;
        }
        if exit.is_some()
            && out.is_finished()
            && err.is_finished()
            && writer.as_ref().is_none_or(|w| w.is_finished())
        {
            break exit.unwrap();
        }
        thread::sleep(Duration::from_millis(5));
    };
    if let Some(writer) = writer {
        writer
            .join()
            .map_err(|_| "Input writer failed")?
            .map_err(|e| format!("{program} stdin failed: {e}"))?;
    }
    let output = out
        .join()
        .map_err(|_| "Output reader failed")?
        .map_err(|e| e.to_string())?;
    let errors = err
        .join()
        .map_err(|_| "Error reader failed")?
        .map_err(|e| e.to_string())?;
    if !status.success() {
        return Err(format!(
            "{program} failed ({status}): {}",
            String::from_utf8_lossy(&errors)
                .chars()
                .take(400)
                .collect::<String>()
        ));
    }
    Ok(output)
}

fn niri(state: &State, kind: &str) -> R<Value> {
    niri_epoch(state, kind, None)
}
fn niri_epoch(state: &State, kind: &str, epoch: Option<u64>) -> R<Value> {
    let out = bounded_command(
        state,
        "niri",
        &["msg".into(), "-j".into(), kind.into()],
        None,
        Duration::from_secs(3),
        epoch,
    )?;
    serde_json::from_slice(&out).map_err(|e| format!("Niri {kind} response invalid: {e}"))
}

fn focused(windows: &Value) -> Option<Value> {
    windows
        .as_array()
        .and_then(|ws| ws.iter().find(|w| w["is_focused"].as_bool() == Some(true)))
        .cloned()
}
fn identity(window: &Value) -> Value {
    json!({"id":window["id"],"pid":window["pid"],"app_id":window["app_id"],"workspace_id":window["workspace_id"],"layout":window["layout"],"is_floating":window["is_floating"]})
}

fn system_monotonic_ms() -> Option<f64> {
    let mut t = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut t) } == 0 {
        Some(t.tv_sec as f64 * 1000.0 + t.tv_nsec as f64 / 1_000_000.0)
    } else {
        None
    }
}
fn record(state: &State, event: &str, data: Value) {
    let v = json!({"schema":1,"monotonic_ms":state.started.elapsed().as_secs_f64()*1000.0,"monotonic_system_ms":system_monotonic_ms(),"event":event,"data":data});
    if let Ok(mut file) = state.log.lock() {
        let _ = writeln!(file, "{v}");
        let _ = file.flush();
    }
}

fn capture_unavailable(state: &State, epoch: u64, category: &str) {
    // A scoped cancellation/deadline is not evidence of global capture failure.
    if own_canceled() || deadline_elapsed() || state.epoch.load(Ordering::SeqCst) != epoch {
        return;
    }
    state.capture_available.store(false, Ordering::SeqCst);
    let next = state.epoch.fetch_add(1, Ordering::SeqCst) + 1;
    if let Ok(mut saved) = state.observations.lock() {
        for obs in saved.values() {
            let _ = fs::remove_file(&obs.image);
            let _ = fs::remove_file(&obs.view_image);
        }
        saved.clear();
    }
    if let Ok(mut targets) = state.semantic_targets.lock() {
        targets.clear();
    }
    record(
        state,
        "capture_unavailable",
        json!({"epoch":next,"category":category,"old_observations_invalidated":true,"new_successful_capture_required":true}),
    );
}
fn capture(
    state: &State,
    output: &str,
    path: &Path,
    id: &str,
    timeout: Duration,
    epoch: u64,
) -> R<()> {
    record(
        state,
        "capture_request",
        json!({"observation_id":id,"output":output}),
    );
    let started = Instant::now();
    if bounded_command(
        state,
        "grim",
        &[
            "-l".into(),
            "1".into(),
            "-s".into(),
            "1".into(),
            "-o".into(),
            output.into(),
            path.to_string_lossy().into(),
        ],
        None,
        timeout,
        Some(epoch),
    )
    .is_err()
    {
        if own_canceled() || deadline_elapsed() || state.epoch.load(Ordering::SeqCst) != epoch {
            return check_epoch(state, Some(epoch));
        }
        capture_unavailable(state, epoch, "capture_process_failed");
        return Err("Capture backend failed/unavailable; old observations and semantic handles invalidated. No further input allowed until desktop_observe succeeds.".into());
    }
    record(
        state,
        "capture_complete",
        json!({"observation_id":id,"capture_ms":started.elapsed().as_secs_f64()*1000.0}),
    );
    Ok(())
}

fn png_size(path: &Path) -> R<(u32, u32)> {
    let mut f = fs::File::open(path).map_err(|e| e.to_string())?;
    let mut b = [0u8; 24];
    f.read_exact(&mut b).map_err(|e| e.to_string())?;
    if &b[..8] != b"\x89PNG\r\n\x1a\n" {
        return Err("Capture is not PNG".into());
    }
    Ok((
        u32::from_be_bytes(b[16..20].try_into().unwrap()),
        u32::from_be_bytes(b[20..24].try_into().unwrap()),
    ))
}

struct Pixels {
    width: u32,
    height: u32,
    channels: usize,
    bytes: Vec<u8>,
}
fn view_point(obs: &Observation, x: f64, y: f64) -> R<()> {
    if !x.is_finite()
        || !y.is_finite()
        || x < 0.0
        || y < 0.0
        || x >= obs.view.width as f64
        || y >= obs.view.height as f64
    {
        return Err("Pointer coordinate outside displayed observation view; no input sent".into());
    }
    Ok(())
}
fn preflight(obs: &Observation, action: &Action) -> R<()> {
    match action {
        Action::Move { x, y } | Action::Click { x, y, .. } | Action::Scroll { x, y, .. } => {
            view_point(obs, *x, *y)?
        }
        Action::Drag {
            x, y, to_x, to_y, ..
        } => {
            view_point(obs, *x, *y)?;
            view_point(obs, *to_x, *to_y)?;
        }
        _ => {}
    }
    match action {
        Action::Click{button:b,count,..}=>{button(b)?;if count.is_some_and(|n|n==0||n>3){return Err("Click count must be 1..3; no input sent".into());}},
        Action::Scroll{dx,dy,..} if (*dx==0&&*dy==0)||dx.unsigned_abs()>100||dy.unsigned_abs()>100=>return Err("Scroll needs a nonzero dx/dy within -100..100 wheel steps; no input sent".into()),
        Action::Drag{duration_ms:Some(ms),..} if !(50..=3000).contains(ms)=>return Err("Drag duration_ms must be 50..3000; no input sent".into()),
        Action::Key{keys,key_scope}=>preflight_keys(keys,*key_scope)?,
        Action::SemanticSetValue{handle_id,text,expected_text}=>{if handle_id.is_empty()||handle_id.len()>128||text.len()>65536||expected_text.as_ref().is_some_and(|t|t.len()>65536){return Err("Semantic handle/text exceeds bounded schema; no input sent".into());}},
        Action::SemanticClick{handle_id,action_name}=>{if handle_id.is_empty()||handle_id.len()>128||action_name.is_empty()||action_name.len()>128{return Err("Semantic handle/action name invalid; no input sent".into());}},
        Action::Type{text,..}|Action::Paste{text,..} if text.len()>65536=>return Err("Text exceeds 64 KiB; no input sent".into()),
        Action::Type{text,text_method:TextMethod::Keyboard} if text.chars().count()>1000=>return Err("Explicit keyboard typing is limited to 1000 characters for the calibrated 8s budget; use text_method=clipboard/auto for longer input".into()),
        Action::Wait{ms} if *ms>10000=>return Err("Wait exceeds 10 seconds; reobserve instead".into()),
        _=>{},
    }
    Ok(())
}
fn png_pixels(path: &Path) -> R<Pixels> {
    let file = fs::File::open(path).map_err(|e| format!("Guard image unavailable: {e}"))?;
    let mut decoder = png::Decoder::new(BufReader::new(file));
    decoder.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut reader = decoder
        .read_info()
        .map_err(|e| format!("Guard PNG decode failed: {e}"))?;
    let size = reader
        .output_buffer_size()
        .ok_or("Guard PNG size overflow")?;
    if size > 128 * 1024 * 1024 {
        return Err("Guard PNG exceeds 128MiB".into());
    }
    let mut bytes = vec![0; size];
    let info = reader
        .next_frame(&mut bytes)
        .map_err(|e| format!("Guard PNG pixels unavailable: {e}"))?;
    let channels = match info.color_type {
        png::ColorType::Rgb => 3,
        png::ColorType::Rgba => 4,
        png::ColorType::Grayscale => 1,
        png::ColorType::GrayscaleAlpha => 2,
        _ => return Err("Unsupported guard PNG color type".into()),
    };
    bytes.truncate(info.buffer_size());
    Ok(Pixels {
        width: info.width,
        height: info.height,
        channels,
        bytes,
    })
}

fn visual_guard(state: &State, obs: &Observation, action: &Action, epoch: u64) -> R<Value> {
    preflight(obs, action)?;
    let points = match action {
        Action::Click { x, y, .. } | Action::Scroll { x, y, .. } => vec![(*x, *y)],
        Action::Drag {
            x, y, to_x, to_y, ..
        } => vec![(*x, *y), (*to_x, *to_y)],
        _ => return Ok(json!({"applied":false})),
    };
    let start = Instant::now();
    check_epoch(state, Some(epoch))?;
    let prior = png_pixels(&obs.image).map_err(|_| {
        capture_unavailable(state, epoch, "prior_image_unavailable");
        "Prior capture artifact unavailable; fresh observation required".to_string()
    })?;
    let path = state.image_dir.join(format!(
        "guard-{}.png",
        state.serial.fetch_add(1, Ordering::SeqCst)
    ));
    let capture_start = Instant::now();
    capture(
        state,
        &obs.output,
        &path,
        &obs.id,
        Duration::from_secs(5),
        epoch,
    )?;
    let capture_ms = capture_start.elapsed().as_secs_f64() * 1000.0;
    let current = png_pixels(&path);
    let _ = fs::remove_file(&path);
    let current = current.map_err(|_| {
        capture_unavailable(state, epoch, "capture_decode_failed");
        "Capture PNG decode failed; fresh observation required".to_string()
    })?;
    if (prior.width, prior.height, prior.channels)
        != (current.width, current.height, current.channels)
    {
        return Err("Screenshot dimensions/color frame changed; no pointer input sent".into());
    }
    check_epoch(state, Some(epoch))?;
    let mut regions = Vec::new();
    for (x, y) in points {
        let x = x + obs.view.x as f64;
        let y = y + obs.view.y as f64;
        if !x.is_finite()
            || !y.is_finite()
            || x < 0.0
            || y < 0.0
            || x >= prior.width as f64
            || y >= prior.height as f64
        {
            return Err("Pointer target outside observed screenshot; no input sent".into());
        }
        let left = (x.floor() as u32).saturating_sub(16);
        let top = (y.floor() as u32).saturating_sub(16);
        let right = ((x.floor() as u32) + 17).min(prior.width);
        let bottom = ((y.floor() as u32) + 17).min(prior.height);
        let mut changed = 0usize;
        let mut count = 0usize;
        for yy in top..bottom {
            for xx in left..right {
                let idx = ((yy as usize) * (prior.width as usize) + (xx as usize)) * prior.channels;
                // Ignore alpha; tolerate tiny compositor/antialias noise only.
                let rgb = if prior.channels < 3 { 1 } else { 3 };
                if (0..rgb).any(|c| prior.bytes[idx + c].abs_diff(current.bytes[idx + c]) > 12) {
                    changed += 1;
                }
                count += 1;
            }
        }
        let fraction = changed as f64 / (count.max(1) as f64);
        regions.push(json!({"x":left,"y":top,"width":right-left,"height":bottom-top,"changed_fraction":fraction}));
        if fraction > 0.02 {
            record(
                state,
                "stale_visual_target",
                json!({"observation_id":obs.id,"changed_fraction":fraction,"guard_capture_ms":capture_ms,"guard_total_ms":start.elapsed().as_secs_f64()*1000.0}),
            );
            return Err(format!("Visual target changed in fresh 33px region ({:.1}% pixels); no pointer input sent. Observe again and ground the new target.",fraction*100.0));
        }
    }
    let result = json!({"applied":true,"guard_capture_ms":capture_ms,"guard_total_ms":start.elapsed().as_secs_f64()*1000.0,"regions":regions});
    record(
        state,
        "visual_guard",
        json!({"observation_id":obs.id,"capture_ms":capture_ms,"total_ms":start.elapsed().as_secs_f64()*1000.0}),
    );
    Ok(result)
}

fn crop_png(source: &Path, destination: &Path, crop: &Crop) -> R<()> {
    let pixels = png_pixels(source)?;
    if crop.width == 0
        || crop.height == 0
        || crop
            .x
            .checked_add(crop.width)
            .is_none_or(|v| v > pixels.width)
        || crop
            .y
            .checked_add(crop.height)
            .is_none_or(|v| v > pixels.height)
    {
        return Err("Crop is outside actual screenshot dimensions".into());
    }
    let mut bytes =
        Vec::with_capacity(crop.width as usize * crop.height as usize * pixels.channels);
    for y in crop.y..crop.y + crop.height {
        let start = (y as usize * pixels.width as usize + crop.x as usize) * pixels.channels;
        bytes
            .extend_from_slice(&pixels.bytes[start..start + crop.width as usize * pixels.channels]);
    }
    let file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(destination)
        .map_err(|e| e.to_string())?;
    let mut encoder = png::Encoder::new(io::BufWriter::new(file), crop.width, crop.height);
    encoder.set_color(match pixels.channels {
        1 => png::ColorType::Grayscale,
        2 => png::ColorType::GrayscaleAlpha,
        3 => png::ColorType::Rgb,
        _ => png::ColorType::Rgba,
    });
    encoder.set_depth(png::BitDepth::Eight);
    encoder.set_compression(png::Compression::Fast);
    encoder
        .write_header()
        .map_err(|e| e.to_string())?
        .write_image_data(&bytes)
        .map_err(|e| e.to_string())
}

fn text_result(data: Value) -> Value {
    json!({"content":[{"type":"text","text":data.to_string()}],"isError":false})
}
fn error_result(message: String) -> Value {
    json!({"content":[{"type":"text","text":json!({"schema":1,"status":"failed","error":message}).to_string()}],"isError":true})
}

fn observe(state: &State, args: &Value) -> R<Value> {
    observe_inner(state, args, false)
}
fn observe_inner(state: &State, args: &Value, actor_held: bool) -> R<Value> {
    let start = Instant::now();
    let epoch = state.epoch.load(Ordering::SeqCst);
    record(state, "observe_request", json!({"epoch":epoch}));
    // Observe shares the actuator lock so images never race a running batch.
    let _actor = if actor_held {
        None
    } else {
        Some(state.actor.lock().map_err(|_| "Actuator lock poisoned")?)
    };
    let windows = niri_epoch(state, "windows", Some(epoch))?;
    let outputs = niri_epoch(state, "outputs", Some(epoch))?;
    let workspaces = niri_epoch(state, "workspaces", Some(epoch))?;
    let focus = focused(&windows);
    let name = args["output"]
        .as_str()
        .map(str::to_owned)
        .or_else(|| {
            workspaces
                .as_array()
                .and_then(|w| w.iter().find(|v| v["is_focused"] == true))
                .and_then(|w| w["output"].as_str())
                .map(str::to_owned)
        })
        .or_else(|| {
            outputs.as_object().and_then(|o| {
                o.iter()
                    .find(|(_, v)| v["logical"].is_object())
                    .map(|(n, _)| n.clone())
            })
        })
        .ok_or("No enabled Niri output")?;
    let geometry = outputs[&name]["logical"].clone();
    if !geometry.is_object() {
        return Err("Requested output unavailable or disabled".into());
    }
    let id = format!(
        "obs-{}-{}",
        state.session_id,
        state.serial.fetch_add(1, Ordering::SeqCst)
    );
    let image = state.image_dir.join(format!("{id}.png"));
    let capture_start = Instant::now();
    capture(state, &name, &image, &id, Duration::from_secs(8), epoch)?;
    let capture_ms = capture_start.elapsed().as_secs_f64() * 1000.0;
    let capture_at = Instant::now();
    fs::set_permissions(&image, fs::Permissions::from_mode(0o600)).map_err(|e| e.to_string())?;
    let (width, height) = png_size(&image).map_err(|_| {
        capture_unavailable(state, epoch, "capture_header_failed");
        "Capture PNG header invalid; fresh observation required".to_string()
    })?;
    let view = if args["crop"].is_object() {
        serde_json::from_value::<Crop>(args["crop"].clone())
            .map_err(|e| format!("Invalid crop: {e}"))?
    } else {
        Crop {
            x: 0,
            y: 0,
            width,
            height,
        }
    };
    let view_image = if args["crop"].is_object() {
        let path = state.image_dir.join(format!("{id}-crop.png"));
        crop_png(&image, &path, &view)?;
        path
    } else {
        image.clone()
    };
    let data = json!({"schema":1,"observation_id":id,"epoch":epoch,"global_keyboard":global_keyboard_capability(),"observed_unix_ms":SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis(),"monotonic_ms":state.started.elapsed().as_secs_f64()*1000.0,"monotonic_system_ms":system_monotonic_ms(),"expires_after_ms":60000,"desktop":"niri-wayland","focused_window":focus,"windows":windows,"workspaces":workspaces,"outputs":outputs,"capture":{"output":name,"path":image,"mime_type":"image/png","image_width":width,"image_height":height,"scale":1,"coordinate_frame":"output-local screenshot pixels; origin top-left; dimensions are actual PNG dimensions and may differ by rounding from Niri logical size","output_logical":geometry},"capabilities":{"capture":true,"window_focus":true,"pointer":"wlr_virtual_pointer_v2","keyboard":{"shortcuts":"app shortcuts: persistent canonical German evdev Wayland keyboard; keymap refreshed before every chord. key_scope=compositor or chords containing Super/meta/logo use an owned Linux uinput device so Niri compositor bindings can process them; permission/monitor/device-open failures refuse before any batch input. Device creation is a capability side effect; open/write acknowledgement is not UI success","unicode_text":{"auto":"plain clipboard for known Electron app IDs or >1000characters; wtype for shorter text in other apps","keyboard_limit_characters":1000,"max_text_utf8_bytes":65536,"electron_keyboard":"known unreliable due physical DomCode and supplementary Unicode; explicit override requires app-specific proof"}},"clipboard":{"backend":"Rust wlr-data-control helper with an owned user scope","plain_text_restore":"best effort; source ownership checked, no atomic selection CAS; skipped after cancel/takeover","rich_or_nontext_restore":"supported bounded MIME payloads including HTML, COMPOUND_TEXT and original Chromium metadata; no portal handles/password hints","rich_preserve_request":"snapshot same offer before replacement; unknown/oversized/sensitive formats refuse","ignored_transport_mimes":["SAVE_TARGETS"],"holder_lifetime":"separate user scope; source replacement or graphical session shutdown","potential_change_reported_on_failure":true},"semantic_tree":"desktop_semantic: read-only Cua application/PID tree; unique window inventory mapping does not attest node window scope; Cua bounds are not screenshot coordinates","takeover":"explicit or physical-input latch; desktop_resume then fresh observe required"},"timing_ms":{"capture":capture_start.elapsed().as_secs_f64()*1000.0,"observe_total":start.elapsed().as_secs_f64()*1000.0}});
    check_epoch(state, Some(epoch))?;
    if focused(&niri_epoch(state, "windows", Some(epoch))?)
        .as_ref()
        .map(identity)
        != focus.as_ref().map(identity)
        || niri_epoch(state, "outputs", Some(epoch))?[&name]["logical"] != geometry
    {
        return Err("Desktop changed during capture; observe again".into());
    }
    let focus_output = focus
        .as_ref()
        .and_then(|w| w["workspace_id"].as_u64())
        .and_then(|id| {
            workspaces
                .as_array()
                .and_then(|ws| ws.iter().find(|w| w["id"].as_u64() == Some(id)))
        })
        .and_then(|w| w["output"].as_str())
        .map(str::to_owned);
    let obs = Observation {
        id: id.clone(),
        at: capture_at,
        epoch,
        output: name,
        output_geometry: geometry,
        focused_window: focus,
        focus_output,
        image_width: width,
        image_height: height,
        image: image.clone(),
        view: view.clone(),
        view_image: view_image.clone(),
    };
    let mut saved = state
        .observations
        .lock()
        .map_err(|_| "Observation storage poisoned")?;
    if saved.len() >= 64 {
        if let Some(old) = saved.values().min_by_key(|o| o.at).map(|o| o.id.clone()) {
            if let Some(o) = saved.remove(&old) {
                let _ = fs::remove_file(o.image);
                let _ = fs::remove_file(o.view_image);
            }
        }
    }
    saved.insert(id.clone(), obs);
    drop(saved);
    let image_block = if args["include_image"].as_bool() != Some(false) {
        let bytes = fs::read(&view_image).map_err(|e| e.to_string())?;
        Some(json!({"type":"image","mimeType":"image/png","data":STANDARD.encode(bytes)}))
    } else {
        None
    };
    let total_ms = start.elapsed().as_secs_f64() * 1000.0;
    let mut data = data;
    data["timing_ms"]["capture"] = json!(capture_ms);
    data["timing_ms"]["observe_total"] = json!(total_ms);
    data["capture"]["path"] = json!(view_image);
    data["capture"]["reference_path"] = json!(image);
    data["capture"]["full_output_width"] = json!(width);
    data["capture"]["full_output_height"] = json!(height);
    data["capture"]["view"] = json!(view);
    data["capture"]["image_width"] = json!(view.width);
    data["capture"]["image_height"] = json!(view.height);
    data["capture"]["coordinate_frame"]=json!("x/y actions are local to displayed view image. Core adds view.x/y to map to full output PNG; full output dimensions normalize virtual pointer. Never add desktop output origin.");
    state.capture_available.store(true, Ordering::SeqCst);
    record(
        state,
        "observed",
        json!({"observation_id":id,"capture_ms":capture_ms,"total_ms":total_ms}),
    );
    let mut result = text_result(data);
    if let Some(block) = image_block {
        result["content"].as_array_mut().unwrap().push(block);
    }
    Ok(result)
}

fn validate(
    state: &State,
    obs: &Observation,
    window_id: Option<u64>,
    pointer_action: bool,
) -> R<()> {
    if !state.capture_available.load(Ordering::SeqCst) {
        return Err(
            "Capture unavailable; no input allowed until a successful fresh desktop_observe".into(),
        );
    }
    check_epoch(state, Some(obs.epoch))?;
    if obs.at.elapsed() > MAX_AGE {
        return Err("Observation is older than 60 seconds; call desktop_observe again".into());
    }
    let windows = niri_epoch(state, "windows", Some(obs.epoch))?;
    let current = focused(&windows);
    let expected = window_id.or_else(|| obs.focused_window.as_ref().and_then(|w| w["id"].as_u64()));
    if expected.is_none() {
        return Err("Observed desktop has no focused window identity; no input sent. Focus an actual window, then observe again.".into());
    }
    if expected != obs.focused_window.as_ref().and_then(|w| w["id"].as_u64()) {
        return Err(
            "Requested window was not focused in the observation; focus separately then observe"
                .into(),
        );
    }
    if current.as_ref().and_then(|w| w["id"].as_u64()) != expected {
        return Err("Focused window changed; observe and select the window again".into());
    }
    if current.as_ref().map(identity) != obs.focused_window.as_ref().map(identity) {
        return Err("Window identity, workspace or geometry changed; observe again".into());
    }
    if pointer_action {
        if obs.focus_output.as_deref() != Some(obs.output.as_str()) {
            return Err("Captured output does not contain focused target workspace; focus desired window then observe its output".into());
        }
        let workspace_id = current
            .as_ref()
            .and_then(|w| w["workspace_id"].as_u64())
            .ok_or("Focused target has no workspace identity")?;
        let workspaces = niri_epoch(state, "workspaces", Some(obs.epoch))?;
        let workspace = workspaces
            .as_array()
            .and_then(|ws| ws.iter().find(|w| w["id"].as_u64() == Some(workspace_id)))
            .ok_or("Target workspace disappeared")?;
        if workspace["output"].as_str() != Some(obs.output.as_str())
            || workspace["is_focused"] != true
            || workspace["is_active"] != true
            || workspace["active_window_id"].as_u64() != expected
        {
            return Err("Fresh target workspace/output/active-window mapping changed; no pointer input sent. Observe again.".into());
        }
        if niri_epoch(state, "outputs", Some(obs.epoch))?[&obs.output]["logical"]
            != obs.output_geometry
        {
            return Err("Output geometry or scaling changed; stale pointer target rejected".into());
        }
    }
    Ok(())
}

fn delay(state: &State, epoch: u64, ms: u64) -> R<()> {
    let until = Instant::now() + Duration::from_millis(ms);
    while Instant::now() < until {
        check_epoch(state, Some(epoch))?;
        thread::sleep(
            Duration::from_millis(5).min(until.saturating_duration_since(Instant::now())),
        );
    }
    check_epoch(state, Some(epoch))
}

fn uses_global_keyboard(keys: &[String], scope: KeyScope) -> R<bool> {
    let codes = keys
        .iter()
        .map(|key| keyboard::named_evdev(key).map_err(|e| e.to_string()))
        .collect::<R<Vec<_>>>()?;
    Ok(scope == KeyScope::Compositor || global_keyboard::requires_global(&codes))
}
fn validate_german_layout(state: &State, epoch: u64) -> R<()> {
    let layouts = niri_epoch(state, "keyboard-layouts", Some(epoch))?;
    let idx = layouts["current_idx"]
        .as_u64()
        .ok_or("Keyboard layout identity unavailable")? as usize;
    if layouts["names"][idx].as_str() != Some("German") {
        return Err("Canonical shortcut backend is calibrated for default German layout; current layout differs. No key input sent.".into());
    }
    Ok(())
}
fn canonical_keys(
    state: &State,
    obs: &Observation,
    epoch: u64,
    keys: &[String],
    scope: KeyScope,
) -> R<()> {
    canonical_keys_with_pre_dispatch(state, obs, epoch, keys, scope, || Ok(()))
}

fn canonical_keys_with_pre_dispatch(
    state: &State,
    obs: &Observation,
    epoch: u64,
    keys: &[String],
    scope: KeyScope,
    mut pre_dispatch: impl FnMut() -> R<()>,
) -> R<()> {
    preflight_keys(keys, scope)?;
    check_epoch(state, Some(epoch))?;
    validate_german_layout(state, epoch)?;
    let codes: Vec<u32> = keys
        .iter()
        .map(|key| keyboard::named_evdev(key).map_err(|e| e.to_string()))
        .collect::<R<_>>()?;
    if uses_global_keyboard(keys, scope)? {
        let mut saved = state
            .global_keyboard
            .lock()
            .map_err(|_| "Global keyboard lock poisoned")?;
        let kb = saved
            .as_mut()
            .ok_or("Global keyboard was not prepared before batch; no fallback/input sent")?;
        let opened_deadline = Instant::now() + remaining_timeout(Duration::from_secs(3));
        kb.ensure_opened(opened_deadline, || check_epoch(state, Some(epoch)))?;
        // Readiness can wait. The earlier layout read is not sufficient.
        validate_german_layout(state, epoch)?;
        let monitor = state
            .human_monitor
            .lock()
            .map_err(|_| "Human monitor status poisoned")?;
        if monitor["available"].as_bool() != Some(true)
            || monitor["watched_devices"].as_u64().unwrap_or(0) == 0
            || monitor["status"].as_str() == Some("starting")
        {
            return Err(
                "Physical takeover monitor unavailable before global shortcut; no key sent".into(),
            );
        }
        drop(monitor);
        check_epoch(state, Some(epoch))?;
        validate(state, obs, None, false)?;
        pre_dispatch()?;
        let result = (|| {
            for code in &codes {
                check_epoch(state, Some(epoch))?;
                kb.key(
                    *code,
                    true,
                    Instant::now() + remaining_timeout(Duration::from_millis(100)),
                    || check_epoch(state, Some(epoch)),
                )?;
                delay(state, epoch, 8)?;
            }
            delay(state, epoch, 20)?;
            for code in codes.iter().rev() {
                check_epoch(state, Some(epoch))?;
                kb.key(
                    *code,
                    false,
                    Instant::now() + remaining_timeout(Duration::from_millis(100)),
                    || check_epoch(state, Some(epoch)),
                )?;
            }
            check_epoch(state, Some(epoch))
        })();
        let release = kb.release_all();
        return result.and(release);
    }
    let mut saved = state
        .keyboard
        .lock()
        .map_err(|_| "Keyboard lock poisoned")?;
    if saved.is_none() {
        *saved = Some(
            Keyboard::new_timeout(remaining_timeout(Duration::from_secs(1)))
                .map_err(|e| e.to_string())?,
        );
    }
    check_epoch(state, Some(epoch))?;
    let kb = saved.as_mut().unwrap();
    // wtype installs its own temporary virtual keymap. Reassert canonical evdev
    // before every shortcut, not only at initial connection creation.
    kb.refresh_keymap_timeout(remaining_timeout(Duration::from_millis(100)))
        .map_err(|e| e.to_string())?;
    check_epoch(state, Some(epoch))?;
    validate(state, obs, None, false)?;
    // Run contextual checks after keymap refresh and target validation, before
    // the first key press. Epoch/cancellation are checked again for every key.
    pre_dispatch()?;
    let result = (|| {
        for key in keys {
            check_epoch(state, Some(epoch))?;
            kb.key_named(key, true).map_err(|e| e.to_string())?;
            delay(state, epoch, 8)?;
        }
        delay(state, epoch, 20)?;
        for key in keys.iter().rev() {
            check_epoch(state, Some(epoch))?;
            kb.key_named(key, false).map_err(|e| e.to_string())?;
        }
        check_epoch(state, Some(epoch))?;
        kb.sync_timeout(remaining_timeout(Duration::from_millis(100)))
            .map_err(|e| e.to_string())
    })(); // Always release modifiers on cancellation/error.
    let release = kb.release_all().map_err(|e| e.to_string());
    result.and(release)
}
fn preflight_keys(keys: &[String], scope: KeyScope) -> R<()> {
    if keys.is_empty() || keys.len() > 6 {
        return Err("Key needs 1..6 key names, modifiers first".into());
    }
    for k in &keys[..keys.len() - 1] {
        match k.to_ascii_lowercase().as_str() {
            "ctrl" | "control" | "shift" | "alt" | "super" | "meta" | "logo" | "altgr" => {}
            _ => return Err("Supported modifiers: ctrl, shift, alt, super, altgr".into()),
        };
    }
    let mut seen = std::collections::HashSet::new();
    for k in keys {
        let code = keyboard::named_evdev(k).map_err(|e| e.to_string())?;
        if !seen.insert(code) {
            return Err("Duplicate key/modifier in chord; no input sent".into());
        }
    }
    if uses_global_keyboard(keys, scope)? {
        global_keyboard::permission_available()?;
    }
    Ok(())
}

fn button(name: &Option<String>) -> R<Button> {
    match name.as_deref().unwrap_or("left") {
        "left" => Ok(Button::Left),
        "right" => Ok(Button::Right),
        "middle" => Ok(Button::Middle),
        _ => Err("Button must be left, right, or middle".into()),
    }
}
fn atspi_helper(state: &State, request: Value, epoch: u64) -> R<Value> {
    let bytes = serde_json::to_vec(&request).map_err(|e| e.to_string())?;
    if bytes.len() > 2 * 1024 * 1024 {
        return Err("Direct accessibility helper request exceeds private2MiB budget".into());
    }
    let executable = env::current_exe()
        .map_err(|e| e.to_string())?
        .to_string_lossy()
        .into_owned();
    let out = bounded_command(
        state,
        &executable,
        &["__atspi_helper".into()],
        Some(&bytes),
        Duration::from_secs(10),
        Some(epoch),
    )?;
    serde_json::from_slice(&out)
        .map_err(|e| format!("Direct AT-SPI helper returned invalid JSON: {e}"))
}
fn semantic_target(state: &State, obs: &Observation, handle: &str) -> R<SemanticTarget> {
    let target=state.semantic_targets.lock().map_err(|_|"Semantic handle cache poisoned")?.get(handle).cloned().ok_or("Semantic handle unknown; call desktop_semantic_direct first. Foreign Cua/index/object tokens are not accepted.")?;
    check_epoch(state, Some(target.epoch))?;
    if target.at.elapsed() > MAX_AGE {
        return Err("Semantic handle expired; call desktop_semantic_direct again".into());
    }
    if obs.focused_window.as_ref().map(identity) != Some(identity(&target.window)) {
        return Err("Semantic handle belongs to another window identity/layout; focus and observe actual target, then read semantics again".into());
    }
    Ok(target)
}

fn execute(
    state: &State,
    obs: &Observation,
    pointer: &mut Option<Pointer>,
    action: &Action,
    epoch: u64,
    details: &mut Value,
) -> R<()> {
    check_epoch(state, Some(epoch))?;
    if action.pointer() && pointer.is_none() {
        *pointer = Some(
            Pointer::new_timeout(remaining_timeout(Duration::from_secs(1)))
                .map_err(|e| e.to_string())?,
        );
    }
    check_epoch(state, Some(epoch))?;
    if action.pointer() {
        let refresh = Instant::now();
        pointer
            .as_mut()
            .unwrap()
            .refresh_capabilities_timeout(remaining_timeout(Duration::from_millis(100)))
            .map_err(|e| e.to_string())?;
        check_epoch(state, Some(epoch))?;
        validate(state, obs, None, true)?;
        *details = json!({"pointer_backend_refresh_ms":refresh.elapsed().as_secs_f64()*1000.0,"capability_scope":"fresh Wayland globals and Niri focused workspace/output identity"});
    }
    let move_to = |p: &mut Pointer, x: f64, y: f64| {
        check_epoch(state, Some(epoch))?;
        view_point(obs, x, y)?;
        p.move_to(
            &obs.output,
            x + obs.view.x as f64,
            y + obs.view.y as f64,
            obs.image_width,
            obs.image_height,
        )
        .map_err(|e| e.to_string())
    };
    match action {
        Action::Focus { window_id } => {
            bounded_command(
                state,
                "niri",
                &[
                    "msg".into(),
                    "action".into(),
                    "focus-window".into(),
                    "--id".into(),
                    window_id.to_string(),
                ],
                None,
                Duration::from_secs(3),
                Some(epoch),
            )?;
        }
        Action::Move { x, y } => {
            move_to(pointer.as_mut().unwrap(), *x, *y)?;
        }
        Action::Click {
            x,
            y,
            button: b,
            count,
        } => {
            let p = pointer.as_mut().unwrap();
            move_to(p, *x, *y)?;
            for _ in 0..count.unwrap_or(1) {
                check_epoch(state, Some(epoch))?;
                p.button(button(b)?, true).map_err(|e| e.to_string())?;
                delay(state, epoch, 30)?;
                p.button(button(b)?, false).map_err(|e| e.to_string())?;
                delay(state, epoch, 40)?;
            }
        }
        Action::Scroll { x, y, dx, dy } => {
            let p = pointer.as_mut().unwrap();
            move_to(p, *x, *y)?;
            p.scroll_steps(*dx, *dy).map_err(|e| e.to_string())?;
        }
        Action::Drag {
            x,
            y,
            to_x,
            to_y,
            duration_ms,
        } => {
            let p = pointer.as_mut().unwrap();
            move_to(p, *x, *y)?;
            p.button(Button::Left, true).map_err(|e| e.to_string())?;
            let ms = duration_ms.unwrap_or(300).clamp(50, 3000);
            for i in 1..=20 {
                delay(state, epoch, ms / 20)?;
                move_to(
                    p,
                    x + (to_x - x) * i as f64 / 20.0,
                    y + (to_y - y) * i as f64 / 20.0,
                )?;
            }
            p.button(Button::Left, false).map_err(|e| e.to_string())?;
        }
        Action::Type { text, text_method } => {
            if text.len() > 65536 {
                return Err("Text exceeds 64 KiB".into());
            }
            let app = obs
                .focused_window
                .as_ref()
                .and_then(|w| w["app_id"].as_str())
                .unwrap_or("");
            let electron_clipboard = matches!(
                app,
                "code"
                    | "Code"
                    | "com.visualstudio.code"
                    | "com.t3tools.T3Code"
                    | "com.t3tools.T3CodeNightly"
            );
            let clipboard = matches!(text_method, TextMethod::Clipboard)
                || (matches!(text_method, TextMethod::Auto)
                    && (electron_clipboard || text.chars().count() > 1000));
            if clipboard {
                let result = execute(
                    state,
                    obs,
                    pointer,
                    &Action::Paste {
                        text: text.clone(),
                        restore_clipboard: true,
                    },
                    epoch,
                    details,
                );
                details["text_backend"] = json!("owned RAM-only clipboard paste; bounded payload MIME restore; SAVE_TARGETS marker omitted");
                details["text_method_requested"] = json!(match text_method {
                    TextMethod::Auto => "auto",
                    TextMethod::Keyboard => "keyboard",
                    TextMethod::Clipboard => "clipboard",
                });
                result?;
            } else {
                *details = json!({"text_backend":"wtype Unicode keyboard","text_method_requested":match text_method{TextMethod::Auto=>"auto",TextMethod::Keyboard=>"keyboard",TextMethod::Clipboard=>"clipboard"}});
                bounded_command(
                    state,
                    "wtype",
                    &["--".into(), text.clone()],
                    None,
                    Duration::from_secs(8),
                    Some(epoch),
                )?;
            }
        }
        Action::Paste {
            text,
            restore_clipboard,
        } => {
            if text.len() > 65536 {
                return Err("Text exceeds 64 KiB".into());
            }
            check_epoch(state, Some(epoch))?;
            let cancelled = || {
                own_canceled()
                    || state.epoch.load(Ordering::SeqCst) != epoch
                    || state.takeover.load(Ordering::SeqCst)
                    || deadline_elapsed()
            };
            // Publication may precede acknowledgement. Keep this possible
            // effect even when the helper is refused, lost, or cancelled.
            *details = json!({"clipboard_changed_possible":true,"clipboard_changed":false,"restore_requested":restore_clipboard,"restored":false,"clipboard_backend":"owned RAM-only multi-MIME data-control helper in a separate user scope"});
            let executable = env::current_exe().map_err(|e| e.to_string())?;
            let mut lease = clipboard::Lease::begin_in_user_scope(
                Path::new("/run/current-system/sw/bin/systemd-run"),
                &executable,
                &["__clipboard_helper"],
                text,
                *restore_clipboard,
                remaining_timeout(Duration::from_secs(2)),
                cancelled,
            )?;
            details["clipboard_changed"] = json!(true);
            details["clipboard_holder"] = lease.ready.clone();
            let operation = (|| {
                canonical_keys_with_pre_dispatch(
                    state,
                    obs,
                    epoch,
                    &["ctrl".into(), "v".into()],
                    KeyScope::App,
                    || {
                        if !lease
                            .check_owned(remaining_timeout(Duration::from_millis(300)), cancelled)?
                        {
                            return Err(
                                "Clipboard source changed before paste; no Ctrl+V dispatched"
                                    .into(),
                            );
                        }
                        // No keymap/layout/window roundtrip follows this check.
                        // Wayland still has no atomic selection-check-and-paste.
                        Ok(())
                    },
                )?;
                details["paste_dispatched"] = json!(true);
                delay(state, epoch, 250)
            })();
            let restore_allowed = *restore_clipboard && !cancelled();
            // Cleanup IPC consumes the same action deadline. No hidden deadline
            // reset. Abandoning never replaces a new human/foreign selection.
            let restoration = lease.finish(
                restore_allowed,
                remaining_timeout(Duration::from_millis(300)),
                cancelled,
            );
            match restoration {
                Ok(result) => {
                    details["restored"] = json!(result["state"] == "restored");
                    details["clipboard_restoration"] = result;
                }
                Err(error) => {
                    details["restore_error"] = json!(error.clone());
                    if operation.is_ok() {
                        return Err(format!(
                            "Clipboard restoration uncertain after paste: {error}"
                        ));
                    }
                }
            }
            operation?;
        }
        Action::Key { keys, key_scope } => {
            details["key_scope"] = json!(if uses_global_keyboard(keys, *key_scope)? {
                "compositor"
            } else {
                "app"
            });
            details["key_transport"] = json!(if uses_global_keyboard(keys, *key_scope)? {
                "owned_uinput"
            } else {
                "wayland_virtual_keyboard"
            });
            canonical_keys(state, obs, epoch, keys, *key_scope)?;
        }
        Action::SemanticSetValue {
            handle_id,
            text,
            expected_text,
        } => {
            let target = semantic_target(state, obs, handle_id)?;
            validate(state, obs, None, false)?;
            check_epoch(state, Some(epoch))?;
            *details = atspi_helper(
                state,
                json!({"operation":"set_value","snapshot":target.snapshot.as_ref(),"object":target.object,"text":text,"expected_text":expected_text}),
                epoch,
            )?;
            if details["status"] != "buffer_verified" {
                return Err("Direct semantic edit returned uncertain buffer result; inspect new observation and artifact, no retry without new evidence".into());
            }
        }
        Action::SemanticClick {
            handle_id,
            action_name,
        } => {
            let target = semantic_target(state, obs, handle_id)?;
            validate(state, obs, None, false)?;
            check_epoch(state, Some(epoch))?;
            *details = atspi_helper(
                state,
                json!({"operation":"click","snapshot":target.snapshot.as_ref(),"object":target.object,"action_name":action_name}),
                epoch,
            )?;
            if details["accepted"] != true {
                return Err("Direct semantic action refused; no pointer fallback attempted".into());
            }
        }
        Action::Wait { ms } => {
            if *ms > 10000 {
                return Err("Wait exceeds 10 seconds; reobserve instead".into());
            }
            delay(state, epoch, *ms)?;
        }
    }
    if action.pointer() {
        check_epoch(state, Some(epoch))?;
        pointer
            .as_mut()
            .unwrap()
            .sync_timeout(remaining_timeout(Duration::from_millis(100)))
            .map_err(|e| e.to_string())?;
    }
    check_epoch(state, Some(epoch))
}

fn act(state: &State, args: &Value, epoch: u64) -> R<Value> {
    let start = Instant::now();
    if !state.capture_available.load(Ordering::SeqCst) {
        return Err(
            "No successful current capture available; call desktop_observe before input".into(),
        );
    }
    if state.takeover.load(Ordering::SeqCst) {
        return Err(
            "Desktop takeover is latched; call desktop_resume, then observe again before acting"
                .into(),
        );
    }
    let parsed: ActArgs = serde_json::from_value(args.clone())
        .map_err(|e| format!("Invalid action arguments: {e}"))?;
    if let Some(guard) = &parsed.expected_global_backend {
        validate_global_backend_guard(guard, &state.session_id, epoch, &parsed.observation_id)?;
    }
    let timeout = Duration::from_millis(parsed.timeout_ms.unwrap_or(30000).clamp(100, 120000));
    let _deadline = DeadlineGuard::set(Some(start + timeout));
    if parsed.settle_ms > 1000 {
        return Err(
            "settle_ms exceeds 1000ms; use bounded fresh observations for slower states".into(),
        );
    }
    if parsed.actions.is_empty() || parsed.actions.len() > 32 {
        return Err("Batch needs 1..32 typed actions".into());
    }
    if parsed.actions.len() > 1
        && parsed
            .actions
            .iter()
            .any(|a| matches!(a, Action::Focus { .. }))
    {
        return Err(
            "Focus must be a standalone action; observe again before any typing or pointer action"
                .into(),
        );
    }
    let obs = state
        .observations
        .lock()
        .map_err(|_| "Observation storage poisoned")?
        .get(&parsed.observation_id)
        .cloned()
        .ok_or("Observation missing; call desktop_observe first")?;
    // Reject malformed later targets before any earlier batch effects occur.
    for action in &parsed.actions {
        preflight(&obs, action)?;
        match action {
            Action::SemanticSetValue { handle_id, .. }
            | Action::SemanticClick { handle_id, .. } => {
                semantic_target(state, &obs, handle_id)?;
            }
            _ => {}
        }
    }
    let task = parsed
        .task_id
        .unwrap_or_else(|| format!("task-{}", state.serial.fetch_add(1, Ordering::SeqCst)));
    record(
        state,
        "action_batch_request",
        json!({"task_id":task,"epoch":epoch,"action_count":parsed.actions.len()}),
    );
    state.queued.fetch_add(1, Ordering::SeqCst);
    let mut ptr = loop {
        if let Err(e) = check_epoch(state, Some(epoch)) {
            state.queued.fetch_sub(1, Ordering::SeqCst);
            return Err(e);
        }
        match state.actor.try_lock() {
            Ok(lock) => break lock,
            Err(std::sync::TryLockError::WouldBlock) => thread::sleep(Duration::from_millis(5)),
            Err(_) => {
                state.queued.fetch_sub(1, Ordering::SeqCst);
                return Err("Actuator lock poisoned".into());
            }
        }
    };
    state.queued.fetch_sub(1, Ordering::SeqCst);
    check_epoch(state, Some(epoch))?;
    check_epoch(state, Some(obs.epoch))?;
    if state.takeover.load(Ordering::SeqCst) {
        return Err("Desktop takeover is latched; pending batch rejected".into());
    }
    if !state.release_confirmed.load(Ordering::SeqCst) {
        return Err("Previous actuator release/receipt is unconfirmed; no new input allowed. Repair/reconnect own backend and obtain release confirmation before resuming.".into());
    }
    *state
        .active
        .lock()
        .map_err(|_| "Active task lock poisoned")? = json!({"task_id":task,"completed_actions":0,"total_actions":parsed.actions.len(),"epoch":epoch,"phase":"preparing_global_keyboard"});
    state.release_confirmed.store(false, Ordering::SeqCst);
    let mut completed = 0usize;
    let mut effects = Vec::new();
    // Prepare a required global device before ANY earlier batch input. Creation
    // is a documented capability side effect, never an observation side effect.
    // Own event-node open is only a readiness gate, not proof of a UI result.
    let needs_global = parsed.actions.iter().any(|action| match action {
        Action::Key { keys, key_scope } => uses_global_keyboard(keys, *key_scope).unwrap_or(false),
        _ => false,
    });
    let preparation = (|| -> R<()> {
        if needs_global {
            let monitor = state
                .human_monitor
                .lock()
                .map_err(|_| "Human monitor status poisoned")?;
            if monitor["available"].as_bool() != Some(true)
                || monitor["watched_devices"].as_u64().unwrap_or(0) == 0
                || monitor["status"].as_str() == Some("starting")
            {
                return Err(
                "Global keyboard requires an available physical takeover monitor; no input sent"
                    .into(),
            );
            }
            drop(monitor);
            validate(state, &obs, parsed.window_id, false)?;
            let mut saved = state
                .global_keyboard
                .lock()
                .map_err(|_| "Global keyboard lock poisoned")?;
            let deadline = Instant::now() + remaining_timeout(Duration::from_secs(3));
            if saved.is_none() {
                *saved = Some(global_keyboard::GlobalKeyboard::prepare(deadline, || {
                    check_epoch(state, Some(epoch))
                })?);
            }
            saved
                .as_mut()
                .unwrap()
                .ensure_opened(deadline, || check_epoch(state, Some(epoch)))?;
            check_epoch(state, Some(epoch))?;
            validate(state, &obs, parsed.window_id, false)?;
        }
        Ok(())
    })();
    let mut failure = preparation.err();
    if failure.is_none() {
        *state
            .active
            .lock()
            .map_err(|_| "Active task lock poisoned")? = json!({"task_id":task,"completed_actions":0,"total_actions":parsed.actions.len(),"epoch":epoch,"phase":"executing"});
    }
    for action in &parsed.actions {
        if failure.is_some() {
            break;
        }
        let step = Instant::now();
        let mut dispatched = false;
        let mut guard = Value::Null;
        let mut details = Value::Null;
        let result = (|| {
            check_epoch(state, Some(epoch))?;
            if state.takeover.load(Ordering::SeqCst) {
                return Err("Human desktop takeover; pending actions stopped".into());
            }
            if start.elapsed() > timeout {
                return Err("Action batch timed out".into());
            }
            if !matches!(action, Action::Focus { .. } | Action::Wait { .. }) {
                validate(state, &obs, parsed.window_id, action.pointer())?;
            }
            if action.pointer() {
                guard = visual_guard(state, &obs, action, epoch)?;
                validate(state, &obs, parsed.window_id, true)?;
            }
            dispatched = true;
            record(
                state,
                "action_dispatch",
                json!({"task_id":task,"kind":action.name()}),
            );
            execute(state, &obs, &mut ptr, action, epoch, &mut details)
        })();
        let ok = result.is_ok();
        effects.push(json!({"kind":action.name(),"dispatch_started":dispatched,"acknowledged":ok,"may_have_partial_effects":!ok && dispatched && !matches!(action,Action::Wait{..}),"details":details,"visual_guard":guard,"dispatch_ack_ms":step.elapsed().as_secs_f64()*1000.0}));
        record(
            state,
            "action",
            json!({"task_id":task,"kind":action.name(),"acknowledged":ok,"latency_ms":step.elapsed().as_secs_f64()*1000.0}),
        );
        if let Err(error) = result {
            failure = Some(error);
            break;
        }
        completed += 1;
        *state
            .active
            .lock()
            .map_err(|_| "Active task lock poisoned")? = json!({"task_id":task,"completed_actions":completed,"total_actions":parsed.actions.len(),"epoch":epoch});
    }
    // A canceled drag/click always releases held buttons before the actor is free.
    let mut cleanup_ok = true;
    if let Some(p) = ptr.as_mut() {
        if let Err(e) = p
            .release_all()
            .and_then(|_| p.sync_timeout(Duration::from_millis(100)))
        {
            cleanup_ok = false;
            if failure.is_none() {
                failure = Some(format!("Button release/receipt failed: {e}"));
            }
        }
    }
    if let Ok(mut kb) = state.keyboard.lock() {
        if let Some(k) = kb.as_mut() {
            if let Err(e) = k
                .release_all()
                .and_then(|_| k.sync_timeout(Duration::from_millis(100)))
            {
                cleanup_ok = false;
                if failure.is_none() {
                    failure = Some(format!("Keyboard release/receipt failed: {e}"));
                }
            }
        }
    } else {
        cleanup_ok = false;
    }
    if let Ok(mut keyboard) = state.global_keyboard.lock() {
        if let Some(keyboard) = keyboard.as_mut() {
            if let Err(error) = keyboard.release_all() {
                cleanup_ok = false;
                if failure.is_none() {
                    failure = Some(format!("Global keyboard release failed: {error}"));
                }
            }
        }
    } else {
        cleanup_ok = false;
    }
    state.release_confirmed.store(cleanup_ok, Ordering::SeqCst);
    *state
        .active
        .lock()
        .map_err(|_| "Active task lock poisoned")? = Value::Null;
    let dispatch_ms = start.elapsed().as_secs_f64() * 1000.0;
    let mut after = None;
    let mut after_error = None;
    let after_start = Instant::now();
    let mut settle_wait_ms = 0.0;
    if parsed.observe_after
        && failure.is_none()
        && !own_canceled()
        && state.epoch.load(Ordering::SeqCst) == epoch
    {
        let mut observe_args = json!({"include_image":parsed.include_image});
        if !parsed
            .actions
            .iter()
            .any(|a| matches!(a, Action::Focus { .. }))
        {
            observe_args["output"] = json!(obs.output);
            if obs.view.x != 0
                || obs.view.y != 0
                || obs.view.width != obs.image_width
                || obs.view.height != obs.image_height
            {
                observe_args["crop"] = json!(obs.view);
            }
        }
        // Buttons/keys have been released, but retain writer ownership through
        // this capture so another queued action cannot change its result first.
        let settle_started = Instant::now();
        let settled = delay(state, epoch, parsed.settle_ms);
        settle_wait_ms = settle_started.elapsed().as_secs_f64() * 1000.0;
        match settled.and_then(|_| observe_inner(state, &observe_args, true)) {
            Ok(v) => after = Some(v),
            Err(e) => after_error = Some(e),
        }
    }
    let canceled = state.epoch.load(Ordering::SeqCst) != epoch || own_canceled();
    let mut data = json!({"schema":1,"task_id":task,"status":if canceled{"canceled"}else if failure.is_some(){"failed"}else{"dispatched"},"completed_actions":completed,"requested_actions":parsed.actions.len(),"effects":effects,"error":failure,"actor_release_confirmed":cleanup_ok,"timing_ms":{"dispatch_and_release":dispatch_ms,"post_action_settle_wait":settle_wait_ms,"post_observe":after_start.elapsed().as_secs_f64()*1000.0},"total_ms":start.elapsed().as_secs_f64()*1000.0,"after_observation_error":after_error,"verification":"Input acknowledgement only. after_observation is fresh evidence to inspect, not inferred UI success. Verify the expected UI state or independent artifact before reporting success."});
    let mut image_blocks = Vec::new();
    if let Some(after) = after {
        if let Some(content) = after["content"].as_array() {
            for block in content {
                if block["type"] == "text" {
                    if let Some(text) = block["text"].as_str() {
                        data["after_observation"] = serde_json::from_str(text)
                            .map_err(|e| format!("Internal post-observation invalid: {e}"))?;
                    }
                } else {
                    image_blocks.push(block.clone());
                }
            }
        }
    }
    *state
        .last_result
        .lock()
        .map_err(|_| "Last result state poisoned")? = data.clone();
    let failed = data["status"] == "failed" || data["status"] == "canceled";
    let mut result = text_result(data);
    result["isError"] = json!(failed);
    result["content"]
        .as_array_mut()
        .unwrap()
        .extend(image_blocks);
    Ok(result)
}

fn semantic(state: &State, args: &Value) -> R<Value> {
    let start = Instant::now();
    let id = args["window_id"]
        .as_u64()
        .ok_or("desktop_semantic requires Niri window_id")?;
    let windows = niri(state, "windows")?;
    let win = windows
        .as_array()
        .and_then(|ws| ws.iter().find(|w| w["id"].as_u64() == Some(id)))
        .ok_or("Requested Niri window is gone")?;
    let pid = win["pid"]
        .as_u64()
        .ok_or("Niri window has no PID; refusing guessed Cua mapping")?;
    let title = win["title"].as_str().unwrap_or("");
    let raw = bounded_command(
        state,
        "cua-driver",
        &["call".into(), "list_windows".into(), "{}".into()],
        None,
        Duration::from_secs(4),
        None,
    )?;
    let listed: Value =
        serde_json::from_slice(&raw).map_err(|e| format!("Cua list_windows invalid: {e}"))?;
    let matches: Vec<&Value> = listed["windows"]
        .as_array()
        .ok_or("Cua windows unavailable")?
        .iter()
        .filter(|w| {
            if w["pid"].as_u64() != Some(pid) {
                return false;
            }
            let cua_title = w["title"].as_str().unwrap_or("");
            let app = w["app_name"].as_str().unwrap_or("");
            cua_title == title
                || (!app.is_empty()
                    && cua_title
                        .strip_suffix(&format!(" [{app}]"))
                        .is_some_and(|s| s == title))
        })
        .collect();
    if matches.len() != 1 {
        return Err(format!("Cua mapping needs exactly one matching PID+title; found {}. Use visual observation rather than guessed synthetic window IDs.",matches.len()));
    }
    let cua = matches[0];
    let cua_id = cua["window_id"]
        .as_u64()
        .ok_or("Cua window lacks numeric synthetic ID")?;
    let max_elements = args["max_elements"].as_u64().unwrap_or(500).clamp(1, 1000);
    let max_depth = args["max_depth"].as_u64().unwrap_or(24).clamp(1, 40);
    let params = json!({"pid":pid,"window_id":cua_id,"include_screenshot":false,"max_elements":max_elements,"max_depth":max_depth});
    let raw = bounded_command(
        state,
        "cua-driver",
        &["call".into(), "get_window_state".into(), params.to_string()],
        None,
        Duration::from_secs(8),
        None,
    )?;
    let tree: Value =
        serde_json::from_slice(&raw).map_err(|e| format!("Cua get_window_state invalid: {e}"))?;
    let fresh = niri(state, "windows")?;
    if fresh
        .as_array()
        .and_then(|ws| ws.iter().find(|w| w["id"].as_u64() == Some(id)))
        .map(identity)
        != Some(identity(win))
    {
        return Err("Window identity/layout changed during semantic capture; reobserve".into());
    }
    let query = args["query"].as_str().map(|s| s.to_lowercase());
    let mut elements = tree["elements"].as_array().cloned().unwrap_or_default();
    let available = elements.len() > 1 || tree["total_element_count"].as_u64().unwrap_or(0) > 1;
    for elem in &mut elements {
        if elem["role"].as_str().is_some_and(|r| {
            r.to_lowercase().contains("password") || r.to_lowercase().contains("securetext")
        }) || elem["is_password"] == true
            || elem["protected"] == true
        {
            *elem = json!({"role":elem["role"],"bounds":elem["bounds"],"element_token":elem["element_token"],"label":"[protected field]","protected_content_redacted":true});
        }
    }
    if let Some(q) = query {
        elements.retain(|e| e.to_string().to_lowercase().contains(&q));
    }
    Ok(text_result(
        json!({"schema":1,"status":if available{"available"}else{"limited"},"niri_window_id":id,"pid":pid,"title":title,"cua_synthetic_window_id":cua_id,"snapshot_id":tree["snapshot_id"],"elements_complete":tree["elements_complete"],"total_element_count":tree.get("total_element_count").filter(|v|v.is_number()).unwrap_or(&tree["element_count"]),"returned_element_count":elements.len(),"elements":elements,"semantic_scope":"application/PID; exact window scoping is not attested by Cua0.23.2. Unique inventory mapping identifies the requested window but does not prove every returned node belongs to it","coordinate_frame":"Cua accessibility bounds are app/window-local and may be inaccurate. They are NOT Niri output screenshot coordinates; do not directly click them. Match semantic intent to fresh visual screenshot until a mapping is explicitly calibrated.","latency_ms":start.elapsed().as_secs_f64()*1000.0,"note":tree["_note"]}),
    ))
}

fn semantic_direct(state: &State, args: &Value) -> R<Value> {
    let started = Instant::now();
    let epoch = state.epoch.load(Ordering::SeqCst);
    let id = args["window_id"]
        .as_u64()
        .ok_or("Niri window_id required")?;
    let _actor = loop {
        check_epoch(state, Some(epoch))?;
        match state.actor.try_lock() {
            Ok(lock) => break lock,
            Err(std::sync::TryLockError::WouldBlock) => thread::sleep(Duration::from_millis(5)),
            Err(_) => return Err("Actuator lock poisoned".into()),
        }
    };
    let windows = niri_epoch(state, "windows", Some(epoch))?;
    let window = windows
        .as_array()
        .and_then(|ws| ws.iter().find(|w| w["id"].as_u64() == Some(id)))
        .cloned()
        .ok_or("Requested Niri window disappeared")?;
    let pid = window["pid"].as_u64().ok_or("Niri target has no PID")?;
    let title = window["title"].as_str().unwrap_or("");
    let sole_window = windows
        .as_array()
        .is_some_and(|ws| ws.iter().filter(|w| w["pid"].as_u64() == Some(pid)).count() == 1);
    let raw = atspi_helper(
        state,
        json!({"operation":"observe","pid":pid,"title":title,"single_window":sole_window,"max_nodes":args["max_elements"].as_u64().unwrap_or(1000).clamp(1,1000),"max_depth":args["max_depth"].as_u64().unwrap_or(40).clamp(1,40)}),
        epoch,
    )?;
    let snapshot: atspi::Snapshot = serde_json::from_value(raw["snapshot"].clone())
        .map_err(|e| format!("Direct semantic snapshot invalid: {e}"))?;
    if niri_epoch(state, "windows", Some(epoch))?
        .as_array()
        .and_then(|ws| ws.iter().find(|w| w["id"].as_u64() == Some(id)))
        .map(identity)
        != Some(identity(&window))
    {
        return Err("Niri target changed during semantic capture; reobserve".into());
    }
    check_epoch(state, Some(epoch))?;
    let snapshot = Arc::new(snapshot);
    let snapshot_id = format!(
        "ax-snapshot-{}-{}",
        state.session_id,
        state.serial.fetch_add(1, Ordering::SeqCst)
    );
    let handles: HashMap<atspi::Object, String> = snapshot
        .nodes
        .iter()
        .filter(|n| !n.protected && snapshot.complete)
        .map(|n| {
            (
                n.object.clone(),
                format!(
                    "ax-{}-{}",
                    state.session_id,
                    state.serial.fetch_add(1, Ordering::SeqCst)
                ),
            )
        })
        .collect();
    let mut cache = state
        .semantic_targets
        .lock()
        .map_err(|_| "Semantic handle cache poisoned")?;
    cache.retain(|_, t| t.epoch == epoch && t.at.elapsed() < MAX_AGE);
    if cache.len() + handles.len() > 2048 {
        cache.clear();
    }
    let mut elements = Vec::new();
    for node in &snapshot.nodes {
        let handle = handles.get(&node.object);
        if let Some(handle) = handle {
            cache.insert(
                handle.clone(),
                SemanticTarget {
                    at: Instant::now(),
                    epoch,
                    window: window.clone(),
                    snapshot: snapshot.clone(),
                    object: node.object.clone(),
                },
            );
        }
        let has = |interface: &str| node.interfaces.iter().any(|s| s == interface);
        let has_state = |bit: usize| {
            node.states
                .get(bit / 32)
                .is_some_and(|word| word & (1 << (bit % 32)) != 0)
        };
        let editable = has_state(7);
        let enabled = has_state(8) && has_state(24) && !has_state(3) && !has_state(6);
        let showing = has_state(25);
        elements.push(json!({"handle_id":handle,"parent_handle_id":node.parent.as_ref().and_then(|p|handles.get(p)),"depth":node.depth,"role":node.role,"label":node.name,"description":node.description,"interfaces":node.interfaces,"states":node.states,"protected":node.protected,"text_excerpt":node.text_excerpt,"action_names":node.action_names,"editable":editable,"enabled":enabled,"showing":showing,"capabilities":{"set_value":handle.is_some()&&has("org.a11y.atspi.EditableText")&&editable&&enabled&&showing,"click":handle.is_some()&&!node.action_names.is_empty()&&enabled&&showing},"coordinates":"none; semantic object targeting only"}));
    }
    if let Some(query) = args["query"].as_str() {
        let query = query.to_lowercase();
        elements.retain(|n| n.to_string().to_lowercase().contains(&query));
    }
    Ok(text_result(
        json!({"schema":1,"status":if snapshot.complete{"available"}else{"limited"},"niri_window_id":id,"epoch":epoch,"pid":pid,"title":title,"semantic_snapshot_id":snapshot_id,"elements_complete":snapshot.complete,"returned_element_count":elements.len(),"total_element_count":snapshot.nodes.len(),"elements":elements,"semantic_scope":snapshot.semantic_scope,"visibility_traversal":snapshot.visibility_traversal,"coordinate_frame":"No pixel bounds exported; direct typed actions use daemon-owned opaque handles only. Cua tokens and raw D-Bus paths are not accepted.","expires_after_ms":60000,"note":"Mutations freshly validate immutable bus generation/unique owner, object role/name/description/interfaces, observed ancestry, the defined SHOWING-ancestor-chain semantic context, enabled/showing state and modal set. Incomplete snapshots are read-only. set_value requires expected complete prior text or a complete matching512char excerpt; exact saved artifact remains independently verified.","latency_ms":started.elapsed().as_secs_f64()*1000.0}),
    ))
}

fn handle(state: &State, tool: &str, args: &Value, epoch: u64) -> R<Value> {
    match tool {
        "desktop_status" => Ok(text_result(
            json!({"schema":1,"version":"0.1.0","session_id":state.session_id,"interface_revision":GLOBAL_ROUTING_REVISION,"global_keyboard":global_keyboard_capability(),"desktop":"niri-wayland","epoch":state.epoch.load(Ordering::SeqCst),"queued_batches":state.queued.load(Ordering::SeqCst),"active":*state.active.lock().map_err(|_|"Active state poisoned")?,"last_result":*state.last_result.lock().map_err(|_|"Last result state poisoned")?,"actor_release_confirmed":state.release_confirmed.load(Ordering::SeqCst),"capture_available":state.capture_available.load(Ordering::SeqCst),"fresh_observation_required_after_capture_failure":true,"uptime_ms":state.started.elapsed().as_millis(),"takeover_latched":state.takeover.load(Ordering::SeqCst),"takeover_persistence":state.takeover_marker.lock().map_err(|_|"Takeover marker state poisoned")?.status(),"human_input_monitor":*state.human_monitor.lock().map_err(|_|"Human input monitor state poisoned")?}),
        )),
        "desktop_windows" => Ok(text_result(
            json!({"schema":1,"windows":niri(state,"windows")?,"outputs":niri(state,"outputs")?,"workspaces":niri(state,"workspaces")?}),
        )),
        "desktop_observe" => observe(state, args),
        "desktop_semantic" => semantic(state, args),
        "desktop_semantic_direct" => semantic_direct(state, args),
        "desktop_act" => act(state, args, epoch),
        "desktop_cancel" | "desktop_takeover" => {
            if tool == "desktop_takeover" {
                state.takeover.store(true, Ordering::SeqCst);
            }
            let start = Instant::now();
            let next = state.epoch.fetch_add(1, Ordering::SeqCst) + 1;
            if tool == "desktop_takeover" {
                if let Err(error) = state
                    .takeover_marker
                    .lock()
                    .map_err(|_| "Takeover marker state poisoned")?
                    .set("explicit_desktop_takeover", &state.session_id)
                {
                    record(
                        state,
                        "takeover_persistence_failed",
                        json!({"error":error,"input_remains_latched":true,"backend_restart_requires_resume":true}),
                    );
                    return Err(format!("Desktop takeover latched and pending work canceled, but its marker could not be persisted: {error}. Every backend startup still requires explicit resume."));
                }
            }
            let active = state
                .active
                .lock()
                .map_err(|_| "Active task poisoned")?
                .clone();
            record(
                state,
                tool,
                json!({"epoch":next,"ack_ms":start.elapsed().as_secs_f64()*1000.0}),
            );
            Ok(text_result(
                json!({"schema":1,"status":"cancel_acknowledged","epoch":next,"active_at_ack":active,"ack_ms":start.elapsed().as_secs_f64()*1000.0,"actor_fully_released":false,"note":"Epoch changed immediately. Active actor releases buttons and returns canceled; inspect desktop_status until active=null and actor_release_confirmed=true before assuming desktop is free. Already-dispatched effects cannot be rolled back."}),
            ))
        }
        "desktop_resume" => {
            if !state
                .active
                .lock()
                .map_err(|_| "Active task poisoned")?
                .is_null()
            {
                return Err(
                    "Actor still releasing canceled task; wait desktop_status active=null".into(),
                );
            }
            if !state.release_confirmed.load(Ordering::SeqCst) {
                return Err("Previous actor release was not confirmed by compositor; repair/reconnect own backend before resuming".into());
            }
            // A fresh process has not yet observed a quiet interval. Missing
            // evdev observation is a capability failure, never evidence of idle.
            if state.started.elapsed() < Duration::from_millis(300) {
                return Err("Backend startup quiet interval is not complete; wait at least300ms and inspect desktop_status before explicit resume".into());
            }
            let monitor = state
                .human_monitor
                .lock()
                .map_err(|_| "Human input monitor state poisoned")?;
            if monitor["available"] != true
                || monitor["status"] == "starting"
                || monitor["watched_devices"].as_u64().unwrap_or(0) == 0
            {
                return Err("Physical input monitor is not ready/available; takeover remains latched. Repair input observation before resuming desktop automation.".into());
            }
            drop(monitor);
            let last = state.last_human_ms.load(Ordering::SeqCst);
            let now = state.started.elapsed().as_millis() as u64;
            if last != 0 && now.saturating_sub(last) < 300 {
                return Err("Physical human input is still recent; wait until desktop is idle before resuming".into());
            }
            // Serialize marker deletion with physical-event persistence. The
            // explicit tool call must follow the user's return-of-control policy.
            let mut marker = state
                .takeover_marker
                .lock()
                .map_err(|_| "Takeover marker state poisoned")?;
            if state.last_human_ms.load(Ordering::SeqCst) != last {
                return Err(
                    "Physical input changed while preparing resume; takeover remains latched"
                        .into(),
                );
            }
            let next = state.epoch.fetch_add(1, Ordering::SeqCst) + 1;
            marker.clear()?;
            state.takeover.store(false, Ordering::SeqCst);
            if state.last_human_ms.load(Ordering::SeqCst) != last
                || state.epoch.load(Ordering::SeqCst) != next
            {
                state.takeover.store(true, Ordering::SeqCst);
                if let Err(error) = marker.restore() {
                    record(
                        state,
                        "takeover_persistence_failed",
                        json!({"error":error,"input_remains_latched":true,"backend_restart_requires_resume":true}),
                    );
                }
                return Err(
                    "Human input or cancellation arrived while resuming; takeover remains latched"
                        .into(),
                );
            }
            record(state, "desktop_resume", json!({"epoch":next}));
            Ok(text_result(
                json!({"schema":1,"status":"resumed","epoch":next,"fresh_observation_required":true,"backend_restart_requires_explicit_resume":true}),
            ))
        }
        _ => Err(format!("Unknown tool {tool}")),
    }
}

fn tools() -> Value {
    let action = json!({"type":"object","properties":{"kind":{"type":"string","enum":["focus","move","click","scroll","drag","type","paste","key","semantic_set_value","semantic_click","wait"]},"window_id":{"type":"integer"},"x":{"type":"number"},"y":{"type":"number"},"to_x":{"type":"number"},"to_y":{"type":"number"},"button":{"type":"string","enum":["left","right","middle"]},"count":{"type":"integer"},"dx":{"type":"integer","minimum":-100,"maximum":100,"description":"Discrete wheel steps, not pixels. Positive moves right."},"dy":{"type":"integer","minimum":-100,"maximum":100,"description":"Discrete wheel steps, not pixels. Positive moves down."},"text":{"type":"string"},"handle_id":{"type":"string"},"action_name":{"type":"string"},"expected_text":{"type":"string"},"text_method":{"type":"string","enum":["auto","keyboard","clipboard"],"default":"auto"},"keys":{"type":"array","items":{"type":"string"}},"key_scope":{"type":"string","enum":["app","compositor"],"default":"app","description":"app uses Wayland; compositor explicitly uses owned uinput. Super/meta/logo always imply compositor. Does not translate or guess Niri bindings."},"ms":{"type":"integer"},"duration_ms":{"type":"integer"},"restore_clipboard":{"type":"boolean"}},"required":["kind"]});
    let crop = json!({"type":"object","properties":{"x":{"type":"integer","minimum":0},"y":{"type":"integer","minimum":0},"width":{"type":"integer","minimum":1},"height":{"type":"integer","minimum":1}},"required":["x","y","width","height"]});
    let mut catalog = json!([
      {"name":"desktop_status","description":"Persistent Niri desktop actor status, active/preparing task, queued batches and cancel epoch. Advertises global_keyboard routing_revision=2 only when this software implements scoped owned-uinput routing; this is not a live device/UI-success attestation. Does not capture or act.","inputSchema":{"type":"object","properties":{}}},
      {"name":"desktop_windows","description":"Read actual Niri windows, outputs and workspaces. Window layout may lack global app bounds; never invent bounds.","inputSchema":{"type":"object","properties":{}}},
      {"name":"desktop_observe","description":"Capture one actual laptop output via grim at scale1, plus Niri identities. Optional crop uses full-output screenshot pixels x/y/width/height; action x/y then use local pixels of the displayed crop. Core translates crop origin; NEVER add compositor output origin. Actual PNG size can differ from Niri logical size by rounding. Observation expires in60seconds; identity/geometry and fresh target-region guards still run. Observe after focus/workspace/layout changes. include_image=false returns private PNG reference only.","inputSchema":{"type":"object","properties":{"output":{"type":"string"},"include_image":{"type":"boolean"},"crop":crop}}},
      {"name":"desktop_semantic","description":"Read fresh Cua AT-SPI elements for a Niri window. Maps only unique actual PID+title; synthetic Cua IDs are never guessed. Query filters returned elements. Accessibility bounds are app-local and NOT screenshot coordinates; do not directly click them without calibrated mapping. Limited/root-only trees require visual fallback.","inputSchema":{"type":"object","properties":{"window_id":{"type":"integer"},"query":{"type":"string"},"max_elements":{"type":"integer"},"max_depth":{"type":"integer"}},"required":["window_id"]}},
      {"name":"desktop_semantic_direct","description":"Read exact-window AT-SPI subtree with immutable direct object handles. Supplies role/label/description/parent/text excerpt/action_names. Only daemon-owned handles from complete snapshots may be used with desktop_act semantic_set_value or semantic_click. No raw object/index/Cua tokens and no pixel fallback. Native GTK candidates need live acceptance; missing/incomplete bridges use visual typed actions.","inputSchema":{"type":"object","properties":{"window_id":{"type":"integer"},"query":{"type":"string"},"max_elements":{"type":"integer"},"max_depth":{"type":"integer"}},"required":["window_id"]}},
      {"name":"desktop_act","description":"Single-writer typed desktop actions against fresh observation. Rejects changed focus/geometry/scaling or changed pixels near pointer targets. x/y are local to displayed screenshot/crop. Focus must be standalone. By default observe_after=true returns a new after_observation ID and image in this same response after dispatch/release and a bounded80ms defaultsettle wait; settle_ms=0..1000 can adjust. Use it for the next act and inspect expected result. A slow/unchanged frame needs another observation/semantic check, not repetition of toggle input. include_image=false omits its image. Acknowledgement is not UI success. Type text_method=auto uses clipboard for known Electron IDs (code/T3) and >1000-character text, keyboard for shorter text in other apps; explicit keyboard/clipboard are available. Electron wtype Unicode is unreliable on this laptop. Clipboard preserves supported text/rich app payloads and original Chromium provenance in bounded RAM from one offer, normalizes duplicate MIME names, omits SAVE_TARGETS transport marker, and keeps a separate source holder across actor restarts. Unsupported/sensitive/oversized formats refuse before replacement. Own-source check runs after layout/keymap/window validation and before the first paste modifier press; ownership can still change between reply and input because Wayland has no atomic selection-check-and-paste. No restore after takeover/cancel/ownership loss. Scroll dx/dy are discrete wheel steps (integer -100..100), not pixels; positive dx moves right and positive dy moves down. Smooth-scroll animation needs another fresh observation/settle check before reusing visual targets. Keys are modifiers first e.g.[ctrl,l],[Return]. Explicit key_scope=compositor and Super/meta/logo chords use an owned persistent direct-uinput device because this Niri25.11 Wayland virtual keyboard bypasses compositor bindings; Ctrl/app chords retain the Wayland transport. A fresh proxy check requires backend routing_revision=2 and binds session/epoch/observation before forwarding a global batch; an older backend is refused. Missing permission/takeover monitor/compositor device-open evidence refuses the complete batch before input. Creating the own device is a capability side effect. A kernel input acknowledgement does not verify Niri/UI acceptance; inspect the fresh result. No automatic input fallback. Direct semantic_set_value(handle_id,text,expected_text optional) replaces exact editable contents; semantic_click(handle_id,action_name from direct tree) invokes only AT-SPI named action. Both freshly revalidate context and have no input fallback. Batch stable edits/shortcuts when intermediate states cannot invalidate later targets; changed-target actions need fresh observation.","inputSchema":{"type":"object","properties":{"observation_id":{"type":"string"},"window_id":{"type":"integer"},"task_id":{"type":"string"},"timeout_ms":{"type":"integer","minimum":100,"maximum":120000,"description":"Whole batch budget including queue, validation, capture, input and post-observe. Bounded release cleanup follows even after timeout."},"observe_after":{"type":"boolean","default":true},"include_image":{"type":"boolean","default":true},"settle_ms":{"type":"integer","default":80,"minimum":0,"maximum":1000,"description":"Bounded post-action settle wait before capture; not a proof of repaint. Slow conditions require fresh observations, never repeated blind input."},"actions":{"type":"array","items":action,"minItems":1,"maxItems":32}},"required":["observation_id","actions"]}},
      {"name":"desktop_cancel","description":"Priority epoch cancellation independent of actor lock. Pending batches stop; held buttons release. Already-dispatched effects remain. Wait for desktop_status active=null and actor_release_confirmed=true for full release.","inputSchema":{"type":"object","properties":{}}},
      {"name":"desktop_takeover","description":"Explicit human desktop takeover, persists its cause across backend restarts and latches refusal of future actions and cancels queued/active automation. Physical evdev input does this automatically when accessible. Wait active=null and actor_release_confirmed=true for full release. desktop_resume then fresh observation is required.","inputSchema":{"type":"object","properties":{}}},
      {"name":"desktop_resume","description":"Backend startup is always latched and preserves any prior human/explicit cause. Explicitly release takeover latch only after the user returns control, actor stopped and physical input idle. Do not automatically undo human takeover. Invalidates older observations. Call desktop_observe again before acting.","inputSchema":{"type":"object","properties":{}}}
    ]);
    // These hints describe desktop/app effects; private read caches do not
    // grant input. The managed client policy authorizes only this server.
    for tool in catalog
        .as_array_mut()
        .expect("Static MCP tool catalog is an array")
    {
        let (read_only, destructive, open_world) = match tool["name"].as_str() {
            Some("desktop_status") => (true, false, false),
            Some(
                "desktop_windows"
                | "desktop_observe"
                | "desktop_semantic"
                | "desktop_semantic_direct",
            ) => (true, false, true),
            Some("desktop_cancel" | "desktop_takeover" | "desktop_resume") => (false, false, false),
            _ => (false, true, true),
        };
        tool["annotations"] = json!({
            "readOnlyHint": read_only,
            "destructiveHint": destructive,
            // Every control mutation advances the epoch, even if already idle.
            "idempotentHint": read_only,
            "openWorldHint": open_world,
        });
    }
    catalog
}

fn socket_path() -> PathBuf {
    env::var_os("WEASEL_COMPUTER_USE_SOCKET")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(format!(
                "/run/user/{}/weasel-computer-use/desktop.sock",
                uid()
            ))
        })
}

fn daemon_call(socket: &Path, tool: &str, args: &Value) -> R<Value> {
    daemon_call_owned(socket, tool, args, None)
}

fn proxy_needs_global_guard(tool: &str, args: &Value) -> R<bool> {
    if tool != "desktop_act" {
        return Ok(false);
    }
    let actions = args["actions"]
        .as_array()
        .ok_or("desktop_act actions must be an array")?;
    let mut global = false;
    for item in actions {
        if item["kind"] == "key" {
            let action: Action = serde_json::from_value(item.clone())
                .map_err(|e| format!("Invalid scoped key action before proxy dispatch: {e}"))?;
            if let Action::Key { keys, key_scope } = action {
                global |= uses_global_keyboard(&keys, key_scope)?;
            }
        }
    }
    Ok(global)
}
fn validate_global_backend_guard(
    guard: &GlobalBackendGuard,
    session: &str,
    epoch: u64,
    observation_id: &str,
) -> R<()> {
    if guard.routing_revision != GLOBAL_ROUTING_REVISION
        || guard.session_id != session
        || guard.epoch != epoch
        || !observation_id.starts_with(&format!("obs-{session}-"))
    {
        return Err("Global keyboard backend changed or observation is from another session/epoch; no batch input sent. Reconnect and obtain a fresh observation.".into());
    }
    Ok(())
}
fn guarded_global_arguments(args: &Value, status_response: &Value) -> R<Value> {
    if status_response["isError"] == true {
        return Err(
            "Global keyboard capability query failed; complete batch refused before dispatch"
                .into(),
        );
    }
    let status: Value = serde_json::from_str(
        status_response["content"][0]["text"]
            .as_str()
            .ok_or("Global keyboard status response has no JSON metadata")?,
    )
    .map_err(|_| "Global keyboard status metadata invalid")?;
    if status["interface_revision"].as_u64() != Some(GLOBAL_ROUTING_REVISION as u64)
        || status["global_keyboard"]["routing_revision"].as_u64()
            != Some(GLOBAL_ROUTING_REVISION as u64)
        || status["global_keyboard"]["transport"] != "owned_uinput"
        || status["global_keyboard"]["super_implies_compositor"] != true
    {
        return Err("Backend does not advertise global keyboard routing revision2. Complete batch refused; restart/reconnect the declared backend before compositor shortcuts. No Wayland fallback.".into());
    }
    let guard = GlobalBackendGuard {
        routing_revision: GLOBAL_ROUTING_REVISION,
        session_id: status["session_id"]
            .as_str()
            .ok_or("Global keyboard status session missing")?
            .into(),
        epoch: status["epoch"]
            .as_u64()
            .ok_or("Global keyboard status epoch missing")?,
    };
    let observation_id = args["observation_id"]
        .as_str()
        .ok_or("Global action observation ID missing")?;
    validate_global_backend_guard(&guard, &guard.session_id, guard.epoch, observation_id)?;
    let mut guarded = args.clone();
    guarded.as_object_mut().ok_or("Global action arguments must be an object")?.insert("expected_global_backend".into(), json!({"routing_revision":guard.routing_revision,"session_id":guard.session_id,"epoch":guard.epoch}));
    Ok(guarded)
}
fn daemon_call_owned(
    socket: &Path,
    tool: &str,
    args: &Value,
    cancel: Option<Arc<AtomicBool>>,
) -> R<Value> {
    if proxy_needs_global_guard(tool, args)? {
        let started = Instant::now();
        let budget = Duration::from_millis(
            args["timeout_ms"]
                .as_u64()
                .unwrap_or(30000)
                .clamp(100, 120000),
        );
        let status = daemon_call_transport(
            socket,
            "desktop_status",
            &json!({}),
            cancel.clone(),
            budget.min(Duration::from_secs(2)),
        )?;
        let mut guarded = guarded_global_arguments(args, &status)?;
        let remaining = budget.saturating_sub(started.elapsed());
        if remaining < Duration::from_millis(100) {
            return Err(
                "Global capability preflight consumed the batch deadline; no action request sent"
                    .into(),
            );
        }
        guarded["timeout_ms"] = json!(remaining.as_millis() as u64);
        return daemon_call_transport(
            socket,
            tool,
            &guarded,
            cancel,
            remaining + Duration::from_secs(15),
        );
    }
    daemon_call_transport(
        socket,
        tool,
        args,
        cancel,
        if matches!(tool, "desktop_cancel" | "desktop_takeover") {
            Duration::from_secs(2)
        } else {
            Duration::from_secs(135)
        },
    )
}
fn daemon_call_transport(
    socket: &Path,
    tool: &str,
    args: &Value,
    cancel: Option<Arc<AtomicBool>>,
    read_timeout: Duration,
) -> R<Value> {
    if cancel.as_ref().is_some_and(|c| c.load(Ordering::SeqCst)) {
        return Err("MCP request canceled before dispatch".into());
    }
    let mut stream=UnixStream::connect(socket).map_err(|e|format!("Desktop daemon unavailable at {}: {e}. Start serve once; do not fall back to blind actions.",socket.display()))?;
    stream
        .set_read_timeout(Some(read_timeout))
        .map_err(|e| e.to_string())?;
    let done = Arc::new(AtomicBool::new(false));
    let monitor = if let Some(cancel) = cancel {
        let watch = stream.try_clone().map_err(|e| e.to_string())?;
        let done = done.clone();
        Some(thread::spawn(move || {
            while !done.load(Ordering::SeqCst) {
                if cancel.load(Ordering::SeqCst) {
                    let _ = watch.shutdown(std::net::Shutdown::Both);
                    break;
                }
                thread::sleep(Duration::from_millis(5));
            }
        }))
    } else {
        None
    };
    let result = (|| {
        writeln!(stream, "{}", json!({"tool":tool,"arguments":args})).map_err(|e| e.to_string())?;
        let mut line = String::new();
        BufReader::new(stream)
            .read_line(&mut line)
            .map_err(|e| e.to_string())?;
        if line.is_empty() {
            return Err("MCP request canceled/disconnected while backend was executing; inspect desktop_status last_result and reobserve before continuing".into());
        }
        serde_json::from_str(&line).map_err(|e| e.to_string())
    })();
    done.store(true, Ordering::SeqCst);
    if let Some(monitor) = monitor {
        let _ = monitor.join();
    }
    result
}

fn serve(socket: &Path) -> R<()> {
    // Different client socket names must not create competing physical actors.
    // flock remains held for the entire daemon lifetime and releases on exit.
    let global_dir = PathBuf::from(format!("/run/user/{}/weasel-computer-use", uid()));
    private_dir(&global_dir)?;
    let global_lock = fs::OpenOptions::new()
        .create(true)
        .write(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .mode(0o600)
        .open(global_dir.join("actuator.lock"))
        .map_err(|e| format!("Global actuator lock unavailable: {e}"))?;
    if global_lock.metadata().map_err(|e| e.to_string())?.uid() != uid() {
        return Err("Global actuator lock must be owned by current user".into());
    }
    fs::set_permissions(
        global_dir.join("actuator.lock"),
        fs::Permissions::from_mode(0o600),
    )
    .map_err(|e| e.to_string())?;
    if unsafe { libc::flock(global_lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err("A desktop actor is already running for this user, possibly through another socket. Do not create a second physical writer.".into());
    }
    let dir = socket.parent().ok_or("Socket needs parent directory")?;
    private_dir(dir)?;
    if socket.exists() {
        let m = fs::symlink_metadata(socket).map_err(|e| e.to_string())?;
        if !m.file_type().is_socket() || m.uid() != uid() {
            return Err("Refusing to replace non-owned socket path".into());
        }
        if UnixStream::connect(socket).is_ok() {
            return Err("Desktop daemon already listening".into());
        }
        fs::remove_file(socket).map_err(|e| e.to_string())?;
    }
    let listener = UnixListener::bind(socket).map_err(|e| e.to_string())?;
    fs::set_permissions(socket, fs::Permissions::from_mode(0o600)).map_err(|e| e.to_string())?;
    let images = dir.join("images");
    private_dir(&images)?;
    let log_path = dir.join("events.jsonl");
    let file = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .mode(0o600)
        .open(&log_path)
        .map_err(|e| e.to_string())?;
    fs::set_permissions(log_path, fs::Permissions::from_mode(0o600)).map_err(|e| e.to_string())?;
    let session_id = format!(
        "{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    );
    let takeover_marker = takeover::Latch::startup(global_dir.join("takeover.json"), &session_id)?;
    let state = Arc::new(State {
        started: Instant::now(),
        session_id,
        epoch: AtomicU64::new(1),
        serial: AtomicU64::new(1),
        queued: AtomicUsize::new(0),
        takeover: AtomicBool::new(true),
        takeover_marker: Mutex::new(takeover_marker),
        last_human_ms: AtomicU64::new(0),
        human_monitor: Mutex::new(json!({"available":false,"status":"starting"})),
        release_confirmed: AtomicBool::new(true),
        capture_available: AtomicBool::new(false),
        active: Mutex::new(Value::Null),
        last_result: Mutex::new(Value::Null),
        observations: Mutex::new(HashMap::new()),
        semantic_targets: Mutex::new(HashMap::new()),
        actor: Mutex::new(None),
        keyboard: Mutex::new(None),
        global_keyboard: Mutex::new(None),
        image_dir: images,
        log: Mutex::new(file),
    });
    let monitor = state.clone();
    thread::spawn(move || human_monitor(monitor));
    eprintln!("weasel computer use daemon listening {}", socket.display());
    for stream in listener.incoming() {
        let mut stream = match stream {
            Ok(s) => s,
            Err(e) => {
                eprintln!("Socket accept failed: {e}");
                continue;
            }
        };
        let state = state.clone();
        thread::spawn(move || {
            let epoch = state.epoch.load(Ordering::SeqCst);
            let clone = match stream.try_clone() {
                Ok(s) => s,
                Err(_) => return,
            };
            let mut line = String::new();
            if BufReader::new(clone.take(MAX_REQUEST))
                .read_line(&mut line)
                .is_err()
            {
                return;
            }
            let cancel = Arc::new(AtomicBool::new(false));
            CURRENT_CANCEL_FLAG.with(|f| *f.borrow_mut() = Some(cancel.clone()));
            let done = Arc::new(AtomicBool::new(false));
            let watch = match stream.try_clone() {
                Ok(s) => s,
                Err(_) => return,
            };
            let monitor_cancel = cancel.clone();
            let monitor_done = done.clone();
            let monitor = thread::spawn(move || {
                while !monitor_done.load(Ordering::SeqCst) {
                    let mut fd = libc::pollfd {
                        fd: watch.as_raw_fd(),
                        events: libc::POLLRDHUP,
                        revents: 0,
                    };
                    let result = unsafe { libc::poll(&mut fd, 1, 5) };
                    if result > 0
                        && fd.revents
                            & (libc::POLLRDHUP | libc::POLLHUP | libc::POLLERR | libc::POLLNVAL)
                            != 0
                    {
                        monitor_cancel.store(true, Ordering::SeqCst);
                        break;
                    }
                    if result < 0 {
                        monitor_cancel.store(true, Ordering::SeqCst);
                        break;
                    }
                }
            });
            let result = (|| {
                let req: Value = serde_json::from_str(&line).map_err(|e| e.to_string())?;
                handle(
                    &state,
                    req["tool"].as_str().ok_or("Missing tool name")?,
                    &req["arguments"],
                    epoch,
                )
            })();
            done.store(true, Ordering::SeqCst);
            let _ = monitor.join();
            CURRENT_CANCEL_FLAG.with(|f| *f.borrow_mut() = None);
            let value = result.unwrap_or_else(error_result);
            let _ = writeln!(stream, "{value}");
        });
    }
    Ok(())
}

fn mcp(socket: &Path) -> R<()> {
    let output = Arc::new(Mutex::new(io::stdout()));
    let stdin = io::stdin();
    let mut running = Vec::new();
    let pending = Arc::new(Mutex::new(HashMap::<String, Arc<AtomicBool>>::new()));
    let inflight = Arc::new(Mutex::new(std::collections::HashSet::<String>::new()));
    for line in stdin.lock().lines() {
        let line = line.map_err(|e| e.to_string())?;
        if line.trim().is_empty() {
            continue;
        }
        let req: Value = serde_json::from_str(&line).map_err(|e| e.to_string())?;
        let Some(id) = req.get("id").cloned() else {
            if req["method"] == "notifications/cancelled" {
                if let Some(flag) = pending
                    .lock()
                    .map_err(|_| "Pending calls lock poisoned")?
                    .get(&req["params"]["requestId"].to_string())
                {
                    flag.store(true, Ordering::SeqCst);
                }
            }
            continue;
        };
        let request_key = id.to_string();
        if !inflight
            .lock()
            .map_err(|_| "Inflight IDs lock poisoned")?
            .insert(request_key.clone())
        {
            let response = json!({"jsonrpc":"2.0","id":id,"error":{"code":-32600,"message":"Duplicate in-flight MCP request ID rejected; original call and cancellation ownership retained"}});
            let mut stdout = output.lock().map_err(|_| "MCP output lock poisoned")?;
            writeln!(*stdout, "{response}").map_err(|e| e.to_string())?;
            stdout.flush().map_err(|e| e.to_string())?;
            continue;
        }
        let is_act = req["method"] == "tools/call" && req["params"]["name"] == "desktop_act";
        let cancel = Arc::new(AtomicBool::new(false));
        if is_act {
            pending
                .lock()
                .map_err(|_| "Pending calls lock poisoned")?
                .insert(request_key.clone(), cancel.clone());
        }
        let pending = pending.clone();
        let inflight = inflight.clone();
        let out = output.clone();
        let path = socket.to_owned();
        running.push(thread::spawn(move||{
        let method=req["method"].as_str().unwrap_or("");let result=match method{
          "initialize"=>Ok(json!({"protocolVersion":req["params"]["protocolVersion"].as_str().unwrap_or("2024-11-05"),"capabilities":{"tools":{"listChanged":false}},"serverInfo":{"name":"weasel-computer-use","version":"0.1.0"}})),
          "ping"=>Ok(json!({})),"tools/list"=>Ok(json!({"tools":tools()})),
          "tools/call"=>daemon_call_owned(&path,req["params"]["name"].as_str().unwrap_or(""),req["params"].get("arguments").unwrap_or(&json!({})),if is_act{Some(cancel)}else{None}),
          _=>Err(format!("Unsupported MCP method {method}")),
        };if is_act{if let Ok(mut calls)=pending.lock(){calls.remove(&request_key);}}
        let response=match result{Ok(result)=>json!({"jsonrpc":"2.0","id":id,"result":result}),Err(message)=>json!({"jsonrpc":"2.0","id":id,"error":{"code":-32603,"message":message}})};if let Ok(mut stdout)=out.lock(){let _=writeln!(*stdout,"{response}");let _=stdout.flush();}if let Ok(mut ids)=inflight.lock(){ids.remove(&request_key);}
    }));
        running.retain(|h| !h.is_finished());
    }
    for flag in pending
        .lock()
        .map_err(|_| "Pending calls lock poisoned")?
        .values()
    {
        flag.store(true, Ordering::SeqCst);
    }
    for h in running {
        let _ = h.join();
    }
    Ok(())
}

fn main() {
    let mut args = env::args().skip(1);
    let command = args.next().unwrap_or_else(|| "--help".into());
    let socket = socket_path();
    let result = match command.as_str() {
        "__clipboard_helper" => clipboard::helper_main(),
        "__atspi_helper" => {
            let mut bytes = Vec::new();
            io::stdin()
                .take(2 * 1024 * 1024)
                .read_to_end(&mut bytes)
                .map_err(|e| e.to_string())
                .and_then(|_| serde_json::from_slice(&bytes).map_err(|e| e.to_string()))
                .and_then(atspi::run)
                .map(|v| println!("{v}"))
        }
        "serve" => serve(&socket),
        "mcp" => mcp(&socket),
        "call" => {
            let tool = args.next().unwrap_or_default();
            let raw = args.next().unwrap_or_else(|| "{}".into());
            serde_json::from_str(&raw)
                .map_err(|e| e.to_string())
                .and_then(|value| daemon_call(&socket, &tool, &value))
                .map(|v| println!("{v}"))
        }
        "--help" | "help" => {
            println!("weasel-computer-use-core serve | mcp | call TOOL JSON\nSocket: WEASEL_COMPUTER_USE_SOCKET or /run/user/UID/weasel-computer-use/desktop.sock\nDaemon has no model/API/credential access. One persistent physical desktop writer; explicit cancel/takeover.");
            Ok(())
        }
        _ => Err("Use --help".into()),
    };
    if let Err(e) = result {
        eprintln!("{e}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod regression {
    use super::*;
    #[test]
    fn restart_latch_and_resume_guards_without_desktop() {
        let dir = env::temp_dir().join(format!("weasel-resume-regression-{}", std::process::id()));
        private_dir(&dir).unwrap();
        let marker_path = dir.join("takeover.json");
        let session = "offline-session-1";
        let file = fs::OpenOptions::new()
            .create(true)
            .write(true)
            .mode(0o600)
            .open(dir.join("events.jsonl"))
            .unwrap();
        let mut state = State {
            started: Instant::now(),
            session_id: session.into(),
            epoch: AtomicU64::new(1),
            serial: AtomicU64::new(1),
            queued: AtomicUsize::new(0),
            takeover: AtomicBool::new(true),
            takeover_marker: Mutex::new(
                takeover::Latch::startup(marker_path.clone(), session).unwrap(),
            ),
            last_human_ms: AtomicU64::new(0),
            human_monitor: Mutex::new(Value::Null),
            release_confirmed: AtomicBool::new(true),
            capture_available: AtomicBool::new(false),
            active: Mutex::new(Value::Null),
            last_result: Mutex::new(Value::Null),
            observations: Mutex::new(HashMap::new()),
            semantic_targets: Mutex::new(HashMap::new()),
            actor: Mutex::new(None),
            keyboard: Mutex::new(None),
            global_keyboard: Mutex::new(None),
            image_dir: dir.clone(),
            log: Mutex::new(file),
        };
        assert!(handle(&state, "desktop_resume", &json!({}), 1)
            .unwrap_err()
            .contains("startup quiet interval"));
        state.started = Instant::now() - Duration::from_millis(350);
        assert!(handle(&state, "desktop_resume", &json!({}), 1)
            .unwrap_err()
            .contains("not ready/available"));
        *state.human_monitor.lock().unwrap() = json!({"available":true,"watched_devices":1});
        state
            .last_human_ms
            .store(state.started.elapsed().as_millis() as u64, Ordering::SeqCst);
        assert!(handle(&state, "desktop_resume", &json!({}), 1)
            .unwrap_err()
            .contains("recent"));
        assert!(marker_path.exists());
        assert!(state.takeover.load(Ordering::SeqCst));
        state.last_human_ms.store(0, Ordering::SeqCst);
        *state.active.lock().unwrap() = json!({"task_id":"owned offline task"});
        assert!(handle(&state, "desktop_resume", &json!({}), 1)
            .unwrap_err()
            .contains("still releasing"));
        *state.active.lock().unwrap() = Value::Null;
        state.release_confirmed.store(false, Ordering::SeqCst);
        assert!(handle(&state, "desktop_resume", &json!({}), 1)
            .unwrap_err()
            .contains("not confirmed"));
        state.release_confirmed.store(true, Ordering::SeqCst);
        let resumed = handle(&state, "desktop_resume", &json!({}), 1).unwrap();
        let data: Value =
            serde_json::from_str(resumed["content"][0]["text"].as_str().unwrap()).unwrap();
        assert_eq!(data["status"], "resumed");
        assert_eq!(data["fresh_observation_required"], true);
        assert!(!state.takeover.load(Ordering::SeqCst));
        assert!(!marker_path.exists());
        let takeover = handle(&state, "desktop_takeover", &json!({}), 2).unwrap();
        assert_eq!(takeover["isError"], false);
        assert!(state.takeover.load(Ordering::SeqCst));
        assert!(marker_path.exists());
        let restarted = takeover::Latch::startup(marker_path, "offline-session-2").unwrap();
        assert_eq!(restarted.reason.source, "explicit_desktop_takeover");
        assert_eq!(restarted.reason.session_id, session);
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn bounded_background_and_cancel_and_crop_targets() {
        // These are disposable subprocess/data tests. They never connect to
        // Wayland, Niri, Cua, input devices, real clipboard, or the daemon.
        let dir = env::temp_dir().join(format!("weasel-core-regression-{}", std::process::id()));
        private_dir(&dir).unwrap();
        let script = dir.join("wl-copy");
        fs::write(&script, b"#!/bin/sh\nsleep 0.4 &\nexit 0\n").unwrap();
        fs::set_permissions(&script, fs::Permissions::from_mode(0o700)).unwrap();
        let old_path = env::var_os("PATH").unwrap_or_default();
        env::set_var(
            "PATH",
            format!("{}:{}", dir.display(), old_path.to_string_lossy()),
        );
        let log = fs::OpenOptions::new()
            .create(true)
            .write(true)
            .mode(0o600)
            .open(dir.join("events.jsonl"))
            .unwrap();
        let state = Arc::new(State {
            started: Instant::now(),
            session_id: "regression".into(),
            epoch: AtomicU64::new(1),
            serial: AtomicU64::new(1),
            queued: AtomicUsize::new(0),
            takeover: AtomicBool::new(false),
            takeover_marker: Mutex::new(
                takeover::Latch::startup(dir.join("takeover.json"), "offline-regression").unwrap(),
            ),
            last_human_ms: AtomicU64::new(0),
            human_monitor: Mutex::new(Value::Null),
            release_confirmed: AtomicBool::new(true),
            capture_available: AtomicBool::new(false),
            active: Mutex::new(Value::Null),
            last_result: Mutex::new(Value::Null),
            observations: Mutex::new(HashMap::new()),
            semantic_targets: Mutex::new(HashMap::new()),
            actor: Mutex::new(None),
            keyboard: Mutex::new(None),
            global_keyboard: Mutex::new(None),
            image_dir: dir.clone(),
            log: Mutex::new(log),
        });
        let start = Instant::now();
        bounded_command(
            &state,
            "wl-copy",
            &[],
            Some(b"fixture"),
            Duration::from_millis(200),
            Some(1),
        )
        .unwrap();
        assert!(
            start.elapsed() < Duration::from_millis(200),
            "background output owner must not retain acknowledgement pipes"
        );
        env::set_var("PATH", &old_path);
        let canceller = state.clone();
        let timer = thread::spawn(move || {
            thread::sleep(Duration::from_millis(30));
            canceller.epoch.fetch_add(1, Ordering::SeqCst);
        });
        let start = Instant::now();
        let error = bounded_command(
            &state,
            "sh",
            &["-c".into(), "sleep 5".into()],
            Some(&vec![b'x'; 65536]),
            Duration::from_secs(2),
            Some(1),
        )
        .unwrap_err();
        timer.join().unwrap();
        assert!(error.contains("Canceled"));
        assert!(
            start.elapsed() < Duration::from_millis(400),
            "stalled stdin must remain cancelable"
        );
        let obs = Observation {
            id: "fixture".into(),
            at: Instant::now(),
            epoch: 2,
            output: "none".into(),
            output_geometry: Value::Null,
            focused_window: None,
            focus_output: None,
            image_width: 100,
            image_height: 100,
            image: dir.join("unused.png"),
            view: Crop {
                x: 40,
                y: 40,
                width: 20,
                height: 20,
            },
            view_image: dir.join("unused-crop.png"),
        };
        assert!(preflight(&obs,&Action::Drag{x:5.0,y:5.0,to_x:-1.0,to_y:5.0,duration_ms:None}).is_err(),"negative crop-local endpoint must reject before button down even if full-output position exists");
        assert!(preflight(
            &obs,
            &Action::Click {
                x: 5.0,
                y: 5.0,
                button: None,
                count: Some(0)
            }
        )
        .is_err());
        assert!(preflight(
            &obs,
            &Action::Click {
                x: 19.0,
                y: 19.0,
                button: None,
                count: Some(1)
            }
        )
        .is_ok());
        assert!(preflight(
            &obs,
            &Action::Key {
                keys: vec!["ctrl".into(), "invalid-key".into()],
                key_scope: KeyScope::App
            }
        )
        .is_err());
        assert!(preflight(
            &obs,
            &Action::Scroll {
                x: 5.0,
                y: 5.0,
                dx: 0,
                dy: 101
            }
        )
        .is_err());
        state
            .observations
            .lock()
            .unwrap()
            .insert(obs.id.clone(), obs.clone());
        state.capture_available.store(true, Ordering::SeqCst);
        let started = Instant::now();
        let response=act(&state,&json!({"observation_id":obs.id,"timeout_ms":100,"observe_after":false,"actions":[{"kind":"wait","ms":10000}]}),2).unwrap();
        let data: Value =
            serde_json::from_str(response["content"][0]["text"].as_str().unwrap()).unwrap();
        assert_eq!(data["status"], "failed");
        assert_eq!(response["isError"], true);
        assert_eq!(data["completed_actions"], 0);
        assert_eq!(data["actor_release_confirmed"], true);
        assert!(data["error"].as_str().unwrap().contains("deadline"));
        assert!(
            started.elapsed() < Duration::from_millis(300),
            "100ms batch deadline must interrupt 10-second wait"
        );
        let held = state.actor.lock().unwrap();
        let waiting = state.clone();
        let started = Instant::now();
        let queued = thread::spawn(move || {
            act(
                &waiting,
                &json!({"observation_id":"fixture","timeout_ms":100,"observe_after":false,"actions":[{"kind":"wait","ms":1000}]}),
                2,
            )
        });
        thread::sleep(Duration::from_millis(150));
        drop(held);
        assert!(queued.join().unwrap().unwrap_err().contains("deadline"));
        assert!(started.elapsed() < Duration::from_millis(300));
        assert_eq!(state.queued.load(Ordering::SeqCst), 0);
        // Simulated capture failure and recovery use only owned fake binaries.
        // This tests capability gating, not a real screenshot or desktop input.
        let niri_script = dir.join("niri");
        fs::write(&niri_script, b"#!/bin/sh\ncase \"$3\" in\nwindows) echo '[]';;\noutputs) echo '{\"mock\":{\"logical\":{\"x\":0,\"y\":0,\"width\":2,\"height\":2,\"scale\":1,\"transform\":\"Normal\"}}}';;\nworkspaces) echo '[{\"id\":1,\"idx\":1,\"output\":\"mock\",\"is_focused\":true,\"is_active\":true,\"active_window_id\":null}]';;\n*) exit 1;;\nesac\n").unwrap();
        fs::set_permissions(&niri_script, fs::Permissions::from_mode(0o700)).unwrap();
        let grim_script = dir.join("grim");
        fs::write(&grim_script, b"#!/bin/sh\nexit 1\n").unwrap();
        fs::set_permissions(&grim_script, fs::Permissions::from_mode(0o700)).unwrap();
        env::set_var(
            "PATH",
            format!("{}:{}", dir.display(), old_path.to_string_lossy()),
        );
        assert!(
            observe(&state, &json!({"output":"mock","include_image":false}))
                .unwrap_err()
                .contains("Capture backend failed")
        );
        assert!(!state.capture_available.load(Ordering::SeqCst));
        assert_eq!(state.epoch.load(Ordering::SeqCst), 3);
        assert!(state.observations.lock().unwrap().is_empty());
        assert!(act(&state,&json!({"observation_id":"fixture","observe_after":false,"actions":[{"kind":"wait","ms":1}]}),3).unwrap_err().contains("No successful current capture"));
        let sample = dir.join("synthetic.png");
        let image_file = fs::File::create(&sample).unwrap();
        let mut encoder = png::Encoder::new(image_file, 2, 2);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        encoder
            .write_header()
            .unwrap()
            .write_image_data(&[0u8; 16])
            .unwrap();
        fs::write(
            &grim_script,
            format!(
                "#!/bin/sh\nfor arg do destination=\"$arg\"; done\ncp '{}' \"$destination\"\n",
                sample.display()
            ),
        )
        .unwrap();
        let recovered = observe(&state, &json!({"output":"mock","include_image":false})).unwrap();
        let recovered_data: Value =
            serde_json::from_str(recovered["content"][0]["text"].as_str().unwrap()).unwrap();
        assert!(state.capture_available.load(Ordering::SeqCst));
        assert_eq!(recovered_data["epoch"], 3);
        assert_eq!(state.observations.lock().unwrap().len(), 1);
        let waited=act(&state,&json!({"observation_id":recovered_data["observation_id"],"observe_after":false,"actions":[{"kind":"wait","ms":1}]}),3).unwrap();
        assert_eq!(waited["isError"], false);
        env::set_var("PATH", &old_path);
        let _ = fs::remove_dir_all(dir);
    }
}

#[cfg(test)]
mod global_routing_regression {
    use super::*;
    fn keys(names: &[&str]) -> Vec<String> {
        names.iter().map(|n| n.to_string()).collect()
    }
    fn global_args(action: Value) -> Value {
        json!({"observation_id":"obs-offline-session-1","timeout_ms":1000,"actions":[{"kind":"type","text":"owned fixture"},action]})
    }
    #[test]
    fn scoped_route_defaults_and_aliases_are_typed() {
        for alias in ["super", "meta", "logo"] {
            assert!(uses_global_keyboard(&keys(&[alias, "f"]), KeyScope::App).unwrap());
        }
        assert!(!uses_global_keyboard(&keys(&["ctrl", "alt", "Escape"]), KeyScope::App).unwrap());
        assert!(
            uses_global_keyboard(&keys(&["ctrl", "alt", "Escape"]), KeyScope::Compositor).unwrap()
        );
        assert!(!uses_global_keyboard(&keys(&["ctrl", "s"]), KeyScope::App).unwrap());
        let action: Action =
            serde_json::from_value(json!({"kind":"key","keys":["ctrl","s"]})).unwrap();
        assert!(matches!(
            action,
            Action::Key {
                key_scope: KeyScope::App,
                ..
            }
        ));
        assert!(serde_json::from_value::<Action>(
            json!({"kind":"key","keys":["ctrl","s"],"key_scope":"global-guess"})
        )
        .is_err());
        assert!(proxy_needs_global_guard(
            "desktop_act",
            &global_args(json!({"kind":"key","keys":["super","shift","f"]}))
        )
        .unwrap());
        assert!(proxy_needs_global_guard(
            "desktop_act",
            &global_args(
                json!({"kind":"key","keys":["ctrl","alt","Escape"],"key_scope":"compositor"})
            )
        )
        .unwrap());
    }
    #[test]
    fn backend_guard_rejects_wrong_session_epoch_and_revision() {
        let guard = GlobalBackendGuard {
            routing_revision: GLOBAL_ROUTING_REVISION,
            session_id: "offline-session".into(),
            epoch: 7,
        };
        assert!(validate_global_backend_guard(
            &guard,
            "offline-session",
            7,
            "obs-offline-session-1"
        )
        .is_ok());
        assert!(
            validate_global_backend_guard(&guard, "other-session", 7, "obs-offline-session-1")
                .is_err()
        );
        assert!(validate_global_backend_guard(
            &guard,
            "offline-session",
            8,
            "obs-offline-session-1"
        )
        .is_err());
        assert!(
            validate_global_backend_guard(&guard, "offline-session", 7, "obs-other-session-1")
                .is_err()
        );
        let old = GlobalBackendGuard {
            routing_revision: 1,
            ..guard
        };
        assert!(
            validate_global_backend_guard(&old, "offline-session", 7, "obs-offline-session-1")
                .is_err()
        );
    }
    fn fake_backend(status: Value, expects_act: bool) -> (PathBuf, thread::JoinHandle<Vec<Value>>) {
        static SERIAL: AtomicU64 = AtomicU64::new(1);
        let dir = env::temp_dir().join(format!(
            "weasel-global-proxy-test-{}-{}",
            std::process::id(),
            SERIAL.fetch_add(1, Ordering::SeqCst)
        ));
        fs::create_dir(&dir).unwrap();
        fs::set_permissions(&dir, fs::Permissions::from_mode(0o700)).unwrap();
        let socket = dir.join("fixture.sock");
        let listener = std::os::unix::net::UnixListener::bind(&socket).unwrap();
        listener.set_nonblocking(true).unwrap();
        let cleanup_socket = socket.clone();
        let handle = thread::spawn(move || {
            let mut requests = Vec::new();
            let mut last = Instant::now();
            loop {
                match listener.accept() {
                    Ok((mut stream, _)) => {
                        stream
                            .set_read_timeout(Some(Duration::from_millis(200)))
                            .unwrap();
                        let mut line = String::new();
                        BufReader::new(stream.try_clone().unwrap())
                            .read_line(&mut line)
                            .unwrap();
                        let req: Value = serde_json::from_str(&line).unwrap();
                        let response = if req["tool"] == "desktop_status" {
                            text_result(status.clone())
                        } else {
                            text_result(json!({"status":"offline_fixture_ack"}))
                        };
                        requests.push(req);
                        writeln!(stream, "{response}").unwrap();
                        last = Instant::now();
                        if expects_act && requests.len() == 2 {
                            break;
                        }
                    }
                    Err(e) if e.kind() == io::ErrorKind::WouldBlock => {
                        if (!requests.is_empty()
                            && !expects_act
                            && last.elapsed() > Duration::from_millis(120))
                            || last.elapsed() > Duration::from_secs(2)
                        {
                            break;
                        }
                        thread::sleep(Duration::from_millis(2));
                    }
                    Err(e) => panic!("private fixture socket: {e}"),
                }
            }
            fs::remove_file(&cleanup_socket).unwrap();
            fs::remove_dir(&dir).unwrap();
            requests
        });
        (socket, handle)
    }
    #[test]
    fn new_proxy_old_actor_refuses_entire_batch_before_any_act_request() {
        for action in [
            json!({"kind":"key","keys":["super","shift","f"]}),
            json!({"kind":"key","keys":["ctrl","alt","Escape"],"key_scope":"compositor"}),
        ] {
            let (socket, server) = fake_backend(
                json!({"schema":1,"version":"0.1.0","session_id":"offline-session","epoch":7}),
                false,
            );
            let error =
                daemon_call_owned(&socket, "desktop_act", &global_args(action), None).unwrap_err();
            assert!(error.contains("routing revision2"));
            let requests = server.join().unwrap();
            assert_eq!(requests.len(), 1);
            assert_eq!(requests[0]["tool"], "desktop_status");
        }
    }
    #[test]
    fn new_proxy_new_actor_binds_guard_and_preserves_scoped_chord() {
        let (socket, server) = fake_backend(
            json!({"interface_revision":2,"global_keyboard":global_keyboard_capability(),"session_id":"offline-session","epoch":7}),
            true,
        );
        daemon_call_owned(
            &socket,
            "desktop_act",
            &global_args(
                json!({"kind":"key","keys":["ctrl","alt","Escape"],"key_scope":"compositor"}),
            ),
            None,
        )
        .unwrap();
        let requests = server.join().unwrap();
        assert_eq!(requests.len(), 2);
        assert_eq!(requests[1]["tool"], "desktop_act");
        let args = &requests[1]["arguments"];
        assert_eq!(
            args["expected_global_backend"],
            json!({"routing_revision":2,"session_id":"offline-session","epoch":7})
        );
        assert_eq!(args["actions"][1]["key_scope"], "compositor");
        assert!(args["timeout_ms"].as_u64().unwrap() <= 1000);
    }
}
