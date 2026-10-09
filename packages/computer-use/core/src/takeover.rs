//! Owned runtime takeover marker. Backend startup is always fail-closed, even
//! when a previous marker is absent; resume is the only normal clear operation.
use super::*;
const MAX_MARKER: u64 = 16_384;
#[derive(Clone, Deserialize, Serialize)]
pub(super) struct Marker {
    schema: u8,
    pub source: String,
    pub session_id: String,
    at_unix_ms: u128,
}
impl Marker {
    fn new(source: &str, session_id: &str) -> Self {
        Self {
            schema: 1,
            source: source.into(),
            session_id: session_id.into(),
            at_unix_ms: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis(),
        }
    }
}
pub(super) struct Latch {
    path: PathBuf,
    pub reason: Marker,
    pub persistence_error: Option<String>,
    marker_active: bool,
}
fn validate_metadata(metadata: &fs::Metadata, expected_uid: u32) -> R<()> {
    if !metadata.is_file()
        || metadata.file_type().is_symlink()
        || metadata.uid() != expected_uid
        || metadata.mode() & 0o777 != 0o600
    {
        return Err("Takeover marker must be an owned regular nonsymlink file with mode0600; refusing to clear or replace it".into());
    }
    Ok(())
}
fn validate_parent(path: &Path) -> R<()> {
    let parent = path.parent().ok_or("Takeover marker has no parent")?;
    let metadata = fs::symlink_metadata(parent).map_err(|e| e.to_string())?;
    if !metadata.is_dir()
        || metadata.file_type().is_symlink()
        || metadata.uid() != uid()
        || metadata.mode() & 0o777 != 0o700
    {
        return Err("Takeover marker parent must be an owned nonsymlink mode0700 directory".into());
    }
    Ok(())
}
fn load(path: &Path) -> R<Option<Marker>> {
    validate_parent(path)?;
    let path_meta = match fs::symlink_metadata(path) {
        Ok(m) => m,
        Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(e.to_string()),
    };
    validate_metadata(&path_meta, uid())?;
    let file = fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)
        .map_err(|e| e.to_string())?;
    let file_meta = file.metadata().map_err(|e| e.to_string())?;
    validate_metadata(&file_meta, uid())?;
    if (file_meta.dev(), file_meta.ino()) != (path_meta.dev(), path_meta.ino()) {
        return Err("Takeover marker changed while opening; refusal retained".into());
    }
    let mut bytes = Vec::new();
    file.take(MAX_MARKER + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| e.to_string())?;
    if bytes.len() as u64 > MAX_MARKER {
        return Err("Takeover marker exceeds bounded schema".into());
    }
    let marker:Marker=serde_json::from_slice(&bytes).map_err(|e|format!("Invalid takeover marker; backend remains unavailable rather than clearing takeover: {e}"))?;
    if marker.schema != 1
        || !matches!(
            marker.source.as_str(),
            "backend_startup"
                | "physical_escape"
                | "physical_input_activity"
                | "controlled_evdev_simulation"
                | "explicit_desktop_takeover"
        )
    {
        return Err("Unknown takeover marker schema/source; refusing automatic recovery".into());
    }
    Ok(Some(marker))
}
impl Latch {
    pub fn startup(path: PathBuf, session_id: &str) -> R<Self> {
        // An old human/explicit cause is retained across a new session. Missing
        // marker never authorizes input after a crash or controlled restart.
        let prior = load(&path)?;
        let reason = prior.unwrap_or_else(|| Marker::new("backend_startup", session_id));
        let mut latch = Self {
            path,
            reason,
            persistence_error: None,
            marker_active: true,
        };
        latch.store()?;
        Ok(latch)
    }
    fn store(&mut self) -> R<()> {
        let result = (|| {
            validate_parent(&self.path)?;
            let _ = load(&self.path)?;
            let stamp = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos();
            let temporary = self
                .path
                .with_file_name(format!(".takeover-{}-{stamp}.tmp", std::process::id()));
            let result = (|| {
                let mut file = fs::OpenOptions::new()
                    .write(true)
                    .create_new(true)
                    .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
                    .mode(0o600)
                    .open(&temporary)
                    .map_err(|e| e.to_string())?;
                serde_json::to_writer(&mut file, &self.reason).map_err(|e| e.to_string())?;
                file.sync_all().map_err(|e| e.to_string())?;
                let _ = load(&self.path)?;
                fs::rename(&temporary, &self.path).map_err(|e| e.to_string())
            })();
            if result.is_err() {
                let _ = fs::remove_file(&temporary);
            }
            result
        })();
        self.persistence_error = result.as_ref().err().cloned();
        result
    }
    pub fn set(&mut self, source: &str, session_id: &str) -> R<bool> {
        let changed = self.reason.source != source;
        if !changed && self.marker_active && self.persistence_error.is_none() {
            return Ok(false);
        }
        self.reason = Marker::new(source, session_id);
        self.store()?;
        self.marker_active = true;
        Ok(changed)
    }
    pub fn clear(&mut self) -> R<()> {
        validate_parent(&self.path)?;
        if load(&self.path)?.is_none() {
            if !self.marker_active {
                return Ok(());
            }
            return Err(
                "Takeover marker is missing unexpectedly; startup/refusal remains latched".into(),
            );
        }
        fs::remove_file(&self.path).map_err(|e| e.to_string())?;
        self.persistence_error = None;
        self.marker_active = false;
        Ok(())
    }
    pub fn restore(&mut self) -> R<()> {
        self.store()?;
        self.marker_active = true;
        Ok(())
    }
    pub fn status(&self) -> Value {
        // A cleared cause is history, not a current refusal. Keep it available
        // for audit without inviting clients to treat it as an active latch.
        let reason = self.marker_active.then_some(&self.reason);
        let last_reason = (!self.marker_active).then_some(&self.reason);
        json!({"reason":reason,"last_reason":last_reason,"marker_path":self.path,"marker_active":self.marker_active,"persistence_error":self.persistence_error,"backend_restart_requires_explicit_resume":true,"resume_policy":"Startup, physical Escape, explicit takeover and legacy persisted causes require user-authorized resume with actor released and physical input quiet. Ordinary activity never creates a marker. last_reason is historical and never authorizes or requires a transition."})
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn status_separates_active_cause_from_cleared_history_without_erasing_persisted_reason() {
        let dir = env::temp_dir().join(format!(
            "weasel-latch-status-regression-{}",
            std::process::id()
        ));
        private_dir(&dir).unwrap();
        let path = dir.join("takeover.json");
        let mut latch = Latch::startup(path.clone(), "status-session").unwrap();
        latch
            .set("physical_input_activity", "status-session")
            .unwrap();
        let active = latch.status();
        assert_eq!(active["marker_active"], true);
        assert_eq!(active["reason"]["source"], "physical_input_activity");
        assert_eq!(active["last_reason"], Value::Null);
        let persisted: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        assert_eq!(persisted["source"], "physical_input_activity");
        latch.clear().unwrap();
        let inactive = latch.status();
        assert_eq!(inactive["marker_active"], false);
        assert_eq!(inactive["reason"], Value::Null);
        assert_eq!(inactive["last_reason"]["source"], "physical_input_activity");
        assert_eq!(latch.reason.source, "physical_input_activity");
        latch.restore().unwrap();
        assert_eq!(
            latch.status()["reason"]["source"],
            "physical_input_activity"
        );
        assert_eq!(latch.status()["last_reason"], Value::Null);
        assert_eq!(
            serde_json::from_slice::<Value>(&fs::read(&path).unwrap()).unwrap()["source"],
            "physical_input_activity"
        );
        fs::remove_dir_all(dir).unwrap();
    }
    #[test]
    fn marker_restart_and_owned_path_refusal() {
        let dir = env::temp_dir().join(format!("weasel-latch-regression-{}", std::process::id()));
        private_dir(&dir).unwrap();
        let path = dir.join("takeover.json");
        let mut first = Latch::startup(path.clone(), "fixture-session-1").unwrap();
        assert_eq!(first.reason.source, "backend_startup");
        assert_eq!(fs::metadata(&path).unwrap().mode() & 0o777, 0o600);
        first
            .set("physical_input_activity", "fixture-session-1")
            .unwrap();
        drop(first);
        let mut second = Latch::startup(path.clone(), "fixture-session-2").unwrap();
        assert_eq!(second.reason.source, "physical_input_activity");
        assert_eq!(second.reason.session_id, "fixture-session-1");
        second.clear().unwrap();
        assert!(!path.exists());
        second
            .set("physical_input_activity", "fixture-session-2")
            .unwrap();
        assert!(path.exists());
        second.clear().unwrap();
        let third = Latch::startup(path.clone(), "fixture-session-3").unwrap();
        assert_eq!(third.reason.source, "backend_startup");
        assert_eq!(third.reason.session_id, "fixture-session-3");
        drop(third);
        fs::set_permissions(&path, fs::Permissions::from_mode(0o640)).unwrap();
        assert!(Latch::startup(path.clone(), "fixture-session-4").is_err());
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        let metadata = fs::metadata(&path).unwrap();
        assert!(validate_metadata(&metadata, metadata.uid().wrapping_add(1)).is_err());
        let original = dir.join("original.json");
        fs::rename(&path, &original).unwrap();
        std::os::unix::fs::symlink(&original, &path).unwrap();
        assert!(Latch::startup(path.clone(), "fixture-session-4").is_err());
        assert!(original.exists());
        fs::remove_file(&path).unwrap();
        fs::write(&path, b"broken JSON").unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        assert!(Latch::startup(path, "fixture-session-4").is_err());
        fs::remove_dir_all(dir).unwrap();
    }
}
