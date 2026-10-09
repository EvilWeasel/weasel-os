//! Canonical German evdev virtual keyboard for reliable native shortcuts.
//! Unicode text is a separate transport; this keyboard represents physical keys.
use std::{
    collections::HashSet,
    error::Error,
    fmt,
    fs::File,
    io::Write,
    os::fd::{AsFd, AsRawFd, FromRawFd},
    time::{Duration, Instant},
};
use wayland_client::{
    delegate_noop,
    protocol::{wl_callback, wl_keyboard, wl_registry, wl_seat},
    Connection, Dispatch, EventQueue, QueueHandle,
};
use wayland_protocols_misc::zwp_virtual_keyboard_v1::client::{
    zwp_virtual_keyboard_manager_v1::ZwpVirtualKeyboardManagerV1,
    zwp_virtual_keyboard_v1::ZwpVirtualKeyboardV1,
};

pub const GERMAN_EVDEV_KEYMAP: &str = include_str!("de.xkb");
#[derive(Debug)]
pub struct KeyboardError(pub String);
impl fmt::Display for KeyboardError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}
impl Error for KeyboardError {}
pub type Result<T> = std::result::Result<T, KeyboardError>;
fn error(context: &str, e: impl fmt::Display) -> KeyboardError {
    KeyboardError(format!("{context}: {e}"))
}

#[derive(Default)]
struct State {
    seat: Option<wl_seat::WlSeat>,
    seat_global: Option<u32>,
    manager: Option<ZwpVirtualKeyboardManagerV1>,
    manager_global: Option<u32>,
    globals_invalidated: bool,
    completed_sync: u64,
}
impl Dispatch<wl_registry::WlRegistry, ()> for State {
    fn event(
        state: &mut Self,
        registry: &wl_registry::WlRegistry,
        event: wl_registry::Event,
        _: &(),
        _: &Connection,
        qh: &QueueHandle<Self>,
    ) {
        match event {
            wl_registry::Event::Global {
                name,
                interface,
                version,
            } => match interface.as_str() {
                "wl_seat" if state.seat.is_none() => {
                    state.seat = Some(registry.bind(name, version.min(1), qh, ()));
                    state.seat_global = Some(name);
                }
                "zwp_virtual_keyboard_manager_v1" if state.manager.is_none() => {
                    state.manager = Some(registry.bind(name, 1, qh, ()));
                    state.manager_global = Some(name);
                }
                _ => {}
            },
            wl_registry::Event::GlobalRemove { name } => {
                if state.seat_global == Some(name) {
                    state.seat = None;
                    state.seat_global = None;
                    state.globals_invalidated = true;
                }
                if state.manager_global == Some(name) {
                    state.manager = None;
                    state.manager_global = None;
                    state.globals_invalidated = true;
                }
            }
            _ => {}
        }
    }
}
impl Dispatch<wl_callback::WlCallback, u64> for State {
    fn event(
        state: &mut Self,
        _: &wl_callback::WlCallback,
        event: wl_callback::Event,
        serial: &u64,
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        if let wl_callback::Event::Done { .. } = event {
            state.completed_sync = state.completed_sync.max(*serial)
        }
    }
}
delegate_noop!(State: ignore wl_seat::WlSeat);
delegate_noop!(State: ignore ZwpVirtualKeyboardManagerV1);
delegate_noop!(State: ignore ZwpVirtualKeyboardV1);

pub struct Keyboard {
    connection: Connection,
    queue: EventQueue<State>,
    state: State,
    keyboard: Option<ZwpVirtualKeyboardV1>,
    keymap_file: Option<File>,
    held: HashSet<u32>,
    clock: Instant,
    next_sync: u64,
}

impl Keyboard {
    /// Creates a keyboard and uploads the canonical keymap; no key event is sent.
    /// Do not call this during a read-only inventory of another desktop owner.
    pub fn new() -> Result<Self> {
        Self::new_timeout(Duration::from_millis(350))
    }

