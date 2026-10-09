//! Owned, bounded, RAM-only Wayland clipboard paste lease.
//!
//! This helper never types or clicks. The actor owns target validation and input.
//! Regular clipboard only; one compositor seat; wlr-data-control v1/v2.
//! There is no compositor selection compare-and-set: restoration is best effort.
use std::collections::{BTreeMap, HashMap};
use std::io::{self, Write};
use std::os::fd::{AsFd, AsRawFd, FromRawFd, OwnedFd};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};
static CLIPBOARD_CHANGED_POSSIBLE: AtomicBool = AtomicBool::new(false);
use std::time::{Duration, Instant};

use serde::Deserialize;
use serde_json::{json, Value};
use wayland_client::backend::ObjectId;
use wayland_client::protocol::{wl_callback, wl_registry, wl_seat};
use wayland_client::{
    delegate_noop, event_created_child, Connection, Dispatch, EventQueue, Proxy, QueueHandle,
};
use wayland_protocols_wlr::data_control::v1::client::{
    zwlr_data_control_device_v1::{self as device, ZwlrDataControlDeviceV1},
    zwlr_data_control_manager_v1::ZwlrDataControlManagerV1,
    zwlr_data_control_offer_v1::{self as offer, ZwlrDataControlOfferV1},
    zwlr_data_control_source_v1::{self as source, ZwlrDataControlSourceV1},
};

const MAX_MIMES: usize = 32;
const MAX_MIME_BYTES: usize = 256;
const MAX_PER_MIME: usize = 1024 * 1024;
const MAX_TOTAL: usize = 8 * 1024 * 1024;
const MAX_TEXT: usize = 65536;
const MAX_CONTROL_LINE: usize = 2 * MAX_TEXT + 1024;
const MAX_TRANSFERS: usize = 16;
const TICK: Duration = Duration::from_millis(5);
const SCOPE: &str = "bounded RAM-only payload MIME snapshot from one Wayland offer; SAVE_TARGETS control marker omitted; original Chromium provenance restored only with original payload; own source cancellation checked; best effort, no atomic selection CAS";

type Result<T> = std::result::Result<T, String>;
type Data = BTreeMap<String, Arc<[u8]>>;

fn monotonic_ns() -> u64 {
    let mut time = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut time) } != 0 {
        return 0;
    }
    (time.tv_sec as u64)
        .saturating_mul(1_000_000_000)
        .saturating_add(time.tv_nsec as u64)
}
fn absolute_deadline_ns(deadline: Instant) -> u64 {
    monotonic_ns().saturating_add(
        deadline
            .saturating_duration_since(Instant::now())
            .as_nanos()
            .min(u64::MAX as u128) as u64,
    )
}
fn helper_deadline(timeout_ms: u64, absolute: Option<u64>) -> Result<Instant> {
    let mut budget = Duration::from_millis(timeout_ms);
    if let Some(until) = absolute {
        budget = budget.min(Duration::from_nanos(until.saturating_sub(monotonic_ns())));
    }
    if budget.is_zero() {
        return Err("clipboard shared deadline expired".into());
    }
    Ok(Instant::now() + budget)
}

fn set_nonblocking(fd: i32) -> Result<()> {
    let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
    if flags < 0 || unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0 {
        return Err("cannot make clipboard pipe nonblocking".into());
    }
    Ok(())
}

fn new_pipe() -> Result<(OwnedFd, OwnedFd)> {
    let mut pair = [-1; 2];
    if unsafe { libc::pipe2(pair.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) } < 0 {
        return Err("cannot create clipboard transfer pipe".into());
    }
    Ok(unsafe { (OwnedFd::from_raw_fd(pair[0]), OwnedFd::from_raw_fd(pair[1])) })
}

/// Stable representations supported verbatim. Dynamic file-transfer handles and
/// password-manager hints are refused before reading or replacing the selection.
fn supported_mime(mime: &str) -> bool {
    if mime.len() > MAX_MIME_BYTES || mime.is_empty() || mime.chars().any(char::is_control) {
        return false;
    }
    let lower = mime.to_ascii_lowercase();
    lower.starts_with("text/")
        || matches!(
            lower.as_str(),
            "utf8_string"
                | "string"
                | "text"
                | "compound_text"
                | "save_targets"
                | "chromium/x-web-custom-data"
                | "chromium/x-internal-source-rfh-token"
                | "chromium/x-source-url"
                | "application/rtf"
                | "application/x-rtf"
                | "application/json"
                | "application/xml"
                | "application/xhtml+xml"
                | "vscode-editor-data"
                | "application/x-vscode-editor-data"
                | "application/vnd.code.notebook.cell"
                | "x-special/gnome-copied-files"
                | "application/x-kde-cutselection"
                | "image/png"
                | "image/jpeg"
                | "image/webp"
                | "image/bmp"
        )
}

fn validate_mimes(mimes: &[String]) -> Result<()> {
    if mimes.is_empty() || mimes.len() > MAX_MIMES {
        return Err("empty or excessive MIME offer; clipboard unchanged".into());
    }
    if mimes.iter().any(|mime| !supported_mime(mime)) {
        return Err("unsupported or sensitive MIME offer; clipboard unchanged".into());
    }
    Ok(())
}

struct Transfer {
    fd: OwnedFd,
    data: Arc<[u8]>,
    offset: usize,
    deadline: Instant,
}

