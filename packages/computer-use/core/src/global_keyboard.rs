//! Owned Linux uinput keyboard for compositor shortcuts only.
//! Constructing this device is a capability side effect. Never do so in an
//! observation or while another agent owns the physical desktop.
use std::{
    collections::BTreeSet,
    env, fs, io,
    os::{
        fd::{AsRawFd, FromRawFd, OwnedFd},
        unix::{
            fs::{FileTypeExt, MetadataExt, OpenOptionsExt},
            net::UnixStream,
        },
    },
    path::{Path, PathBuf},
    time::{Duration, Instant},
};

type R<T> = Result<T, String>;
const UI_DEV_CREATE: libc::c_ulong = 0x5501;
const UI_DEV_DESTROY: libc::c_ulong = 0x5502;
const UI_DEV_SETUP: libc::c_ulong = 0x405c5503;
const UI_SET_EVBIT: libc::c_ulong = 0x40045564;
const UI_SET_KEYBIT: libc::c_ulong = 0x40045565;
const UI_GET_VERSION: libc::c_ulong = 0x8004552d;
const UI_GET_SYSNAME_80: libc::c_ulong = 0x8050552c;
const EV_KEY: u16 = 1;

#[repr(C)]
#[derive(Default)]
struct InputId {
    bustype: u16,
    vendor: u16,
    product: u16,
    version: u16,
}
#[repr(C)]
struct Setup {
    id: InputId,
    name: [u8; 80],
    ff_effects_max: u32,
}

pub fn requires_global(codes: &[u32]) -> bool {
    codes.iter().any(|c| matches!(c, 125 | 126))
}

pub fn permission_available() -> R<()> {
    #[cfg(not(all(target_os = "linux", target_arch = "x86_64")))]
    return Err("Global shortcuts require the calibrated Linux x86_64 uinput ABI".into());
    let m = fs::symlink_metadata("/dev/uinput")
        .map_err(|_| "Global uinput device is unavailable; no input sent")?;
    if !m.file_type().is_char_device() || m.rdev() != libc::makedev(10, 223) || m.uid() != 0 {
        return Err("Global uinput path must be the root-owned kernel character device 10:223; no input sent".into());
    }
    if unsafe { libc::access(c"/dev/uinput".as_ptr(), libc::R_OK | libc::W_OK) } != 0 {
        return Err("Global shortcut permission unavailable on /dev/uinput; no input sent".into());
    }
    if env::var_os("NIRI_SOCKET").is_none() {
        return Err(
            "NIRI_SOCKET missing; compositor identity cannot be verified; no input sent".into(),
        );
    }
    Ok(())
}

fn io_error(context: &str) -> String {
    format!("{context}: {}", io::Error::last_os_error())
}
fn check_deadline(deadline: Instant) -> R<()> {
    if Instant::now() >= deadline {
        Err("Global keyboard deadline elapsed".into())
    } else {
        Ok(())
    }
}
fn ioctl_scalar(fd: i32, request: libc::c_ulong, value: u32) -> R<()> {
    if unsafe { libc::ioctl(fd, request, value as libc::c_ulong) } < 0 {
        Err(io_error("uinput capability ioctl"))
    } else {
        Ok(())
    }
}
fn ioctl_ptr<T>(fd: i32, request: libc::c_ulong, value: &mut T) -> R<()> {
    if unsafe { libc::ioctl(fd, request, value as *mut T) } < 0 {
        Err(io_error("uinput setup ioctl"))
    } else {
        Ok(())
    }
}
fn supported_codes() -> Vec<u32> {
    let names = [
        "ctrl",
        "control_r",
        "shift",
        "shift_r",
        "alt",
        "altgr",
        "super",
        "super_r",
        "Return",
        "Escape",
        "Tab",
        "Backspace",
        "space",
        "Delete",
        "Insert",
        "Home",
        "End",
        "PageUp",
        "PageDown",
        "Up",
        "Down",
        "Left",
        "Right",
        "ß",
        "ü",
        "ö",
        "ä",
        "plus",
        "minus",
        "comma",
        "period",
        "less",
        "numbersign",
        "asciicircum",
        "kp_enter",
        "kp_add",
        "kp_subtract",
        "kp_multiply",
        "kp_divide",
        "Print",
        "Pause",
    ];
    let mut codes: BTreeSet<u32> = names
        .iter()
        .map(|n| keyboard::named_evdev(n).unwrap())
        .collect();
    for name in ('a'..='z')
        .map(|c| c.to_string())
        .chain(('0'..='9').map(|c| c.to_string()))
        .chain((1..=12).map(|i| format!("f{i}")))
    {
        codes.insert(keyboard::named_evdev(&name).unwrap());
    }
    codes.into_iter().collect()
}