    /// One total budget covers discovery and canonical keymap acknowledgement.
    pub fn new_timeout(timeout: Duration) -> Result<Self> {
        if timeout.is_zero() {
            return Err(KeyboardError("keyboard bootstrap deadline expired".into()));
        }
        let deadline = Instant::now()
            .checked_add(timeout)
            .ok_or_else(|| KeyboardError("invalid keyboard bootstrap deadline".into()))?;
        let remaining = || {
            let remaining = deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                Err(KeyboardError("keyboard bootstrap deadline expired".into()))
            } else {
                Ok(remaining)
            }
        };
        let connection =
            Connection::connect_to_env().map_err(|e| error("Wayland connection", e))?;
        let queue = connection.new_event_queue();
        connection.display().get_registry(&queue.handle(), ());
        let mut result = Self {
            connection,
            queue,
            state: State::default(),
            keyboard: None,
            keymap_file: None,
            held: HashSet::new(),
            clock: Instant::now(),
            next_sync: 1,
        };
        result.sync_timeout(remaining()?.min(Duration::from_millis(250)))?;
        let manager = result
            .state
            .manager
            .as_ref()
            .ok_or_else(|| KeyboardError("virtual keyboard manager unavailable".into()))?;
        let seat = result
            .state
            .seat
            .as_ref()
            .ok_or_else(|| KeyboardError("Wayland seat unavailable".into()))?;
        remaining()?;
        let keyboard = manager.create_virtual_keyboard(seat, &result.queue.handle(), ());
        let fd = unsafe { libc::memfd_create(c"weasel-cu-de-keymap".as_ptr(), libc::MFD_CLOEXEC) };
        if fd < 0 {
            return Err(error("keymap memfd", std::io::Error::last_os_error()));
        }
        let mut file = unsafe { File::from_raw_fd(fd) };
        file.write_all(GERMAN_EVDEV_KEYMAP.as_bytes())
            .map_err(|e| error("keymap write", e))?;
        file.write_all(&[0])
            .map_err(|e| error("keymap terminator", e))?;
        result.keyboard = Some(keyboard);
        result.keymap_file = Some(file);
        result.refresh_keymap_timeout(remaining()?.min(Duration::from_millis(100)))?;
        Ok(result)
    }

    /// Reasserts the canonical physical keymap after another virtual keyboard
    /// (for example a Unicode typing transport) has used the same seat.
    /// Must run before a chord, never while this device owns held keys.
    /// The retained memfd contains no private text and is reused without writes.
    pub fn refresh_keymap(&mut self) -> Result<()> {
        self.refresh_keymap_timeout(Duration::from_millis(100))
    }

    /// A zero remaining action budget refuses before uploading the keymap.
    pub fn refresh_keymap_timeout(&mut self, timeout: Duration) -> Result<()> {
        if timeout.is_zero() {
            return Err(KeyboardError("keyboard keymap deadline expired".into()));
        }
        let deadline = Instant::now()
            .checked_add(timeout)
            .ok_or_else(|| KeyboardError("invalid keyboard keymap deadline".into()))?;
        let remaining = || {
            let left = deadline.saturating_duration_since(Instant::now());
            if left.is_zero() {
                Err(KeyboardError("keyboard keymap deadline expired".into()))
            } else {
                Ok(left)
            }
        };
        if !self.held.is_empty() {
            return Err(KeyboardError(
                "keymap refresh refused while keys are held".into(),
            ));
        }
        // Read registry changes from the wire before uploading to a cached
        // device; dispatch_pending alone cannot discover unread removals.
        self.sync_timeout(remaining()?)?;
        self.valid_globals()?;
        let file = self
            .keymap_file
            .as_ref()
            .ok_or_else(|| KeyboardError("canonical keymap unavailable".into()))?;
        self.keyboard()?.keymap(
            wl_keyboard::KeymapFormat::XkbV1 as u32,
            file.as_fd(),
            (GERMAN_EVDEV_KEYMAP.len() + 1) as u32,
        );
        self.keyboard()?.modifiers(0, 0, 0, 0);
        self.sync_timeout(remaining()?)?;
        self.valid_globals()
    }

    fn flush(&self) -> Result<()> {
        self.connection
            .flush()
            .map_err(|e| error("Wayland keyboard flush", e))
    }
    fn keyboard(&self) -> Result<&ZwpVirtualKeyboardV1> {
        self.keyboard
            .as_ref()
            .ok_or_else(|| KeyboardError("keyboard unavailable".into()))
    }
    fn valid_globals(&self) -> Result<()> {
        if self.state.globals_invalidated
            || self.state.seat.is_none()
            || self.state.manager.is_none()
        {
            return Err(KeyboardError("keyboard seat/manager disappeared; only release cleanup is allowed until explicit backend reconnect".into()));
        }
        Ok(())
    }
    fn time(&self) -> u32 {
        self.clock.elapsed().as_millis() as u32
    }
    fn modifier_mask(&self) -> u32 {
        let mut mask = 0;
        if self.held.contains(&42) || self.held.contains(&54) {
            mask |= 1;
        }
        if self.held.contains(&29) || self.held.contains(&97) {
            mask |= 4;
        }
        if self.held.contains(&56) {
            mask |= 8;
        }
        if self.held.contains(&125) || self.held.contains(&126) {
            mask |= 64;
        }
        if self.held.contains(&100) {
            mask |= 128;
        }
        mask
    }

    pub fn key_evdev(&mut self, code: u32, pressed: bool) -> Result<()> {
        if code == 0 || code > 255 {
            return Err(KeyboardError("evdev key code must be 1..255".into()));
        }
        if self.held.contains(&code) == pressed {
            return Err(KeyboardError("duplicate key transition refused".into()));
        }
        self.queue
            .dispatch_pending(&mut self.state)
            .map_err(|e| error("keyboard pending registry changes", e))?;
        self.valid_globals()?;
        self.keyboard()?.key(
            self.time(),
            code,
            if pressed {
                wl_keyboard::KeyState::Pressed as u32
            } else {
                wl_keyboard::KeyState::Released as u32
            },
        );
        if pressed {
            self.held.insert(code);
        } else {
            self.held.remove(&code);
        }
        self.keyboard()?.modifiers(self.modifier_mask(), 0, 0, 0);
        self.flush()
    }

    pub fn key_named(&mut self, name: &str, pressed: bool) -> Result<()> {
        self.key_evdev(named_evdev(name)?, pressed)
    }

    pub fn release_all(&mut self) -> Result<()> {
        if self.held.is_empty() {
            return Ok(());
        }
        let held: Vec<_> = self.held.iter().copied().collect();
        for code in held {
            self.keyboard()?
                .key(self.time(), code, wl_keyboard::KeyState::Released as u32)
        }
        self.keyboard()?.modifiers(0, 0, 0, 0);
        self.held.clear();
        self.flush()
    }

    pub fn sync(&mut self) -> Result<()> {
        self.sync_timeout(Duration::from_millis(100))
    }
    pub fn sync_timeout(&mut self, timeout: Duration) -> Result<()> {
        let serial = self.next_sync;
        self.next_sync = self
            .next_sync
            .checked_add(1)
            .ok_or_else(|| KeyboardError("sync serial exhausted".into()))?;
        self.connection.display().sync(&self.queue.handle(), serial);
        self.flush()?;
        let deadline = Instant::now()
            .checked_add(timeout)
            .ok_or_else(|| KeyboardError("invalid sync deadline".into()))?;
        loop {
            self.queue
                .dispatch_pending(&mut self.state)
                .map_err(|e| error("keyboard sync dispatch", e))?;
            if self.state.completed_sync >= serial {
                return Ok(());
            }
            let remaining = deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                return Err(KeyboardError(
                    "keyboard compositor acknowledgement timed out".into(),
                ));
            }
            if let Some(guard) = self.queue.prepare_read() {
                let mut fd = libc::pollfd {
                    fd: self.connection.backend().poll_fd().as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                };
                let r = unsafe {
                    libc::poll(
                        &mut fd,
                        1,
                        remaining.as_millis().clamp(1, i32::MAX as u128) as i32,
                    )
                };
                if r < 0 {
                    let e = std::io::Error::last_os_error();
                    if e.kind() == std::io::ErrorKind::Interrupted {
                        continue;
                    }
                    return Err(error("keyboard poll", e));
                }
                if r == 0 {
                    continue;
                }
                if fd.revents & (libc::POLLERR | libc::POLLHUP | libc::POLLNVAL) != 0 {
                    return Err(KeyboardError("keyboard Wayland connection lost".into()));
                }
                if fd.revents & libc::POLLIN != 0 {
                    guard.read().map_err(|e| error("keyboard sync read", e))?;
                }
            }
        }
    }
}
impl Drop for Keyboard {
    fn drop(&mut self) {
        let _ = self.release_all();
        if let Some(keyboard) = self.keyboard.as_ref() {
            keyboard.destroy()
        }
        let _ = self.connection.flush();
    }
}