impl Transfer {
    fn tick(&mut self) -> bool {
        if Instant::now() >= self.deadline {
            return false;
        }
        let remaining = &self.data[self.offset..];
        if remaining.is_empty() {
            return false;
        }
        let count = unsafe {
            libc::write(
                self.fd.as_raw_fd(),
                remaining.as_ptr().cast(),
                remaining.len().min(65536),
            )
        };
        if count > 0 {
            self.offset += count as usize;
            return self.offset < self.data.len();
        }
        if count < 0 {
            return matches!(
                io::Error::last_os_error().kind(),
                io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
            );
        }
        false
    }
}

#[derive(Default)]
struct State {
    manager: Option<ZwlrDataControlManagerV1>,
    seats: Vec<wl_seat::WlSeat>,
    device: Option<ZwlrDataControlDeviceV1>,
    offers: HashMap<ObjectId, (ZwlrDataControlOfferV1, Vec<String>)>,
    selection: Option<ObjectId>,
    selection_generation: u64,
    sources: HashMap<ObjectId, Data>,
    current_source: Option<ObjectId>,
    source_cancelled: bool,
    transfers: Vec<Transfer>,
    completed_sync: u64,
    capability_error: Option<String>,
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
        if let wl_registry::Event::Global {
            name,
            interface,
            version,
        } = event
        {
            if interface == "zwlr_data_control_manager_v1" && state.manager.is_none() {
                state.manager = Some(registry.bind(name, version.min(2), qh, ()));
            } else if interface == "wl_seat" && version >= 2 {
                state.seats.push(registry.bind(name, 2, qh, ()));
            }
        }
    }
}
delegate_noop!(State: ignore wl_seat::WlSeat);
delegate_noop!(State: ignore ZwlrDataControlManagerV1);

impl Dispatch<wl_callback::WlCallback, u64> for State {
    fn event(
        state: &mut Self,
        _: &wl_callback::WlCallback,
        event: wl_callback::Event,
        token: &u64,
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        if matches!(event, wl_callback::Event::Done { .. }) {
            state.completed_sync = state.completed_sync.max(*token);
        }
    }
}

impl Dispatch<ZwlrDataControlDeviceV1, ()> for State {
    event_created_child!(State, ZwlrDataControlDeviceV1, [device::EVT_DATA_OFFER_OPCODE => (ZwlrDataControlOfferV1, ())]);
    fn event(
        state: &mut Self,
        _: &ZwlrDataControlDeviceV1,
        event: device::Event,
        _: &(),
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        match event {
            device::Event::DataOffer { id } => {
                state.offers.insert(id.id(), (id, Vec::new()));
            }
            device::Event::Selection { id } => {
                state.selection_generation += 1;
                state.selection = id.as_ref().map(Proxy::id);
                state.offers.retain(|key, (offer, _)| {
                    if Some(key) == state.selection.as_ref() {
                        true
                    } else {
                        offer.destroy();
                        false
                    }
                });
            }
            device::Event::PrimarySelection { id: Some(id) } => {
                if let Some((offer, _)) = state.offers.remove(&id.id()) {
                    offer.destroy();
                }
            }
            device::Event::Finished => {
                state.capability_error = Some("Wayland clipboard device became unavailable".into());
            }
            _ => (),
        }
    }
}

impl Dispatch<ZwlrDataControlOfferV1, ()> for State {
    fn event(
        state: &mut Self,
        proxy: &ZwlrDataControlOfferV1,
        event: offer::Event,
        _: &(),
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        if let offer::Event::Offer { mime_type } = event {
            if let Some((_, mimes)) = state.offers.get_mut(&proxy.id()) {
                if !mimes.contains(&mime_type) && mimes.len() <= MAX_MIMES {
                    mimes.push(mime_type);
                }
            }
        }
    }
}