#[derive(Clone)]
struct Peer {
    pid: i32,
    start: String,
}
fn process_start(pid: i32) -> R<String> {
    let data = fs::read_to_string(format!("/proc/{pid}/stat"))
        .map_err(|_| "Niri process identity unavailable")?;
    let fields = data
        .rsplit_once(')')
        .ok_or("Niri process stat invalid")?
        .1
        .split_whitespace()
        .collect::<Vec<_>>();
    fields
        .get(19)
        .map(|s| s.to_string())
        .ok_or("Niri process start identity invalid".into())
}
fn compositor_peer(deadline: Instant, check: &mut dyn FnMut() -> R<()>) -> R<Peer> {
    check_deadline(deadline)?;
    let path = env::var_os("NIRI_SOCKET").ok_or("NIRI_SOCKET unavailable")?;
    use std::os::unix::ffi::OsStrExt;
    let bytes = path.as_bytes();
    if bytes.is_empty() || bytes.len() >= 108 || bytes.contains(&0) || bytes[0] != b'/' {
        return Err("Niri socket pathname invalid".into());
    }
    let raw = unsafe {
        libc::socket(
            libc::AF_UNIX,
            libc::SOCK_STREAM | libc::SOCK_NONBLOCK | libc::SOCK_CLOEXEC,
            0,
        )
    };
    if raw < 0 {
        return Err(io_error("Niri peer socket"));
    }
    let fd = unsafe { OwnedFd::from_raw_fd(raw) };
    let mut addr: libc::sockaddr_un = unsafe { std::mem::zeroed() };
    addr.sun_family = libc::AF_UNIX as _;
    for (dst, src) in addr.sun_path.iter_mut().zip(bytes) {
        *dst = *src as libc::c_char;
    }
    let result = unsafe {
        libc::connect(
            raw,
            &addr as *const _ as *const libc::sockaddr,
            (2 + bytes.len() + 1) as libc::socklen_t,
        )
    };
    if result < 0 {
        let error = io::Error::last_os_error();
        if !matches!(error.raw_os_error(), Some(libc::EINPROGRESS)) {
            return Err(format!("Niri peer connect: {error}"));
        }
        wait_fd(raw, libc::POLLOUT, deadline, check)?;
        let mut socket_error: i32 = 0;
        let mut length = std::mem::size_of::<i32>() as libc::socklen_t;
        if unsafe {
            libc::getsockopt(
                raw,
                libc::SOL_SOCKET,
                libc::SO_ERROR,
                &mut socket_error as *mut _ as *mut _,
                &mut length,
            )
        } < 0
            || socket_error != 0
        {
            return Err("Niri peer connection failed".into());
        }
    }
    let stream = UnixStream::from(fd);
    let mut credentials: libc::ucred = unsafe { std::mem::zeroed() };
    let mut length = std::mem::size_of::<libc::ucred>() as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            stream.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            &mut credentials as *mut _ as *mut _,
            &mut length,
        )
    } < 0
    {
        return Err(io_error("Niri SO_PEERCRED"));
    }
    if length as usize != std::mem::size_of::<libc::ucred>()
        || credentials.pid <= 0
        || credentials.uid != unsafe { libc::geteuid() }
    {
        return Err("Niri socket peer must be the current user's compositor process".into());
    }
    if fs::read_to_string(format!("/proc/{}/comm", credentials.pid))
        .map_err(|_| "Niri peer comm unavailable")?
        .trim()
        != "niri"
    {
        return Err("Socket peer is not Niri".into());
    }
    Ok(Peer {
        pid: credentials.pid,
        start: process_start(credentials.pid)?,
    })
}
fn wait_fd(fd: i32, events: i16, deadline: Instant, check: &mut dyn FnMut() -> R<()>) -> R<()> {
    loop {
        check()?;
        check_deadline(deadline)?;
        let mut p = libc::pollfd {
            fd,
            events,
            revents: 0,
        };
        let ms = deadline
            .saturating_duration_since(Instant::now())
            .as_millis()
            .clamp(1, 5) as i32;
        let n = unsafe { libc::poll(&mut p, 1, ms) };
        if n < 0 {
            if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(io_error("Global keyboard poll"));
        }
        if p.revents & (libc::POLLERR | libc::POLLHUP | libc::POLLNVAL) != 0 {
            return Err("Global keyboard fd unavailable".into());
        }
        if p.revents & events != 0 {
            return Ok(());
        }
    }
}