/// Named key -> Linux evdev code in a canonical German physical layout.
/// Uppercase names denote the same physical key; use an explicit shift modifier.
pub fn named_evdev(name: &str) -> Result<u32> {
    let key = name.to_lowercase();
    let code = match key.as_str() {
        "ctrl" | "control" | "control_l" => 29,
        "control_r" => 97,
        "shift" | "shift_l" => 42,
        "shift_r" => 54,
        "alt" | "alt_l" => 56,
        "altgr" | "alt_r" => 100,
        "super" | "meta" | "logo" | "super_l" => 125,
        "super_r" => 126,
        "enter" | "return" => 28,
        "escape" | "esc" => 1,
        "tab" => 15,
        "backspace" => 14,
        "space" | " " => 57,
        "delete" => 111,
        "insert" => 110,
        "home" => 102,
        "end" => 107,
        "pageup" | "page_up" | "prior" => 104,
        "pagedown" | "page_down" | "next" => 109,
        "up" => 103,
        "down" => 108,
        "left" => 105,
        "right" => 106,
        "a" => 30,
        "b" => 48,
        "c" => 46,
        "d" => 32,
        "e" => 18,
        "f" => 33,
        "g" => 34,
        "h" => 35,
        "i" => 23,
        "j" => 36,
        "k" => 37,
        "l" => 38,
        "m" => 50,
        "n" => 49,
        "o" => 24,
        "p" => 25,
        "q" => 16,
        "r" => 19,
        "s" => 31,
        "t" => 20,
        "u" => 22,
        "v" => 47,
        "w" => 17,
        "x" => 45,
        "y" => 44,
        "z" => 21,
        "1" => 2,
        "2" => 3,
        "3" => 4,
        "4" => 5,
        "5" => 6,
        "6" => 7,
        "7" => 8,
        "8" => 9,
        "9" => 10,
        "0" => 11,
        "ß" => 12,
        "ü" => 26,
        "ö" => 39,
        "ä" => 40,
        "plus" | "+" => 27,
        "minus" | "-" => 53,
        "comma" | "," => 51,
        "period" | "." => 52,
        "less" | "<" => 86,
        "numbersign" | "#" => 43,
        "asciicircum" | "^" => 41,
        "kp_enter" => 96,
        "kp_add" => 78,
        "kp_subtract" => 74,
        "kp_multiply" => 55,
        "kp_divide" => 98,
        "print" | "printscreen" => 99,
        "pause" => 119,
        "f1" => 59,
        "f2" => 60,
        "f3" => 61,
        "f4" => 62,
        "f5" => 63,
        "f6" => 64,
        "f7" => 65,
        "f8" => 66,
        "f9" => 67,
        "f10" => 68,
        "f11" => 87,
        "f12" => 88,
        _ => {
            return Err(KeyboardError(format!(
                "unsupported canonical German key {name:?}; use evdev code deliberately"
            )))
        }
    };
    Ok(code)
}
