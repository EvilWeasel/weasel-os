//! Owned runtime takeover marker. Backend startup is always fail-closed, even
//! when a previous marker is absent; resume is the only normal clear operation.
use super::*;
const MAX_MARKER: u64 = 16_384;
static CAUSE_SERIAL: AtomicU64 = AtomicU64::new(1);
fn source_priority(source: &str) -> Option<u8> {
    match source {
        // Explicit takeover is the strongest live cause. A later Escape still
        // cancels/invalidate work, but may not downgrade this return-of-control gate.
        "explicit_desktop_takeover" => Some(5),
        "physical_escape" => Some(4),
        "physical_input_activity" => Some(2),
        "controlled_evdev_simulation" => Some(1),
        "backend_startup" => Some(0),
        _ => None,
    }
}
#[derive(Clone, Deserialize, Serialize)]
pub(super) struct Marker {
    schema: u8,
    pub source: String,
    pub session_id: String,
    #[serde(default)]
    pub cause_id: String,
    at_unix_ms: u128,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub control_stop: Option<control_scope::StopEvent>,
}
impl Marker {
    fn new(source: &str, session_id: &str) -> Self {
        Self {
            schema: 1,
            source: source.into(),
            session_id: session_id.into(),
            cause_id: format!(
                "{}-{}-{}",
                session_id,
                SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_nanos(),
                CAUSE_SERIAL.fetch_add(1, Ordering::SeqCst)
            ),
            control_stop: None,
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
    if let Some(event) = &marker.control_stop { event.validate()?; }
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
        let incoming =
            source_priority(source).ok_or("Unknown takeover source; existing refusal retained")?;
        let current = source_priority(&self.reason.source)
            .ok_or("Unknown active takeover source; existing refusal retained")?;
        // Test/startup/legacy paths must not reinterpret a real active stop.
        // Cleared historical causes have no priority over a genuinely new stop.
        if self.marker_active && incoming < current {
            if self.persistence_error.is_some() {
                self.store()?;
            }
            return Ok(false);
        }
        // A new real Escape (including the same source) is a new stop, not an
        // idempotent setter: retain its current event identity/session/time.
        let pending = self.reason.control_stop.clone();
        self.reason = Marker::new(source, session_id);
        self.reason.control_stop = pending;
        self.marker_active = true; // current refusal remains visible on I/O error
        self.store()?;
        Ok(true)
    }
    pub fn retain_control_stop(&mut self, event: control_scope::StopEvent) -> R<()> {
        event.validate()?;
        if !self.marker_active { return Err("Cannot persist a control stop under a cleared latch".into()); }
        if let Some(prior) = &self.reason.control_stop {
            if !prior.acknowledged && prior.event_id != event.event_id
                || prior.event_id == event.event_id && !event.is_monotonic_update_of(prior) {
                return Err("Cannot replace pending control owner/event or regress delivery ACK".into());
            }
        }
        let prior = self.reason.control_stop.clone();
        self.reason.control_stop = Some(event);
        if let Err(error) = self.store() {
            // Only optimistic delivery/ACK metadata rolls back. The active
            // stop and persistence error remain latched and visible.
            self.reason.control_stop = prior;
            return Err(error);
        }
        Ok(())
    }
    pub fn clear(&mut self) -> R<()> {
        if self.reason.control_stop.as_ref().is_some_and(|event| !event.acknowledged) {
            return Err("Retained control stop must be delivered and acknowledged; ACK alone never authorizes resume".into());
        }
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
        // A rollback I/O failure is still a current refusal, never history.
        self.marker_active = true;
        self.store()
    }
    pub fn status(&self) -> Value {
        // A cleared cause is history, not a current refusal. Keep it available
        // for audit without inviting clients to treat it as an active latch.
        let reason = self.marker_active.then_some(&self.reason);
        let last_reason = (!self.marker_active).then_some(&self.reason);
        json!({"reason":reason,"last_reason":last_reason,"marker_path":self.path,"marker_active":self.marker_active,"persistence_error":self.persistence_error,"backend_restart_requires_explicit_resume":true,"cause_preservation":"Active explicit desktop takeover dominates physical Escape, legacy, simulation and startup; active physical Escape dominates legacy, simulation and startup. Each accepted new stop has a new cause identity. Cleared history never prevents a new stop.","resume_policy":"Startup, physical Escape, explicit takeover and legacy persisted causes require user-authorized resume with actor released and physical input quiet. Ordinary activity never creates a marker. last_reason is historical and never authorizes or requires a transition."})
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn control_event() -> control_scope::StopEvent {
        serde_json::from_value(json!({"contract_revision":1,"event_id":"control-stop-1","session_id":"actor-1","scope_id":"scope-1",
            "source":"physical_escape","stop_generation":3,
            "responsible":{"thread_id":"actual-thread","run_id":"actual-run","author_turn_id":"actual-turn",
                "conversation_id":null,"parent_turn_id":null,"job_id":null},
            "target":{"adapter":"http","authority":"actual-app-session","resource":"actual-document","revision":"observed"},
            "operation":null,"delivered":false,"acknowledged":false})).unwrap()
    }
    #[test]
    fn control_stop_owner_survives_restart_and_delivery_ack_never_clears_latch() {
        let dir = env::temp_dir().join(format!("weasel-control-stop-persist-{}", std::process::id()));
        private_dir(&dir).unwrap(); let path = dir.join("takeover.json");
        let mut latch = Latch::startup(path.clone(), "actor-1").unwrap();
        latch.set("physical_escape", "actor-1").unwrap();
        let event = control_event(); latch.retain_control_stop(event.clone()).unwrap();
        let mut restarted = Latch::startup(path.clone(), "actor-2").unwrap();
        assert_eq!(restarted.reason.control_stop, Some(event.clone()));
        assert!(restarted.clear().is_err());
        restarted.set("physical_escape", "actor-2").unwrap();
        assert_eq!(restarted.reason.control_stop, Some(event.clone()));
        let mut delivered = event; delivered.delivered = true;
        restarted.retain_control_stop(delivered.clone()).unwrap();
        assert!(restarted.clear().is_err());
        delivered.acknowledged = true;
        restarted.retain_control_stop(delivered).unwrap();
        assert!(restarted.status()["marker_active"] == true);
        assert!(path.exists(), "notification ACK does not clear the stop marker");
        fs::remove_dir_all(dir).unwrap();
    }
    #[test]
    fn failed_delivery_and_ack_store_preserve_prior_metadata_and_block_clear() {
        let dir = env::temp_dir().join(format!("weasel-control-stop-commit-{}", std::process::id()));
        private_dir(&dir).unwrap();
        let path = dir.join("takeover.json");
        let mut latch = Latch::startup(path.clone(), "actor-1").unwrap();
        let original = control_event();
        latch.retain_control_stop(original.clone()).unwrap();
        let disk_before = fs::read(&path).unwrap();
        let mut delivered = original.clone();
        delivered.delivered = true;
        latch.path = dir.join("missing-parent").join("takeover.json");
        assert!(latch.retain_control_stop(delivered.clone()).is_err());
        assert_eq!(latch.reason.control_stop.as_ref(), Some(&original));
        assert!(latch.marker_active);
        assert!(latch.persistence_error.is_some());
        assert_eq!(fs::read(&path).unwrap(), disk_before);
        assert!(latch.clear().is_err());
        latch.path = path.clone();
        latch.retain_control_stop(delivered.clone()).unwrap();
        let disk_delivered = fs::read(&path).unwrap();
        let mut acknowledged = delivered.clone();
        acknowledged.acknowledged = true;
        latch.path = dir.join("missing-parent").join("takeover.json");
        assert!(latch.retain_control_stop(acknowledged.clone()).is_err());
        assert_eq!(latch.reason.control_stop.as_ref(), Some(&delivered));
        assert!(!latch.reason.control_stop.as_ref().unwrap().acknowledged);
        assert!(latch.clear().is_err());
        assert_eq!(fs::read(&path).unwrap(), disk_delivered);
        latch.path = path.clone();
        latch.retain_control_stop(acknowledged.clone()).unwrap();
        assert_eq!(latch.reason.control_stop.as_ref(), Some(&acknowledged));
        assert!(latch.marker_active, "durable ACK never clears latch");
        let restarted = Latch::startup(path, "actor-2").unwrap();
        assert_eq!(restarted.reason.control_stop.as_ref(), Some(&acknowledged));
        fs::remove_dir_all(dir).unwrap();
    }
    #[test]
    fn pending_control_event_cannot_be_replaced_or_delivery_regressed() {
        let dir = env::temp_dir().join(format!("weasel-control-stop-regression-{}", std::process::id()));
        private_dir(&dir).unwrap(); let path = dir.join("takeover.json");
        let mut latch = Latch::startup(path, "actor-1").unwrap();
        let mut event = control_event(); event.delivered = true;
        latch.retain_control_stop(event.clone()).unwrap();
        let mut replacement = event.clone(); replacement.event_id = "different-event".into();
        assert!(latch.retain_control_stop(replacement).is_err());
        let mut wrong_owner = event.clone(); wrong_owner.responsible.run_id = "different-run".into();
        assert!(latch.retain_control_stop(wrong_owner).is_err());
        let mut altered_cause = event.clone(); altered_cause.source = "controlled_evdev_simulation".into();
        assert!(latch.retain_control_stop(altered_cause).is_err());
        event.delivered = false;
        assert!(latch.retain_control_stop(event).is_err());
        fs::remove_dir_all(dir).unwrap();
    }
    #[test]
    fn malformed_persisted_control_owner_refuses_startup_without_overwriting_marker() {
        let dir = env::temp_dir().join(format!("weasel-control-stop-invalid-{}", std::process::id()));
        private_dir(&dir).unwrap(); let path = dir.join("takeover.json");
        let mut latch = Latch::startup(path.clone(), "actor-1").unwrap();
        latch.retain_control_stop(control_event()).unwrap();
        let mut payload: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        payload["control_stop"]["responsible"]["author_turn_id"] = json!("");
        let bytes = serde_json::to_vec(&payload).unwrap(); fs::write(&path, &bytes).unwrap();
        assert!(Latch::startup(path.clone(), "actor-2").is_err());
        assert_eq!(fs::read(&path).unwrap(), bytes);
        fs::remove_dir_all(dir).unwrap();
    }

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
    fn r8_active_physical_escape_survives_lower_sources_and_new_escape_refreshes_identity() {
        let dir = env::temp_dir().join(format!("weasel-r8-physical-{}", std::process::id()));
        private_dir(&dir).unwrap();
        let path = dir.join("takeover.json");
        let mut latch = Latch::startup(path.clone(), "first-session").unwrap();
        latch.set("physical_escape", "first-session").unwrap();
        let original = fs::read(&path).unwrap();
        for lower in [
            "controlled_evdev_simulation",
            "backend_startup",
            "physical_input_activity",
        ] {
            assert!(
                !latch.set(lower, "test-session").unwrap(),
                "{lower} must not replace physical Escape"
            );
            assert_eq!(fs::read(&path).unwrap(), original, "{lower}");
            assert_eq!(latch.status()["reason"]["source"], "physical_escape");
        }
        assert!(latch.set("physical_escape", "current-session").unwrap());
        assert_eq!(latch.reason.session_id, "current-session");
        let prior_cause = latch.reason.cause_id.clone();
        assert!(latch.set("physical_escape", "current-session").unwrap());
        assert_ne!(latch.reason.cause_id,prior_cause,"each real Escape must retain fresh event identity even in the same millisecond/session");
        assert_ne!(fs::read(&path).unwrap(), original);
        assert_eq!(
            Latch::startup(path, "later-backend")
                .unwrap()
                .reason
                .session_id,
            "current-session"
        );
        fs::remove_dir_all(dir).unwrap();
    }
    #[test]
    fn r9_explicit_and_escape_preserve_the_stronger_explicit_cause_in_both_orders() {
        let dir = env::temp_dir().join(format!("weasel-r9-precedence-{}", std::process::id()));
        private_dir(&dir).unwrap();
        let path = dir.join("takeover.json");
        let mut latch = Latch::startup(path.clone(), "precedence-session").unwrap();
        latch.set("explicit_desktop_takeover", "precedence-session").unwrap();
        let explicit = fs::read(&path).unwrap();
        assert!(!latch.set("physical_escape", "precedence-session").unwrap());
        assert_eq!(latch.reason.source, "explicit_desktop_takeover");
        assert_eq!(fs::read(&path).unwrap(), explicit);

        latch.clear().unwrap();
        latch.set("physical_escape", "precedence-session").unwrap();
        latch.set("explicit_desktop_takeover", "precedence-session").unwrap();
        assert_eq!(latch.reason.source, "explicit_desktop_takeover");
        let explicit = fs::read(&path).unwrap();
        assert!(!latch.set("physical_escape", "precedence-session").unwrap());
        assert_eq!(latch.reason.source, "explicit_desktop_takeover");
        assert_eq!(fs::read(&path).unwrap(), explicit);
        fs::remove_dir_all(dir).unwrap();
    }
    #[test]
    fn r8_explicit_stop_survives_simulation_startup_legacy_but_clear_allows_a_new_cause() {
        let dir = env::temp_dir().join(format!("weasel-r8-explicit-{}", std::process::id()));
        private_dir(&dir).unwrap();
        let path = dir.join("takeover.json");
        let mut latch = Latch::startup(path.clone(), "explicit-session").unwrap();
        latch
            .set("explicit_desktop_takeover", "explicit-session")
            .unwrap();
        let original = fs::read(&path).unwrap();
        for lower in [
            "controlled_evdev_simulation",
            "backend_startup",
            "physical_input_activity",
        ] {
            assert!(!latch.set(lower, "test-session").unwrap());
            assert_eq!(fs::read(&path).unwrap(), original);
        }
        latch.clear().unwrap();
        latch
            .set("controlled_evdev_simulation", "owned-test")
            .unwrap();
        assert_eq!(
            latch.status()["reason"]["source"],
            "controlled_evdev_simulation"
        );
        latch.set("physical_escape", "new-human-stop").unwrap();
        assert_eq!(latch.reason.source, "physical_escape");
        assert_eq!(latch.reason.session_id, "new-human-stop");
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn r8_failed_persistence_keeps_current_stop_visible_and_unknown_source_does_not_replace_it() {
        let dir = env::temp_dir().join(format!("weasel-r8-store-failure-{}", std::process::id()));
        private_dir(&dir).unwrap();
        let mut latch = Latch::startup(dir.join("takeover.json"), "store-session").unwrap();
        let original = fs::read(dir.join("takeover.json")).unwrap();
        assert!(latch.set("unknown-test-source", "store-session").is_err());
        assert_eq!(fs::read(dir.join("takeover.json")).unwrap(), original);
        latch.clear().unwrap();
        fs::set_permissions(&dir, fs::Permissions::from_mode(0o750)).unwrap();
        assert!(latch.set("physical_escape", "store-session").is_err());
        assert_eq!(latch.status()["marker_active"], true);
        assert_eq!(latch.status()["reason"]["source"], "physical_escape");
        assert!(latch.persistence_error.is_some());
        fs::set_permissions(&dir, fs::Permissions::from_mode(0o700)).unwrap();
        assert!(!latch
            .set("controlled_evdev_simulation", "test-session")
            .unwrap());
        assert!(latch.persistence_error.is_none());
        assert_eq!(
            Latch::startup(dir.join("takeover.json"), "restart-session")
                .unwrap()
                .reason
                .source,
            "physical_escape"
        );
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn r8_failed_rollback_retains_active_human_cause_against_a_later_low_source() {
        let dir =
            env::temp_dir().join(format!("weasel-r8-rollback-failure-{}", std::process::id()));
        private_dir(&dir).unwrap();
        let path = dir.join("takeover.json");
        let mut latch = Latch::startup(path.clone(), "rollback-session").unwrap();
        latch.set("physical_escape", "rollback-session").unwrap();
        let cause = latch.reason.cause_id.clone();
        latch.clear().unwrap();
        fs::set_permissions(&dir, fs::Permissions::from_mode(0o750)).unwrap();
        assert!(latch.restore().is_err());
        assert_eq!(latch.status()["marker_active"], true);
        assert_eq!(latch.status()["reason"]["source"], "physical_escape");
        assert_eq!(latch.status()["last_reason"], Value::Null);
        assert_eq!(latch.reason.cause_id, cause);
        fs::set_permissions(&dir, fs::Permissions::from_mode(0o700)).unwrap();
        assert!(!latch
            .set("controlled_evdev_simulation", "test-session")
            .unwrap());
        assert_eq!(latch.reason.cause_id, cause);
        assert_eq!(latch.reason.source, "physical_escape");
        assert_eq!(
            Latch::startup(path, "new-backend").unwrap().reason.cause_id,
            cause
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