pub struct GlobalKeyboard {
    file: Option<fs::File>,
    name: String,
    sysname: String,
    peer: Peer,
    event_rdev: Option<u64>,
    held: Vec<u32>,
    healthy: bool,
}
impl GlobalKeyboard {
    /// Creates and owns exactly one kernel device. Emits no key events.
    /// All failures close/destroy this own device; no fallback input is sent.
    pub fn prepare(deadline: Instant, mut check: impl FnMut() -> R<()>) -> R<Self> {
        permission_available()?;
        check()?;
        check_deadline(deadline)?;
        let peer = compositor_peer(deadline, &mut check)?;
        let file = fs::OpenOptions::new()
            .read(true)
            .write(true)
            .custom_flags(libc::O_NONBLOCK | libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open("/dev/uinput")
            .map_err(|e| format!("Open own uinput device: {e}"))?;
        let m = file
            .metadata()
            .map_err(|_| "Own uinput fd metadata unavailable")?;
        if !m.file_type().is_char_device() || m.rdev() != libc::makedev(10, 223) || m.uid() != 0 {
            return Err("Opened uinput identity changed".into());
        }
        let name = format!("weasel-cu-global-{}", std::process::id());
        let mut result = Self {
            file: Some(file),
            name,
            sysname: String::new(),
            peer,
            event_rdev: None,
            held: Vec::new(),
            healthy: true,
        };
        let fd = result.fd()?;
        let mut version: u32 = 0;
        ioctl_ptr(fd, UI_GET_VERSION, &mut version)?;
        if version < 5 {
            return Err(
                "Global uinput requires modern UI_DEV_SETUP protocol5; no legacy fallback".into(),
            );
        }
        check()?;
        check_deadline(deadline)?;
        ioctl_scalar(fd, UI_SET_EVBIT, EV_KEY as u32)?;
        for code in supported_codes() {
            check()?;
            check_deadline(deadline)?;
            ioctl_scalar(fd, UI_SET_KEYBIT, code)?;
        }
        let mut setup = Setup {
            id: InputId {
                bustype: 6,
                vendor: 0x1d6b,
                product: 0x0001,
                version: 1,
            },
            name: [0; 80],
            ff_effects_max: 0,
        };
        setup.name[..result.name.len()].copy_from_slice(result.name.as_bytes());
        check()?;
        check_deadline(deadline)?;
        ioctl_ptr(fd, UI_DEV_SETUP, &mut setup)?;
        // Drop attempts DESTROY even if CREATE reports failure after partial work.
        check()?;
        check_deadline(deadline)?;
        ioctl_scalar(fd, UI_DEV_CREATE, 0)?;
        let mut sysname = [0u8; 80];
        ioctl_ptr(fd, UI_GET_SYSNAME_80, &mut sysname)?;
        let len = sysname
            .iter()
            .position(|b| *b == 0)
            .ok_or("Kernel sysname unterminated")?;
        result.sysname = std::str::from_utf8(&sysname[..len])
            .map_err(|_| "Kernel sysname invalid")?
            .to_string();
        if !valid_sysname(&result.sysname) {
            return Err("Kernel uinput sysname is invalid".into());
        }
        result.wait_opened(deadline, &mut check)?;
        Ok(result)
    }
    fn fd(&self) -> R<i32> {
        self.file
            .as_ref()
            .map(AsRawFd::as_raw_fd)
            .ok_or("Own global keyboard disconnected; restart backend and explicitly resume".into())
    }
    pub fn ensure_opened(&mut self, deadline: Instant, check: impl FnMut() -> R<()>) -> R<()> {
        if !self.healthy {
            return Err(
                "Global keyboard failed; restart own backend and explicitly resume; no fallback"
                    .into(),
            );
        }
        self.wait_opened(deadline, check)
    }
    fn wait_opened(&mut self, deadline: Instant, mut check: impl FnMut() -> R<()>) -> R<()> {
        let directory = PathBuf::from("/sys/devices/virtual/input").join(&self.sysname);
        loop {
            check()?;
            check_deadline(deadline)?;
            if process_start(self.peer.pid)? != self.peer.start {
                return Err("Niri peer changed during global keyboard readiness".into());
            }
            if fs::read_to_string(directory.join("name"))
                .ok()
                .as_deref()
                .map(str::trim)
                != Some(self.name.as_str())
            {
                return Err("Own uinput sysfs identity changed".into());
            }
            let mut events = Vec::new();
            for entry in fs::read_dir(&directory)
                .map_err(|_| "Own uinput sysfs missing")?
                .take(64)
            {
                check()?;
                check_deadline(deadline)?;
                let entry = entry.map_err(|_| "Own uinput sysfs unreadable")?;
                let name = entry.file_name();
                let name = name.to_string_lossy();
                if valid_event_name(&name) {
                    let path = Path::new("/dev/input").join(name.as_ref());
                    let identity =
                        fs::read_to_string(entry.path().join("dev"))
                            .ok()
                            .and_then(|v| {
                                let (major, minor) = v.trim().split_once(':')?;
                                Some(libc::makedev(
                                    major.parse::<u32>().ok()?,
                                    minor.parse::<u32>().ok()?,
                                ))
                            });
                    if let Ok(m) = fs::symlink_metadata(path) {
                        if m.file_type().is_char_device()
                            && m.uid() == 0
                            && libc::major(m.rdev()) == 13
                            && Some(m.rdev()) == identity
                        {
                            events.push(m.rdev())
                        }
                    }
                }
            }
            if events.len() > 1 {
                return Err("Own uinput device exposes ambiguous event nodes".into());
            }
            if let Some(rdev) = events.first().copied() {
                if self.event_rdev.is_some_and(|prior| prior != rdev) {
                    return Err("Own global event node changed".into());
                }
                let mut fds = fs::read_dir(format!("/proc/{}/fd", self.peer.pid))
                    .map_err(|_| "Niri input fd readiness cannot be inspected")?;
                let mut opened = false;
                for _ in 0..4096 {
                    check()?;
                    check_deadline(deadline)?;
                    let Some(entry) = fds.next() else { break };
                    let entry = entry.map_err(|_| "Niri fd enumeration failed")?;
                    if fs::metadata(entry.path())
                        .is_ok_and(|m| m.file_type().is_char_device() && m.rdev() == rdev)
                    {
                        opened = true;
                        break;
                    }
                }
                if opened {
                    check()?;
                    check_deadline(deadline)?;
                    if process_start(self.peer.pid)? != self.peer.start {
                        return Err(
                            "Niri peer changed before global keyboard readiness acknowledgement"
                                .into(),
                        );
                    }
                    self.event_rdev = Some(rdev);
                    return Ok(());
                }
            }
            // Device-open gate, not a compositor/application result acknowledgement.
            std::thread::sleep(Duration::from_millis(5));
        }
    }
    pub fn key(
        &mut self,
        code: u32,
        pressed: bool,
        deadline: Instant,
        check: impl FnMut() -> R<()>,
    ) -> R<()> {
        self.key_with_writer(code, pressed, deadline, check, write_packet)
    }
    fn key_with_writer(
        &mut self,
        code: u32,
        pressed: bool,
        deadline: Instant,
        mut check: impl FnMut() -> R<()>,
        mut write: impl FnMut(i32, &[u8], Instant, &mut dyn FnMut() -> R<()>) -> R<()>,
    ) -> R<()> {
        check()?;
        check_deadline(deadline)?;
        if !self.healthy {
            return Err("Global keyboard is unhealthy; no further input".into());
        }
        if !supported_codes().contains(&code) {
            return Err("Global key code unsupported".into());
        }
        if self.held.contains(&code) == pressed {
            return Err("Duplicate global key transition refused".into());
        }
        // Track a potential press BEFORE writing: a partial packet may have a
        // key effect even when its SYN acknowledgement subsequently fails.
        if pressed {
            self.held.push(code);
        }
        let result = self
            .fd()
            .and_then(|fd| write(fd, &event_packet(code, pressed), deadline, &mut check));
        if result.is_err() {
            self.healthy = false;
        }
        if result.is_ok() && !pressed {
            self.held.retain(|k| *k != code);
        }
        result
    }
    fn emit(
        &self,
        code: u32,
        pressed: bool,
        deadline: Instant,
        check: &mut dyn FnMut() -> R<()>,
    ) -> R<()> {
        write_packet(self.fd()?, &event_packet(code, pressed), deadline, check)
    }
    pub fn release_all(&mut self) -> R<()> {
        self.release_all_until(Instant::now() + Duration::from_millis(100))
    }
    // Explicit recovery shares one bounded budget; normal cleanup stays100ms.
    pub fn release_all_until(&mut self, deadline: Instant) -> R<()> {
        let mut error = None;
        for code in self.held.clone().into_iter().rev() {
            match self.emit(code, false, deadline, &mut || Ok(())) {
                Ok(()) => self.held.retain(|k| *k != code),
                Err(e) => {
                    if error.is_none() {
                        error = Some(e)
                    }
                }
            }
        }
        if let Some(error) = error {
            self.healthy = false;
            self.destroy();
            return Err(format!(
                "Global release unconfirmed; own device closed: {error}"
            ));
        }
        if !self.healthy {
            self.destroy();
            return Err(
                "Global transport failed; own device closed; release remains unconfirmed".into(),
            );
        }
        Ok(())
    }
    fn destroy(&mut self) {
        if let Some(file) = self.file.take() {
            unsafe { libc::ioctl(file.as_raw_fd(), UI_DEV_DESTROY) };
            drop(file);
        }
        self.held.clear();
        self.healthy = false;
    }
}
impl Drop for GlobalKeyboard {
    fn drop(&mut self) {
        let _ = self.release_all();
        self.destroy();
    }
}
fn valid_sysname(name: &str) -> bool {
    name.strip_prefix("input")
        .is_some_and(|n| !n.is_empty() && n.bytes().all(|b| b.is_ascii_digit()))
}
fn valid_event_name(name: &str) -> bool {
    name.strip_prefix("event")
        .is_some_and(|n| !n.is_empty() && n.bytes().all(|b| b.is_ascii_digit()))
}
fn event_packet(code: u32, pressed: bool) -> [u8; 48] {
    let mut packet = [0u8; 48];
    // Linux x86_64 input_event timeval is16bytes, then type2/code2/value4.
    packet[16..18].copy_from_slice(&EV_KEY.to_ne_bytes());
    packet[18..20].copy_from_slice(&(code as u16).to_ne_bytes());
    packet[20..24].copy_from_slice(&(if pressed { 1i32 } else { 0i32 }).to_ne_bytes());
    packet
}
fn write_packet(
    fd: i32,
    packet: &[u8],
    deadline: Instant,
    check: &mut dyn FnMut() -> R<()>,
) -> R<()> {
    let mut offset = 0;
    while offset < packet.len() {
        check()?;
        check_deadline(deadline)?;
        let n = unsafe {
            libc::write(
                fd,
                packet[offset..].as_ptr() as *const _,
                packet.len() - offset,
            )
        };
        if n < 0 {
            let error = io::Error::last_os_error();
            match error.kind() {
                io::ErrorKind::Interrupted => continue,
                io::ErrorKind::WouldBlock => {
                    wait_fd(fd, libc::POLLOUT, deadline, check)?;
                    continue;
                }
                _ => return Err(format!("Global keyboard write: {error}")),
            }
        }
        if n == 0 {
            return Err("Global keyboard zero-length write".into());
        }
        if n as usize % 24 != 0 {
            return Err("Global keyboard partial event boundary; effect uncertain".into());
        }
        offset += n as usize;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn abi_and_routing_without_devices() {
        assert_eq!(std::mem::size_of::<Setup>(), 92);
        assert_eq!(std::mem::size_of::<libc::input_event>(), 24);
        assert!(requires_global(&[125, 42, 33]));
        assert!(requires_global(&[126, 33]));
        assert!(!requires_global(&[29, 31]));
    }
    #[test]
    fn strict_kernel_identity_names() {
        assert!(valid_sysname("input42"));
        assert!(!valid_sysname("input42/../event0"));
        assert!(!valid_sysname("input"));
        assert!(valid_event_name("event27"));
        assert!(!valid_event_name("event27/deleted"));
    }
    #[test]
    fn supported_german_codes() {
        let codes = supported_codes();
        for code in [125, 126, 42, 54, 29, 97, 33, 21, 44] {
            assert!(codes.contains(&code));
        }
        assert!(!codes.contains(&0));
        assert!(!codes.contains(&255));
    }
    #[test]
    fn expired_write_has_no_effect() {
        let mut fds = [0; 2];
        assert_eq!(
            unsafe { libc::pipe2(fds.as_mut_ptr(), libc::O_NONBLOCK | libc::O_CLOEXEC) },
            0
        );
        let read = unsafe { OwnedFd::from_raw_fd(fds[0]) };
        let write = unsafe { OwnedFd::from_raw_fd(fds[1]) };
        assert!(write_packet(
            write.as_raw_fd(),
            &[0u8; 48],
            Instant::now(),
            &mut || Ok(())
        )
        .is_err());
        let mut b = [0u8; 48];
        assert_eq!(
            unsafe { libc::read(read.as_raw_fd(), b.as_mut_ptr() as *mut _, 48) },
            -1
        );
    }
    #[test]
    fn packet_write_to_private_pipe_only() {
        let mut fds = [0; 2];
        assert_eq!(
            unsafe { libc::pipe2(fds.as_mut_ptr(), libc::O_NONBLOCK | libc::O_CLOEXEC) },
            0
        );
        let read = unsafe { OwnedFd::from_raw_fd(fds[0]) };
        let write = unsafe { OwnedFd::from_raw_fd(fds[1]) };
        write_packet(
            write.as_raw_fd(),
            &[7u8; 48],
            Instant::now() + Duration::from_millis(50),
            &mut || Ok(()),
        )
        .unwrap();
        let mut b = [0u8; 48];
        assert_eq!(
            unsafe { libc::read(read.as_raw_fd(), b.as_mut_ptr() as *mut _, 48) },
            48
        );
        assert_eq!(b, [7; 48]);
    }
    fn pipe_keyboard() -> (GlobalKeyboard, OwnedFd) {
        let mut fds = [0; 2];
        assert_eq!(
            unsafe { libc::pipe2(fds.as_mut_ptr(), libc::O_NONBLOCK | libc::O_CLOEXEC) },
            0
        );
        let read = unsafe { OwnedFd::from_raw_fd(fds[0]) };
        let write = unsafe { OwnedFd::from_raw_fd(fds[1]) };
        (
            GlobalKeyboard {
                file: Some(fs::File::from(write)),
                name: "offline-pipe".into(),
                sysname: "input0".into(),
                peer: Peer {
                    pid: 0,
                    start: "offline".into(),
                },
                event_rdev: None,
                held: Vec::new(),
                healthy: true,
            },
            read,
        )
    }
    fn read_key_events(fd: i32) -> Vec<(u16, i32)> {
        let mut bytes = [0u8; 512];
        let n = unsafe { libc::read(fd, bytes.as_mut_ptr() as *mut _, bytes.len()) };
        assert!(n > 0);
        bytes[..n as usize]
            .chunks_exact(24)
            .filter(|e| u16::from_ne_bytes(e[16..18].try_into().unwrap()) == EV_KEY)
            .map(|e| {
                (
                    u16::from_ne_bytes(e[18..20].try_into().unwrap()),
                    i32::from_ne_bytes(e[20..24].try_into().unwrap()),
                )
            })
            .collect()
    }
    #[test]
    fn canceled_chord_releases_all_potential_held_modifiers_in_reverse() {
        let (mut keyboard, read) = pipe_keyboard();
        let deadline = Instant::now() + Duration::from_millis(100);
        keyboard.key(125, true, deadline, || Ok(())).unwrap();
        keyboard.key(42, true, deadline, || Ok(())).unwrap();
        assert!(keyboard
            .key(33, true, deadline, || Err("canceled".into()))
            .is_err());
        keyboard.release_all().unwrap();
        assert!(keyboard.held.is_empty());
        assert_eq!(
            read_key_events(read.as_raw_fd()),
            [(125, 1), (42, 1), (42, 0), (125, 0)]
        );
    }
    #[test]
    fn expired_chord_still_releases_prior_modifiers() {
        let (mut keyboard, read) = pipe_keyboard();
        keyboard
            .key(
                125,
                true,
                Instant::now() + Duration::from_millis(100),
                || Ok(()),
            )
            .unwrap();
        assert!(keyboard.key(33, true, Instant::now(), || Ok(())).is_err());
        keyboard.release_all().unwrap();
        assert_eq!(read_key_events(read.as_raw_fd()), [(125, 1), (125, 0)]);
    }
    #[test]
    fn drop_releases_owned_modifier_without_new_key_presses() {
        let (mut keyboard, read) = pipe_keyboard();
        keyboard
            .key(
                125,
                true,
                Instant::now() + Duration::from_millis(100),
                || Ok(()),
            )
            .unwrap();
        drop(keyboard);
        assert_eq!(read_key_events(read.as_raw_fd()), [(125, 1), (125, 0)]);
    }
    #[test]
    fn partial_key_without_syn_then_cancel_has_bounded_release() {
        let (mut keyboard, read) = pipe_keyboard();
        let canceled = std::cell::Cell::new(false);
        let result = keyboard.key_with_writer(
            125,
            true,
            Instant::now() + Duration::from_millis(100),
            || {
                if canceled.get() {
                    Err("injected cancellation".into())
                } else {
                    Ok(())
                }
            },
            |fd, packet, _deadline, check| {
                // Real EV_KEY bytes reach only this private pipe; SYN is withheld.
                assert_eq!(
                    unsafe { libc::write(fd, packet.as_ptr() as *const _, 24) },
                    24
                );
                canceled.set(true);
                check()
            },
        );
        assert!(result.is_err());
        assert_eq!(keyboard.held, [125]);
        let started = Instant::now();
        assert!(
            keyboard.release_all().is_err(),
            "partial transport remains unconfirmed even when release write completes"
        );
        assert!(started.elapsed() < Duration::from_millis(150));
        assert!(keyboard.held.is_empty());
        assert!(keyboard.file.is_none());
        assert_eq!(read_key_events(read.as_raw_fd()), [(125, 1), (125, 0)]);
    }
    #[test]
    fn transport_failure_preserves_uncertain_press_for_cleanup() {
        let (mut keyboard, _read) = pipe_keyboard();
        keyboard.file.take();
        assert!(keyboard
            .key(
                125,
                true,
                Instant::now() + Duration::from_millis(100),
                || Ok(())
            )
            .is_err());
        assert_eq!(keyboard.held, [125]);
        assert!(!keyboard.healthy);
        assert!(keyboard.release_all().is_err());
        assert!(keyboard.held.is_empty());
        assert!(keyboard.file.is_none());
        assert!(keyboard
            .key(
                33,
                true,
                Instant::now() + Duration::from_millis(100),
                || Ok(())
            )
            .is_err());
    }
}