impl Dispatch<ZwlrDataControlSourceV1, ()> for State {
    fn event(
        state: &mut Self,
        proxy: &ZwlrDataControlSourceV1,
        event: source::Event,
        _: &(),
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        match event {
            source::Event::Send { mime_type, fd } => {
                if state.transfers.len() >= MAX_TRANSFERS {
                    return;
                }
                if let Some(data) = state
                    .sources
                    .get(&proxy.id())
                    .and_then(|mimes| mimes.get(&mime_type))
                    .cloned()
                {
                    if set_nonblocking(fd.as_raw_fd()).is_ok() {
                        state.transfers.push(Transfer {
                            fd,
                            data,
                            offset: 0,
                            deadline: Instant::now() + Duration::from_secs(2),
                        });
                    }
                }
            }
            source::Event::Cancelled => {
                if state.current_source.as_ref() == Some(&proxy.id()) {
                    state.source_cancelled = true;
                }
                state.sources.remove(&proxy.id());
                proxy.destroy();
            }
            _ => (),
        }
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Start {
    text: String,
    #[serde(default = "yes")]
    preserve: bool,
    timeout_ms: u64,
    #[serde(default)]
    deadline_monotonic_ns: Option<u64>,
}
fn yes() -> bool {
    true
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Control {
    command: String,
    #[serde(default)]
    timeout_ms: u64,
    #[serde(default)]
    deadline_monotonic_ns: Option<u64>,
}

struct Backend {
    connection: Connection,
    queue: EventQueue<State>,
    state: State,
    next_sync: u64,
    control: Vec<u8>,
    stdin_closed: bool,
    abandon: bool,
    controls: Vec<Control>,
    snapshot_ignored: Vec<String>,
}

impl Backend {
    fn new(deadline: Instant) -> Result<Self> {
        set_nonblocking(0)?;
        let connection =
            Connection::connect_to_env().map_err(|_| "cannot connect to Wayland clipboard")?;
        let queue = connection.new_event_queue();
        connection.display().get_registry(&queue.handle(), ());
        let mut backend = Self {
            connection,
            queue,
            state: State::default(),
            next_sync: 0,
            control: Vec::new(),
            stdin_closed: false,
            abandon: false,
            controls: Vec::new(),
            snapshot_ignored: Vec::new(),
        };
        backend.sync(deadline)?;
        if backend.state.seats.len() != 1 {
            return Err("clipboard requires exactly one compositor seat".into());
        }
        let manager = backend
            .state
            .manager
            .as_ref()
            .ok_or("wlr-data-control clipboard capability is unavailable")?;
        backend.state.device =
            Some(manager.get_data_device(&backend.state.seats[0], &backend.queue.handle(), ()));
        backend.sync(deadline)?;
        Ok(backend)
    }

    fn read_control(&mut self) -> Result<()> {
        if self.stdin_closed {
            return Ok(());
        }
        let mut bytes = [0; 2048];
        loop {
            let count = unsafe { libc::read(0, bytes.as_mut_ptr().cast(), bytes.len()) };
            if count == 0 {
                self.stdin_closed = true;
                break;
            }
            if count < 0 {
                if io::Error::last_os_error().kind() == io::ErrorKind::WouldBlock {
                    break;
                }
                if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                return Err("clipboard control pipe failed".into());
            }
            self.control.extend_from_slice(&bytes[..count as usize]);
            if self.control.len() > 8192 {
                return Err("excessive clipboard control request".into());
            }
            while let Some(end) = self.control.iter().position(|b| *b == b'\n') {
                let line = self.control.drain(..=end).collect::<Vec<_>>();
                let request: Control = serde_json::from_slice(&line)
                    .map_err(|_| "invalid clipboard control request")?;
                if request.command == "abandon" {
                    self.abandon = true;
                } else if !matches!(request.command.as_str(), "restore" | "check") {
                    return Err("unknown clipboard control request".into());
                }
                if self.controls.len() > 2 {
                    return Err("duplicate clipboard control request".into());
                }
                self.controls.push(request);
            }
        }
        Ok(())
    }

    fn pump(&mut self, deadline: Instant) -> Result<()> {
        if Instant::now() >= deadline {
            return Err("clipboard deadline expired".into());
        }
        self.read_control()?;
        self.queue
            .dispatch_pending(&mut self.state)
            .map_err(|_| "clipboard Wayland dispatch failed")?;
        self.state.transfers.retain_mut(Transfer::tick);
        if let Some(error) = self.state.capability_error.take() {
            return Err(error);
        }
        match self.connection.flush() {
            Ok(()) => (),
            Err(wayland_client::backend::WaylandError::Io(error))
                if error.kind() == io::ErrorKind::WouldBlock =>
            {
                ()
            }
            Err(_) => return Err("clipboard Wayland flush failed".into()),
        }
        if let Some(guard) = self.queue.prepare_read() {
            let mut poll = libc::pollfd {
                fd: self.connection.backend().poll_fd().as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            let ms = deadline
                .saturating_duration_since(Instant::now())
                .min(TICK)
                .as_millis()
                .max(1) as i32;
            let ready = unsafe { libc::poll(&mut poll, 1, ms) };
            if ready > 0 {
                match guard.read() {
                    Ok(_) => (),
                    Err(wayland_client::backend::WaylandError::Io(error))
                        if error.kind() == io::ErrorKind::WouldBlock =>
                    {
                        ()
                    }
                    Err(_) => return Err("clipboard Wayland read failed".into()),
                }
            } else if ready < 0 && io::Error::last_os_error().kind() != io::ErrorKind::Interrupted {
                return Err("clipboard Wayland poll failed".into());
            }
        }
        self.queue
            .dispatch_pending(&mut self.state)
            .map_err(|_| "clipboard Wayland dispatch failed")?;
        self.read_control()?;
        Ok(())
    }

    fn sync(&mut self, deadline: Instant) -> Result<()> {
        self.next_sync += 1;
        self.connection
            .display()
            .sync(&self.queue.handle(), self.next_sync);
        while self.state.completed_sync < self.next_sync {
            self.pump(deadline)?;
        }
        Ok(())
    }

    fn snapshot(&mut self, deadline: Instant) -> Result<Option<Data>> {
        self.sync(deadline)?;
        let Some(id) = self.state.selection.clone() else {
            return Ok(None);
        };
        let generation = self.state.selection_generation;
        let (offer, mimes) = self
            .state
            .offers
            .get(&id)
            .ok_or("clipboard offer was lost")?
            .clone();
        validate_mimes(&mimes)?;
        // SAVE_TARGETS requests X11 clipboard-manager handoff; it is not an
        // application payload representation. Never read or replay the request.
        self.snapshot_ignored = mimes
            .iter()
            .filter(|mime| mime.eq_ignore_ascii_case("SAVE_TARGETS"))
            .cloned()
            .collect();
        let mimes: Vec<_> = mimes
            .into_iter()
            .filter(|mime| !mime.eq_ignore_ascii_case("SAVE_TARGETS"))
            .collect();
        if mimes.is_empty() {
            return Err("clipboard has only transport markers; no payload preserved".into());
        }
        let mut data = Data::new();
        let mut total = 0;
        for mime in &mimes {
            let (read, write) = new_pipe()?;
            offer.receive(mime.clone(), write.as_fd());
            drop(write);
            self.connection
                .flush()
                .map_err(|_| "clipboard receive flush failed")?;
            let bytes = read_bounded(&read, deadline, MAX_PER_MIME.min(MAX_TOTAL - total), || {
                self.pump(deadline)?;
                if self.abandon || self.stdin_closed {
                    return Err("clipboard snapshot cancelled; clipboard unchanged".into());
                }
                if self.state.selection.as_ref() != Some(&id)
                    || self.state.selection_generation != generation
                {
                    return Err("clipboard changed during snapshot; nothing replaced".into());
                }
                Ok(())
            })?;
            total += bytes.len();
            data.insert(mime.clone(), Arc::from(bytes));
        }
        self.sync(deadline)?;
        if self.abandon || self.stdin_closed {
            return Err("clipboard snapshot cancelled; clipboard unchanged".into());
        }
        if self.state.selection.as_ref() != Some(&id)
            || self.state.selection_generation != generation
        {
            return Err("clipboard changed during snapshot; nothing replaced".into());
        }
        Ok(Some(data))
    }

    fn publish(&mut self, data: Option<Data>, deadline: Instant) -> Result<()> {
        if Instant::now() >= deadline || self.abandon || self.stdin_closed {
            return Err("clipboard publication cancelled before dispatch".into());
        }
        let device = self
            .state
            .device
            .as_ref()
            .ok_or("clipboard device is unavailable")?;
        CLIPBOARD_CHANGED_POSSIBLE.store(true, Ordering::SeqCst);
        if let Some(data) = data {
            let source = self
                .state
                .manager
                .as_ref()
                .ok_or("clipboard manager is unavailable")?
                .create_data_source(&self.queue.handle(), ());
            for mime in data.keys() {
                source.offer(mime.clone());
            }
            self.state.current_source = Some(source.id());
            self.state.source_cancelled = false;
            self.state.sources.insert(source.id(), data);
            device.set_selection(Some(&source));
        } else {
            self.state.current_source = None;
            device.set_selection(None);
        }
        self.sync(deadline)?;
        if self.state.current_source.is_some() && self.state.source_cancelled {
            return Err(
                "clipboard source changed during publication; selection may have changed".into(),
            );
        }
        Ok(())
    }

    fn serve(&mut self) -> Result<()> {
        // Once restoration/abandonment is acknowledged, EOF does not erase the
        // selection. Keep our in-memory source until the compositor cancels it.
        while self.state.current_source.is_some() && !self.state.source_cancelled {
            self.pump(Instant::now() + Duration::from_millis(100))?;
        }
        Ok(())
    }
}

fn read_bounded(
    fd: &OwnedFd,
    deadline: Instant,
    limit: usize,
    mut pump: impl FnMut() -> Result<()>,
) -> Result<Vec<u8>> {
    let mut contents = Vec::new();
    let mut bytes = [0; 16384];
    loop {
        if Instant::now() >= deadline {
            return Err("clipboard transfer deadline expired; nothing replaced".into());
        }
        pump()?;
        let count = unsafe { libc::read(fd.as_raw_fd(), bytes.as_mut_ptr().cast(), bytes.len()) };
        if count == 0 {
            return Ok(contents);
        }
        if count < 0 {
            match io::Error::last_os_error().kind() {
                io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted => continue,
                _ => return Err("clipboard transfer failed; nothing replaced".into()),
            }
        }
        if contents.len() + count as usize > limit {
            return Err("clipboard transfer exceeds RAM limits; nothing replaced".into());
        }
        contents.extend_from_slice(&bytes[..count as usize]);
    }
}

fn reply(value: Value) -> Result<()> {
    let mut output = io::stdout().lock();
    serde_json::to_writer(&mut output, &value)
        .map_err(|_| "clipboard status serialization failed")?;
    output
        .write_all(b"\n")
        .and_then(|_| output.flush())
        .map_err(|_| "clipboard status pipe failed".into())
}

/// Helper mode entry point, intended for `core __clipboard_helper`.
/// Input and control use private inherited pipes, never argv or files.
pub fn helper_main() -> Result<()> {
    let result = helper_main_inner();
    if let Err(error) = &result {
        let _ = reply(
            json!({"state":"failed","error":error,"clipboard_changed_possible":CLIPBOARD_CHANGED_POSSIBLE.load(Ordering::SeqCst),"preservation_scope":SCOPE}),
        );
    }
    result
}

fn helper_main_inner() -> Result<()> {
    let mut line = Vec::new();
    // Read exactly one line, avoiding buffered overread of subsequent controls.
    loop {
        let mut byte = [0u8];
        let count = unsafe { libc::read(0, byte.as_mut_ptr().cast(), 1) };
        if count < 0 {
            return Err("clipboard start pipe failed".into());
        }
        if count == 0 {
            return Err("clipboard start request missing".into());
        }
        line.push(byte[0]);
        if line.len() > MAX_CONTROL_LINE {
            return Err("clipboard start request exceeds bound".into());
        }
        if byte[0] == b'\n' {
            break;
        }
    }
    let start: Start =
        serde_json::from_slice(&line).map_err(|_| "invalid clipboard start request")?;
    if start.text.len() > MAX_TEXT || !(100..=120000).contains(&start.timeout_ms) {
        return Err("invalid clipboard text or deadline bound".into());
    }
    let deadline = helper_deadline(start.timeout_ms, start.deadline_monotonic_ns)?;
    let mut backend = Backend::new(deadline)?;
    let prior = if start.preserve {
        backend.snapshot(deadline)?
    } else {
        None
    };
    let snapshot_count = prior.as_ref().map_or(0, |data| data.len());
    let snapshot_bytes = prior.as_ref().map_or(0, |data| {
        data.values().map(|bytes| bytes.len()).sum::<usize>()
    });
    // No operation that can fail due to unsupported/oversized old data remains.
    let text: Arc<[u8]> = Arc::from(start.text.into_bytes());
    let temporary = [
        "text/plain;charset=utf-8",
        "text/plain",
        "UTF8_STRING",
        "TEXT",
        "STRING",
    ]
    .into_iter()
    .map(|mime| (mime.to_string(), text.clone()))
    .collect();
    backend.publish(Some(temporary), deadline)?;
    reply(
        json!({"state":"ready","clipboard_changed":true,"snapshot_mime_count":snapshot_count,"snapshot_bytes":snapshot_bytes,"snapshot_ignored_transport_mimes":backend.snapshot_ignored,"preservation_scope":SCOPE}),
    )?;
    loop {
        while backend.controls.is_empty() && !backend.stdin_closed {
            backend.pump(Instant::now() + Duration::from_millis(100))?;
        }
        if backend
            .controls
            .first()
            .is_some_and(|request| request.command == "check")
        {
            let request = backend.controls.remove(0);
            let result =
                helper_deadline(request.timeout_ms.min(2000), request.deadline_monotonic_ns)
                    .and_then(|deadline| backend.sync(deadline));
            reply(
                json!({"state":"checked","owned":result.is_ok() && !backend.state.source_cancelled && !backend.abandon && !backend.stdin_closed,"preservation_scope":SCOPE}),
            )?;
            continue;
        }
        break;
    }
    let control = if backend.controls.is_empty() {
        None
    } else {
        Some(backend.controls.remove(0))
    };
    if control
        .as_ref()
        .is_some_and(|request| request.command == "restore")
        && start.preserve
        && !backend.stdin_closed
        && !backend.abandon
    {
        let budget = control.as_ref().unwrap().timeout_ms.min(2000);
        let deadline = helper_deadline(budget, control.as_ref().unwrap().deadline_monotonic_ns)?;
        backend.sync(deadline)?;
        if backend.state.source_cancelled || backend.abandon || backend.stdin_closed {
            reply(
                json!({"state":"restore_skipped","cause":"selection_changed_or_cancelled","preservation_scope":SCOPE}),
            )?;
        } else {
            backend.publish(prior, deadline)?;
            reply(json!({"state":"restored","restored":true,"preservation_scope":SCOPE}))?;
        }
    } else {
        if !backend.stdin_closed {
            reply(
                json!({"state":"restore_skipped","cause":"abandoned_or_selection_changed","preservation_scope":SCOPE}),
            )?;
        }
    }
    backend.serve()
}

/// The actor holds this while sending Ctrl+V, then calls finish after fresh
/// cancellation/ownership guards. The helper retains data after it is detached.
pub struct Lease {
    child: Option<Child>,
    input: Option<ChildStdin>,
    output: Option<ChildStdout>,
    buffered: Vec<u8>,
    pub ready: Value,
}

impl Lease {
    pub fn begin_with_executable(
        executable: &std::path::Path,
        args: &[&str],
        text: &str,
        preserve: bool,
        timeout: Duration,
        cancelled: impl Fn() -> bool,
    ) -> Result<Self> {
        let mut command = Command::new(executable);
        command.args(args);
        Self::begin_command(command, text, preserve, timeout, cancelled)
    }

    /// Separate user scope prevents restarting the actor service from erasing
    /// an already restored clipboard. Scope creates no keyboard/pointer writer.
    /// Unit is random, private to this lease, and collected on source release.
    pub fn begin_in_user_scope(
        systemd_run: &std::path::Path,
        executable: &std::path::Path,
        args: &[&str],
        text: &str,
        preserve: bool,
        timeout: Duration,
        cancelled: impl Fn() -> bool,
    ) -> Result<Self> {
        let mut nonce = [0u8; 8];
        if unsafe { libc::getrandom(nonce.as_mut_ptr().cast(), nonce.len(), libc::GRND_NONBLOCK) }
            != nonce.len() as isize
        {
            return Err("clipboard scope nonce unavailable".into());
        }
        let scope = format!(
            "weasel-clipboard-p{:x}-{:016x}.scope",
            std::process::id(),
            u64::from_ne_bytes(nonce)
        );
        let mut command = Command::new(systemd_run);
        command.args([
            "--user",
            "--scope",
            "--quiet",
            "--collect",
            "--no-ask-password",
            "--expand-environment=no",
            "--slice=app",
            "--property=PartOf=graphical-session.target",
        ]);
        command
            .arg(format!("--unit={scope}"))
            .arg(executable)
            .args(args);
        let mut lease = Self::begin_command(command, text, preserve, timeout, cancelled)?;
        lease.ready["holder_scope"] = json!(scope);
        lease.ready["holder_lifetime"] = json!(
            "until source replacement or graphical session shutdown; independent of actor service"
        );
        Ok(lease)
    }

    fn begin_command(
        mut command: Command,
        text: &str,
        preserve: bool,
        timeout: Duration,
        cancelled: impl Fn() -> bool,
    ) -> Result<Self> {
        if text.len() > MAX_TEXT || timeout < Duration::from_millis(100) {
            return Err("invalid clipboard paste text/budget".into());
        }
        let deadline = Instant::now() + timeout;
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|_| "clipboard helper launch failed")?;
        let input = child.stdin.take().ok_or("clipboard helper input missing")?;
        let output = child
            .stdout
            .take()
            .ok_or("clipboard helper output missing")?;
        let mut lease = Self {
            child: Some(child),
            input: Some(input),
            output: Some(output),
            buffered: Vec::new(),
            ready: Value::Null,
        };
        set_nonblocking(lease.input.as_ref().unwrap().as_raw_fd())?;
        set_nonblocking(lease.output.as_ref().unwrap().as_raw_fd())?;
        let request = json!({"text":text,"preserve":preserve,"timeout_ms":timeout.as_millis().min(120000),"deadline_monotonic_ns":absolute_deadline_ns(deadline)});
        lease.send(&request, deadline, &cancelled)?;
        lease.ready = lease.receive(deadline, &cancelled)?;
        if lease.ready["state"] != "ready" {
            return Err(format!(
                "Clipboard helper refused: {}",
                lease.ready["error"]
                    .as_str()
                    .unwrap_or("did not acknowledge ready")
            ));
        }
        Ok(lease)
    }

    fn send(
        &mut self,
        value: &Value,
        deadline: Instant,
        cancelled: &impl Fn() -> bool,
    ) -> Result<()> {
        let mut bytes =
            serde_json::to_vec(value).map_err(|_| "clipboard control serialization failed")?;
        bytes.push(b'\n');
        let fd = self
            .input
            .as_ref()
            .ok_or("clipboard helper input unavailable")?
            .as_raw_fd();
        let mut offset = 0;
        while offset < bytes.len() {
            if cancelled() || Instant::now() >= deadline {
                return Err(
                    "clipboard request cancelled or timed out; mutation may have occurred".into(),
                );
            }
            let count =
                unsafe { libc::write(fd, bytes[offset..].as_ptr().cast(), bytes.len() - offset) };
            if count > 0 {
                offset += count as usize;
            } else if count < 0
                && matches!(
                    io::Error::last_os_error().kind(),
                    io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                )
            {
                std::thread::sleep(TICK);
            } else {
                return Err("clipboard helper write failed; mutation may have occurred".into());
            }
        }
        Ok(())
    }

    fn receive(&mut self, deadline: Instant, cancelled: &impl Fn() -> bool) -> Result<Value> {
        let fd = self
            .output
            .as_ref()
            .ok_or("clipboard helper output unavailable")?
            .as_raw_fd();
        let mut buffer = [0; 2048];
        loop {
            if let Some(end) = self.buffered.iter().position(|byte| *byte == b'\n') {
                return serde_json::from_slice(&self.buffered.drain(..=end).collect::<Vec<_>>())
                    .map_err(|_| "clipboard helper returned malformed status".into());
            }
            if cancelled() || Instant::now() >= deadline {
                return Err(
                    "clipboard request cancelled or timed out; mutation may have occurred".into(),
                );
            }
            let count = unsafe { libc::read(fd, buffer.as_mut_ptr().cast(), buffer.len()) };
            if count == 0 {
                return Err("clipboard helper closed; mutation may have occurred".into());
            }
            if count < 0 {
                if matches!(
                    io::Error::last_os_error().kind(),
                    io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                ) {
                    std::thread::sleep(TICK);
                    continue;
                }
                return Err("clipboard helper read failed; mutation may have occurred".into());
            }
            self.buffered.extend_from_slice(&buffer[..count as usize]);
            if self.buffered.len() > 8192 {
                return Err("clipboard helper status exceeded bound".into());
            }
        }
    }

    // A delayed ownership-check reply is not an acknowledgement that restore
    // or abandon has finished. Never release the actor on an unrelated status.
    fn receive_terminal(
        &mut self,
        deadline: Instant,
        cancelled: &impl Fn() -> bool,
    ) -> Result<Value> {
        loop {
            if cancelled() || Instant::now() >= deadline {
                return Err("clipboard terminal acknowledgement cancelled or timed out; mutation may have occurred".into());
            }
            let response = self.receive(deadline, cancelled)?;
            match response["state"].as_str() {
                Some("restored" | "restore_skipped") => return Ok(response),
                Some("checked") => continue,
                Some("failed") => {
                    return Err(format!(
                        "clipboard helper terminal operation failed: {}",
                        response["error"].as_str().unwrap_or("unspecified failure")
                    ))
                }
                _ => {
                    return Err("clipboard helper returned an unexpected nonterminal status".into())
                }
            }
        }
    }

    /// Fresh source identity check for the actor pre-dispatch hook. The
    /// compositor protocol has no atomic check-and-paste operation: ownership
    /// can still change between this reply and the input event. A text-equal
    /// external copy is still a different selection owner.
    pub fn check_owned(&mut self, timeout: Duration, cancelled: impl Fn() -> bool) -> Result<bool> {
        let deadline = Instant::now() + timeout;
        self.send(
            &json!({"command":"check","timeout_ms":timeout.as_millis().min(2000),"deadline_monotonic_ns":absolute_deadline_ns(deadline)}),
            deadline,
            &cancelled,
        )?;
        let response = self.receive(deadline, &cancelled)?;
        if response["state"] != "checked" {
            return Err("clipboard ownership check was not acknowledged".into());
        }
        Ok(response["owned"].as_bool() == Some(true))
    }

    /// `restore=false` or cancellation abandons restoration. This does not clear
    /// any selection: the current source is kept until some client replaces it.
    pub fn finish(
        mut self,
        restore: bool,
        timeout: Duration,
        cancelled: impl Fn() -> bool,
    ) -> Result<Value> {
        let deadline = Instant::now() + timeout;
        let should_restore = restore && !cancelled() && !timeout.is_zero();
        if cancelled() || timeout.is_zero() {
            self.best_effort_abandon();
            self.detach();
            return Ok(
                json!({"state":"restore_skipped","cause":"caller_cancelled_or_deadline","restored":false,"preservation_scope":SCOPE}),
            );
        }
        let request = json!({"command":if should_restore {"restore"} else {"abandon"},"timeout_ms":timeout.as_millis().min(2000),"deadline_monotonic_ns":absolute_deadline_ns(deadline)});
        let sent = self.send(&request, deadline, &cancelled);
        let result = match sent {
            Ok(()) => self.receive_terminal(deadline, &cancelled),
            Err(error) => Err(error),
        };
        if result.is_err() {
            self.best_effort_abandon();
            // A cancellation must not leave a queued restoration able to run
            // after the actor has reported itself stopped. Drain one helper
            // acknowledgement with a bounded cleanup budget. No restore is
            // requested here. If it cannot quiesce, terminate the owned helper.
            let quiesced = self.receive_terminal(
                deadline.min(Instant::now() + Duration::from_millis(100)),
                &|| false,
            );
            if quiesced.is_err() {
                self.terminate_owned_helper();
            }
        }
        self.detach();
        result
    }

    fn best_effort_abandon(&mut self) {
        if let Some(input) = self.input.as_ref() {
            let bytes = b"{\"command\":\"abandon\",\"timeout_ms\":0}\n";
            unsafe {
                libc::write(input.as_raw_fd(), bytes.as_ptr().cast(), bytes.len());
            }
        }
    }

    fn detach(&mut self) {
        self.input.take();
        self.output.take();
        if let Some(mut child) = self.child.take() {
            // Wait/reap independently while the owned helper serves this one
            // clipboard source. No general background retries or GUI actions.
            std::thread::spawn(move || {
                let _ = child.wait();
            });
        }
    }

    fn terminate_owned_helper(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let until = Instant::now() + Duration::from_millis(100);
            while Instant::now() < until {
                if child.try_wait().ok().flatten().is_some() {
                    return;
                }
                std::thread::sleep(Duration::from_millis(1));
            }
            std::thread::spawn(move || {
                let _ = child.wait();
            });
        }
    }
}

impl Drop for Lease {
    fn drop(&mut self) {
        if self.ready["state"] == "ready" {
            self.best_effort_abandon();
            self.detach();
        } else {
            self.terminate_owned_helper();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fake_ready_lease(script: &str) -> (Lease, u32) {
        // Deterministic status-only fixture. No Wayland, GUI, real clipboard,
        // systemd unit or user content; the child speaks private inherited pipes.
        let mut child = Command::new("sh")
            .args(["-c", script])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        let pid = child.id();
        let input = child.stdin.take().unwrap();
        let output = child.stdout.take().unwrap();
        set_nonblocking(input.as_raw_fd()).unwrap();
        set_nonblocking(output.as_raw_fd()).unwrap();
        (
            Lease {
                child: Some(child),
                input: Some(input),
                output: Some(output),
                buffered: Vec::new(),
                ready: json!({"state":"ready"}),
            },
            pid,
        )
    }

    fn assert_fixture_terminated(pid: u32) {
        let alive = unsafe { libc::kill(pid as i32, 0) } == 0;
        // Ensure even a regressed implementation cannot leave its mock helper.
        if alive {
            unsafe {
                libc::kill(pid as i32, libc::SIGKILL);
            }
        }
        assert!(
            !alive,
            "a nonterminal helper must be terminated, not detached"
        );
    }

    #[test]
    fn finish_drains_late_checked_until_terminal_restore() {
        let (lease, _) = fake_ready_lease(
            r#"
IFS= read -r request
printf '%s\n' '{"state":"checked","owned":true}'
sleep 0.02
printf '%s\n' '{"state":"restored","restored":true}'
"#,
        );
        let result = lease
            .finish(true, Duration::from_millis(500), || false)
            .unwrap();
        assert_eq!(result["state"], "restored");
    }

    #[test]
    fn failed_preservation_is_error_and_checked_is_not_quiescence() {
        let (lease, pid) = fake_ready_lease(
            r#"
IFS= read -r request
printf '%s\n' '{"state":"failed","error":"fixture preservation failure"}'
IFS= read -r abandon
printf '%s\n' '{"state":"checked","owned":false}'
exec sleep 30
"#,
        );
        let result = lease.finish(true, Duration::from_millis(500), || false);
        assert_fixture_terminated(pid);
        assert!(result.unwrap_err().contains("terminal operation failed"));
    }

    #[test]
    fn cancelled_cleanup_drains_checked_then_terminates_without_terminal() {
        let (lease, pid) = fake_ready_lease(
            r#"
IFS= read -r request
IFS= read -r abandon
printf '%s\n' '{"state":"checked","owned":false}'
exec sleep 30
"#,
        );
        let begin = Instant::now();
        let result = lease.finish(true, Duration::from_millis(500), || {
            begin.elapsed() >= Duration::from_millis(30)
        });
        assert_fixture_terminated(pid);
        assert!(result.unwrap_err().contains("cancelled or timed out"));
        assert!(begin.elapsed() < Duration::from_millis(500));
    }

    #[test]
    fn deadline_without_terminal_acknowledgement_terminates_helper() {
        let (lease, pid) = fake_ready_lease(
            r#"
IFS= read -r request
printf '%s\n' '{"state":"checked","owned":true}'
IFS= read -r abandon
printf '%s\n' '{"state":"checked","owned":false}'
exec sleep 30
"#,
        );
        let begin = Instant::now();
        let result = lease.finish(true, Duration::from_millis(70), || false);
        assert_fixture_terminated(pid);
        assert!(result.unwrap_err().contains("cancelled or timed out"));
        assert!(begin.elapsed() < Duration::from_millis(250));
    }

    #[test]
    fn unexpected_status_cannot_finish_or_confirm_cleanup() {
        let (lease, pid) = fake_ready_lease(
            r#"
IFS= read -r request
printf '%s\n' '{"state":"ready"}'
IFS= read -r abandon
printf '%s\n' '{"state":"checked","owned":false}'
exec sleep 30
"#,
        );
        let result = lease.finish(true, Duration::from_millis(500), || false);
        assert_fixture_terminated(pid);
        assert!(result.unwrap_err().contains("unexpected nonterminal"));
    }

    #[test]
    fn rich_text_and_code_metadata_are_preservable() {
        let types = [
            "text/plain;charset=utf-8",
            "text/html",
            "vscode-editor-data",
            "UTF8_STRING",
        ]
        .map(str::to_string);
        validate_mimes(&types).unwrap();
    }
    #[test]
    fn dynamic_portal_and_sensitive_hints_refuse_before_reads() {
        for forbidden in [
            "application/vnd.portal.filetransfer",
            "x-kde-passwordManagerHint",
            "application/x-secret",
        ] {
            assert!(validate_mimes(&["text/plain".into(), forbidden.into()]).is_err());
        }
    }
    #[test]
    fn count_duplicate_and_malformed_mime_guards() {
        assert!(validate_mimes(&vec!["text/plain".into(); 33]).is_err());
        assert!(validate_mimes(&["text/plain".into(), "text/plain".into()]).is_ok());
        assert!(validate_mimes(&["text/plain\nmalformed".into()]).is_err());
    }
    #[test]
    fn transfer_stall_honors_deadline() {
        let (read, _writer_keeps_pipe_open) = new_pipe().unwrap();
        let begin = Instant::now();
        let result = read_bounded(&read, begin + Duration::from_millis(30), 128, || {
            std::thread::sleep(Duration::from_millis(1));
            Ok(())
        });
        assert!(result.is_err());
        assert!(begin.elapsed() < Duration::from_millis(80));
    }
    #[test]
    fn oversized_snapshot_refuses_without_truncation() {
        let (read, write) = new_pipe().unwrap();
        assert_eq!(
            unsafe { libc::write(write.as_raw_fd(), b"123456789".as_ptr().cast(), 9) },
            9
        );
        drop(write);
        assert!(
            read_bounded(&read, Instant::now() + Duration::from_secs(1), 8, || Ok(())).is_err()
        );
    }
    #[test]
    fn binary_and_unicode_snapshot_exact() {
        let (read, write) = new_pipe().unwrap();
        let expected = "äöüß 😀\0\n".as_bytes();
        assert_eq!(
            unsafe { libc::write(write.as_raw_fd(), expected.as_ptr().cast(), expected.len()) },
            expected.len() as isize
        );
        drop(write);
        assert_eq!(
            read_bounded(&read, Instant::now() + Duration::from_secs(1), 128, || Ok(
                ()
            ))
            .unwrap(),
            expected
        );
    }
    #[test]
    fn changed_source_aborts_snapshot_immediately() {
        let (read, _write) = new_pipe().unwrap();
        let begin = Instant::now();
        let result = read_bounded(&read, begin + Duration::from_secs(1), 128, || {
            Err("selection changed".into())
        });
        assert!(result.is_err());
        assert!(begin.elapsed() < Duration::from_millis(20));
    }
    #[test]
    fn blocked_paste_consumer_does_not_block_actor_eventloop() {
        let (_read, write) = new_pipe().unwrap();
        let capacity = unsafe { libc::fcntl(write.as_raw_fd(), libc::F_GETPIPE_SZ) } as usize;
        let mut transfer = Transfer {
            fd: write,
            data: Arc::from(vec![7; capacity + 65536]),
            offset: 0,
            deadline: Instant::now() + Duration::from_millis(25),
        };
        let begin = Instant::now();
        while transfer.tick() {
            std::thread::sleep(Duration::from_millis(1));
        }
        assert!(begin.elapsed() < Duration::from_millis(75));
        assert!(transfer.offset < transfer.data.len());
    }
}
