//! Shared actor admission, exact-target send and retained-stop state.
//! No model JSON owner constructor; production host transport is separately bound.
use super::*;
pub(super) const REVISION: u32 = 2;
fn identifier(value: &str) -> bool {
    !value.is_empty() && value.len() <= 512 && !value.chars().any(char::is_control)
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Responsible {
    pub thread_id: String,
    pub run_id: String,
    pub author_turn_id: String,
    pub conversation_id: Option<String>,
    pub parent_turn_id: Option<String>,
    pub job_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub native_execution: Option<NativeExecution>,
}
impl Responsible {
    pub fn validate(&self) -> R<()> {
        if let Some(native) = &self.native_execution {
            native.validate()?;
        }
        if serde_json::to_vec(self)
            .map_err(|_| "Invalid owner encoding")?
            .len()
            > 4096
        {
            return Err("Responsible identity exceeds durable receipt budget".into());
        }
        if [&self.thread_id, &self.run_id, &self.author_turn_id]
            .into_iter()
            .all(|s| identifier(s))
            && [&self.conversation_id, &self.parent_turn_id, &self.job_id]
                .into_iter()
                .all(|s| s.as_ref().map_or(true, |v| identifier(v)))
        {
            Ok(())
        } else {
            Err("Missing or invalid trusted responsible identity".into())
        }
    }
}
// Canonical T3 fields, separate from Jarvis-local author/job identity. A copied
// JSON tuple is not authority; TrustedOwner still has no wire constructor.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct NativeExecution {
    pub environment_id: String,
    pub attempt_id: String,
    pub root_node_id: String,
    pub provider_instance_id: String,
    pub provider_session_id: String,
    pub provider_thread_id: String,
    pub native_turn_id: String,
    pub runtime_incarnation: String,
    pub native_call_id: String,
}
impl NativeExecution {
    fn validate(&self) -> R<()> {
        if [
            &self.environment_id,
            &self.attempt_id,
            &self.root_node_id,
            &self.provider_instance_id,
            &self.provider_session_id,
            &self.provider_thread_id,
            &self.native_turn_id,
            &self.runtime_incarnation,
            &self.native_call_id,
        ]
        .into_iter()
        .all(|value| identifier(value))
        {
            Ok(())
        } else {
            Err("Incomplete native host invocation binding".into())
        }
    }
}
// Deliberately not Deserialize, nor constructible through actor JSON args.
// A production constructor requires the future authenticated T3 host binder.
#[derive(Clone)]
pub(super) struct TrustedOwner(Responsible);
pub(super) struct ExplicitContinuation {
    decision_id: String,
    session_id: String,
    stopped_generation: u64,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Target {
    pub adapter: String,
    pub authority: String,
    pub resource: String,
    pub revision: String,
}
impl Target {
    fn validate(&self) -> R<()> {
        if [
            &self.adapter,
            &self.authority,
            &self.resource,
            &self.revision,
        ]
        .into_iter()
        .all(|s| identifier(s))
        {
            Ok(())
        } else {
            Err("Exact adapter target binding is required".into())
        }
    }
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) struct Binding {
    session_id: String,
    scope_id: String,
    token: String,
    stop_generation: u64,
    target_generation: u64,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum Disposition {
    NotDispatched,
    PossiblyDispatched,
    Completed,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct OperationReceipt {
    action_id: String,
    target: Target,
    disposition: Disposition,
    cancel_supported: bool,
    cancel_attempted: bool,
    cancel_outcome: Option<String>,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct StopEvent {
    pub contract_revision: u32,
    pub event_id: String,
    pub session_id: String,
    pub scope_id: String,
    pub source: String,
    pub stop_generation: u64,
    pub responsible: Responsible,
    pub target: Target,
    pub operation: Option<OperationReceipt>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub original_command: Option<BrowserClickCommand>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub latest_operation: Option<OperationReceipt>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub delivery: Option<OriginalStopDelivery>,
    pub delivered: bool,
    pub acknowledged: bool,
}
impl StopEvent {
    pub fn is_monotonic_update_of(&self, prior: &Self) -> bool {
        let operation_monotonic = match (&prior.operation, &self.operation) {
            (None, None) => true,
            (Some(old), Some(new)) => {
                old.action_id == new.action_id
                    && old.target == new.target
                    && old.cancel_supported == new.cancel_supported
                    && (!old.cancel_attempted || new.cancel_attempted)
                    && match (&old.disposition, &new.disposition) {
                        (Disposition::NotDispatched, Disposition::NotDispatched)
                        | (Disposition::PossiblyDispatched, Disposition::PossiblyDispatched)
                        | (Disposition::PossiblyDispatched, Disposition::Completed)
                        | (Disposition::Completed, Disposition::Completed) => true,
                        _ => false,
                    }
            }
            _ => false,
        };
        self.contract_revision == prior.contract_revision
            && self.event_id == prior.event_id
            && self.session_id == prior.session_id
            && self.scope_id == prior.scope_id
            && self.source == prior.source
            && self.stop_generation == prior.stop_generation
            && self.responsible == prior.responsible
            && self.target == prior.target
            && (!prior.delivered || self.delivered)
            && (!prior.acknowledged || self.acknowledged)
            && operation_monotonic
            && self.original_command == prior.original_command
            && (self.contract_revision < 2 || self.operation == prior.operation)
            && (prior.delivery.is_none() || self.delivery == prior.delivery)
            && match (&prior.latest_operation, &self.latest_operation) {
                (None, _) => true,
                (Some(old), Some(new)) => {
                    old.action_id == new.action_id
                        && old.target == new.target
                        && old.cancel_supported == new.cancel_supported
                        && (!old.cancel_attempted || new.cancel_attempted)
                        && !(old.disposition == Disposition::Completed
                            && new.disposition != Disposition::Completed)
                }
                (Some(_), None) => false,
            }
    }
    pub fn validate(&self) -> R<()> {
        self.responsible.validate()?;
        self.target.validate()?;
        if !(1..=REVISION).contains(&self.contract_revision)
            || !identifier(&self.event_id)
            || !identifier(&self.session_id)
            || !identifier(&self.scope_id)
            || self.stop_generation == 0
            || !matches!(
                self.source.as_str(),
                "physical_escape" | "explicit_desktop_takeover" | "controlled_evdev_simulation"
            )
            || self.acknowledged && !self.delivered
        {
            return Err("Invalid retained control stop event".into());
        }
        if serde_json::to_vec(self)
            .map_err(|_| "Invalid stop encoding")?
            .len()
            > 12_288
        {
            return Err("Retained stop exceeds bounded durable marker budget".into());
        }
        if let Some(command) = &self.original_command {
            command.validate()?;
            if command.actor_target() != self.target
                || self.operation.as_ref().map(|op| &op.action_id) != Some(&command.action_id)
            {
                return Err("Original stop command/operation mismatch".into());
            }
        }
        if let Some(delivery) = &self.delivery {
            delivery.validate()?;
            if !self.delivered {
                return Err("Durable delivery metadata without delivered state".into());
            }
        }
        if let Some(latest) = &self.latest_operation {
            let original = self
                .operation
                .as_ref()
                .ok_or("Later outcome has no original operation")?;
            if latest.action_id != original.action_id
                || latest.target != original.target
                || latest.cancel_supported != original.cancel_supported
                || original.disposition == Disposition::NotDispatched
                    && latest.disposition != Disposition::NotDispatched
                || original.disposition == Disposition::Completed
                    && latest.disposition != Disposition::Completed
            {
                return Err("Later receipt differs from original stopped operation".into());
            }
        }
        if self.original_command.is_some()
            && (self.delivered || self.acknowledged)
            && self.delivery.is_none()
        {
            return Err("Browser stop delivery lacks durable original-outcome binding".into());
        }
        if let Some(operation) = &self.operation {
            operation.target.validate()?;
            if !identifier(&operation.action_id)
                || operation.target != self.target
                || operation.cancel_attempted && !operation.cancel_supported
                || operation.cancel_outcome.is_some() && !operation.cancel_attempted
            {
                return Err("Invalid retained operation disposition".into());
            }
        }
        Ok(())
    }
}
pub(super) struct PriorityStop {
    state: AtomicU64,
    target_generation: AtomicU64,
    active: AtomicBool,
}
impl PriorityStop {
    fn new() -> Self {
        Self {
            state: AtomicU64::new(3),
            target_generation: AtomicU64::new(0),
            active: AtomicBool::new(false),
        }
    }
    fn snapshot(&self) -> (u64, bool) {
        let value = self.state.load(Ordering::SeqCst);
        (value >> 1, value & 1 != 0)
    }
    pub fn fence(&self) -> R<u64> {
        match self
            .state
            .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |old| {
                old.checked_add(2).map(|next| next | 1)
            }) {
            Ok(old) => Ok((old >> 1) + 1),
            Err(_) => {
                self.state.fetch_or(1, Ordering::SeqCst);
                Err("Stop generation exhausted".into())
            }
        }
    }
    fn arm(&self, expected_generation: u64) -> R<u64> {
        let old = self.state.load(Ordering::SeqCst);
        if old >> 1 != expected_generation {
            return Err("Stop changed before explicit continuation".into());
        }
        let next = (old & !1)
            .checked_add(2)
            .ok_or("Stop generation exhausted")?;
        self.state
            .compare_exchange(old, next, Ordering::SeqCst, Ordering::SeqCst)
            .map(|_| next >> 1)
            .map_err(|_| "Physical stop raced explicit continuation".into())
    }
}
struct Scope {
    binding: Binding,
    responsible: Responsible,
    target: Target,
    ready: Option<Value>,
}
pub(super) struct Fence {
    session_id: String,
    stop_generation: u64,
    target_generation: u64,
    priority: Arc<PriorityStop>,
    stopped: bool,
    scope: Option<Scope>,
    operation: Option<OperationReceipt>,
    used_scopes: HashSet<String>,
    used_actions: HashSet<String>,
    pub pending_stop: Option<StopEvent>,
    original_command: Option<BrowserClickCommand>,
    browser_receipts: HashMap<String, (Binding, BrowserDispatchReceipt)>,
}
impl Fence {
    pub fn new(session_id: String) -> Self {
        Self {
            session_id,
            stop_generation: 1,
            target_generation: 0,
            priority: Arc::new(PriorityStop::new()),
            stopped: true,
            scope: None,
            operation: None,
            used_scopes: HashSet::new(),
            used_actions: HashSet::new(),
            pending_stop: None,
            original_command: None,
            browser_receipts: HashMap::new(),
        }
    }
    pub fn restore_stop(&mut self, event: StopEvent) -> R<()> {
        event.validate()?;
        // Never revive a scope or carry its private token across restart.
        self.stop_generation = self.stop_generation.max(event.stop_generation);
        self.priority.state.store(
            self.stop_generation
                .checked_mul(2)
                .ok_or("Stop generation exhausted")?
                | 1,
            Ordering::SeqCst,
        );
        self.used_scopes.insert(event.scope_id.clone());
        if let Some(operation) = &event.operation {
            self.used_actions.insert(operation.action_id.clone());
        }
        self.pending_stop = Some(event);
        self.stopped = true;
        Ok(())
    }
    pub fn begin(
        &mut self,
        owner: &TrustedOwner,
        permission: &ExplicitContinuation,
        scope_id: &str,
        token: &str,
        target: Target,
    ) -> R<Binding> {
        owner.0.validate()?;
        target.validate()?;
        if !identifier(scope_id)
            || !identifier(token)
            || !identifier(&permission.decision_id)
            || permission.session_id != self.session_id
            || permission.stopped_generation != self.stop_generation
            || self.scope.is_some()
            || self.operation.is_some()
            || self
                .pending_stop
                .as_ref()
                .is_some_and(|event| !event.acknowledged)
            || self.used_scopes.contains(scope_id)
        {
            return Err(
                "Fresh explicit decision, released prior operation and unused scope required"
                    .into(),
            );
        }
        self.used_scopes.insert(scope_id.into());
        self.stop_generation = self.priority.arm(self.stop_generation)?;
        let binding = Binding {
            session_id: self.session_id.clone(),
            scope_id: scope_id.into(),
            token: token.into(),
            stop_generation: self.stop_generation,
            target_generation: self.target_generation,
        };
        self.scope = Some(Scope {
            binding: binding.clone(),
            responsible: owner.0.clone(),
            target,
            ready: None,
        });
        self.priority.active.store(true, Ordering::SeqCst);
        self.stopped = false;
        Ok(binding)
    }
    fn check(&self, binding: &Binding) -> R<()> {
        let (generation, stopped) = self.priority.snapshot();
        if stopped
            || generation != binding.stop_generation
            || self.stopped
            || binding.session_id != self.session_id
            || binding.stop_generation != self.stop_generation
            || !self.scope.as_ref().is_some_and(|scope| {
                scope.binding.scope_id == binding.scope_id && scope.binding.token == binding.token
            })
        {
            return Err("Control scope stopped, stale or not owned".into());
        }
        Ok(())
    }
    fn display_inventory(outputs: &Value) -> R<Value> {
        let inventory = outputs.as_object().ok_or("Output inventory unavailable")?;
        let mut enabled = serde_json::Map::new();
        for (name, entry) in inventory {
            if entry.get("logical") == Some(&Value::Null) {
                continue;
            }
            launch::allowed_output(name, outputs)?;
            enabled.insert(name.clone(), entry["logical"].clone());
        }
        if enabled.is_empty() {
            return Err("No enabled output for aggregate READY".into());
        }
        Ok(Value::Object(enabled))
    }
    // Trusted presentation binder only; model assertions are not renderer evidence.
    pub fn indicator_ready(&mut self, binding: &Binding, mapped: &Value, current: &Value) -> R<()> {
        self.check(binding)?;
        let actual = Self::display_inventory(current)?;
        if *mapped != actual {
            return Err(
                "All-display renderer READY coverage differs from current inventory".into(),
            );
        }
        self.scope.as_mut().ok_or("Scope unavailable")?.ready = Some(actual);
        Ok(())
    }
    pub fn target_changed(&mut self, generation: u64) {
        self.priority
            .target_generation
            .fetch_max(generation, Ordering::SeqCst);
        self.target_generation = self.priority.target_generation.load(Ordering::SeqCst);
    }
    pub fn reground(&self, binding: &Binding, exact: &Target) -> R<Binding> {
        self.check(binding)?;
        if &self.scope.as_ref().ok_or("Scope unavailable")?.target != exact {
            return Err("Wrong control target".into());
        }
        let mut fresh = binding.clone();
        fresh.target_generation = self.priority.target_generation.load(Ordering::SeqCst);
        Ok(fresh)
    }
    pub fn admit(
        &mut self,
        binding: &Binding,
        target: &Target,
        action_id: &str,
        outputs: &Value,
        cancel_supported: bool,
    ) -> R<()> {
        self.check(binding)?;
        let scope = self.scope.as_ref().ok_or("Scope unavailable")?;
        if binding.target_generation != self.priority.target_generation.load(Ordering::SeqCst) {
            return Err("Target stale; reobserve without stopping scope".into());
        }
        if target != &scope.target
            || scope.ready.as_ref() != Some(&Self::display_inventory(outputs)?)
        {
            return Err("Exact target or aggregate display readiness changed".into());
        }
        if self.operation.is_some()
            || !identifier(action_id)
            || !self.used_actions.insert(action_id.into())
        {
            return Err("Only one admitted operation and no action replay are permitted".into());
        }
        self.operation = Some(OperationReceipt {
            action_id: action_id.into(),
            target: target.clone(),
            disposition: Disposition::NotDispatched,
            cancel_supported,
            cancel_attempted: false,
            cancel_outcome: None,
        });
        Ok(())
    }
    // State transition at an actual trusted adapter send boundary. This is
    // NOT an external precheck token and cannot authorize an unfenced send.
    pub fn crossing_send_boundary(
        &mut self,
        binding: &Binding,
        action_id: &str,
        target: &Target,
        outputs: &Value,
    ) -> R<()> {
        self.check(binding)?;
        let scope = self.scope.as_ref().ok_or("Scope unavailable")?;
        if target != &scope.target
            || scope.ready.as_ref() != Some(&Self::display_inventory(outputs)?)
        {
            return Err("Target or all-display readiness changed at send boundary".into());
        }
        if binding.target_generation != self.priority.target_generation.load(Ordering::SeqCst) {
            return Err("Target stale before dispatch".into());
        }
        let operation = self.operation.as_mut().ok_or("No admitted operation")?;
        if operation.action_id != action_id || operation.disposition != Disposition::NotDispatched {
            return Err("Operation already sent, foreign or uncertain; no retry".into());
        }
        operation.disposition = Disposition::PossiblyDispatched;
        Ok(())
    }
    pub fn complete(&mut self, binding: &Binding, action_id: &str) -> R<()> {
        self.check_cleanup_owner(binding)?;
        let operation = self.operation.as_mut().ok_or("No admitted operation")?;
        if operation.action_id != action_id
            || operation.disposition != Disposition::PossiblyDispatched
        {
            return Err("No matching in-flight operation".into());
        }
        operation.disposition = Disposition::Completed;
        if let Some(event) = self.pending_stop.as_mut() {
            if event.scope_id == binding.scope_id
                && event.operation.as_ref().map(|original| &original.action_id)
                    == Some(&operation.action_id)
            {
                event.latest_operation = Some(operation.clone());
            }
        }
        Ok(())
    }
    pub fn stop(&mut self, source: &str) -> R<Option<StopEvent>> {
        if !matches!(
            source,
            "physical_escape" | "explicit_desktop_takeover" | "controlled_evdev_simulation"
        ) {
            return Err("Unsupported stop provenance".into());
        }
        self.stopped = true;
        self.priority.active.store(false, Ordering::SeqCst);
        let (priority_generation, _) = self.priority.snapshot();
        self.stop_generation = if priority_generation > self.stop_generation {
            priority_generation
        } else {
            self.priority.fence()?
        };
        if self
            .pending_stop
            .as_ref()
            .is_some_and(|event| !event.acknowledged)
        {
            return Ok(self.pending_stop.clone()); // stable event identity until acknowledged
        }
        if let Some(scope) = &self.scope {
            self.pending_stop = Some(StopEvent {
                contract_revision: REVISION,
                event_id: format!("{}:control-stop:{}", self.session_id, self.stop_generation),
                session_id: self.session_id.clone(),
                scope_id: scope.binding.scope_id.clone(),
                source: source.into(),
                stop_generation: self.stop_generation,
                responsible: scope.responsible.clone(),
                target: scope.target.clone(),
                operation: self.operation.clone(),
                original_command: self.original_command.clone(),
                latest_operation: None,
                delivery: None,
                delivered: false,
                acknowledged: false,
            });
        }
        Ok(self.pending_stop.clone())
    }
    pub fn delivered(&mut self, event_id: &str, owner: &TrustedOwner) -> R<()> {
        let event = self.pending_stop.as_mut().ok_or("No retained stop event")?;
        if event.event_id != event_id || event.responsible != owner.0 {
            return Err("Wrong stop delivery owner/event".into());
        }
        if event.original_command.is_some() {
            return Err("Browser stop requires retained durable-delivery binding".into());
        }
        event.delivered = true;
        Ok(())
    }
    pub fn acknowledge(&mut self, event_id: &str, owner: &TrustedOwner) -> R<()> {
        let event = self.pending_stop.as_mut().ok_or("No retained stop event")?;
        if event.event_id != event_id || event.responsible != owner.0 || !event.delivered {
            return Err("Stop must be delivered to the exact responsible turn before ACK".into());
        }
        if event.original_command.is_some() {
            return Err("Browser stop requires cleanup-only original-outcome ACK binding".into());
        }
        event.acknowledged = true;
        Ok(()) // never changes stop/scope/operation
    }
    fn check_cleanup_owner(&self, binding: &Binding) -> R<()> {
        let owned = &self.scope.as_ref().ok_or("No owned scope")?.binding;
        if owned.session_id != binding.session_id
            || owned.scope_id != binding.scope_id
            || owned.token != binding.token
            || owned.stop_generation != binding.stop_generation
        {
            return Err("Foreign scope cleanup".into());
        }
        Ok(())
    }
    pub fn cancel_result(&mut self, binding: &Binding, action_id: &str, outcome: &str) -> R<()> {
        self.check_cleanup_owner(binding)?;
        let operation = self.operation.as_mut().ok_or("No admitted operation")?;
        if operation.action_id != action_id
            || !operation.cancel_supported
            || operation.disposition != Disposition::PossiblyDispatched
            || !identifier(outcome)
        {
            return Err("No matching cancellable in-flight operation".into());
        }
        operation.cancel_attempted = true;
        operation.cancel_outcome = Some(outcome.into());
        if let Some(event) = self.pending_stop.as_mut() {
            if event.scope_id == binding.scope_id
                && event.operation.as_ref().map(|original| &original.action_id)
                    == Some(&operation.action_id)
            {
                event.latest_operation = Some(operation.clone());
            }
        }
        Ok(()) // cancellation acknowledgement does not assert completion/rollback
    }
    pub fn cancel_scope(&mut self) {
        self.stopped = true;
        self.stop_generation = self.priority.snapshot().0;
        self.priority.active.store(false, Ordering::SeqCst);
        // Explicit caller cancellation is not relabeled as physical Escape.
        // Already-sent operation and any genuine retained stop stay intact.
    }
    pub fn active(&self) -> bool {
        self.scope.is_some() && !self.stopped && !self.priority.snapshot().1
    }
    pub fn end(&mut self, binding: &Binding) -> R<()> {
        self.check_cleanup_owner(binding)?;
        if self
            .operation
            .as_ref()
            .is_some_and(|operation| operation.disposition == Disposition::PossiblyDispatched)
        {
            return Err(
                "In-flight outcome remains uncertain; cleanup cannot claim rollback/release".into(),
            );
        }
        self.scope = None;
        self.operation = None;
        self.original_command = None;
        self.priority.active.store(false, Ordering::SeqCst);
        Ok(()) // stopped latch survives cleanup
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct OriginalStopDelivery {
    pub cancel_command: Value,
    pub cancel_outcome: Value,
    pub durable_acceptance_id: String,
}
impl OriginalStopDelivery {
    fn validate(&self) -> R<()> {
        if !identifier(&self.durable_acceptance_id)
            || !self.cancel_command.is_object()
            || !self.cancel_outcome.is_object()
            || serde_json::to_vec(self)
                .map_err(|_| "Invalid delivery encoding")?
                .len()
                > 2048
        {
            return Err(
                "Missing bounded canonical cancellation/outcome and durable acceptance".into(),
            );
        }
        Ok(())
    }
}
#[derive(Clone, PartialEq, Eq)]
struct StopIdentity {
    event_id: String,
    session_id: String,
    scope_id: String,
    source: String,
    stop_generation: u64,
    responsible: Responsible,
    target: Target,
    operation: Option<OperationReceipt>,
    command: Option<BrowserClickCommand>,
}
impl StopEvent {
    fn identity(&self) -> StopIdentity {
        StopIdentity {
            event_id: self.event_id.clone(),
            session_id: self.session_id.clone(),
            scope_id: self.scope_id.clone(),
            source: self.source.clone(),
            stop_generation: self.stop_generation,
            responsible: self.responsible.clone(),
            target: self.target.clone(),
            operation: self.operation.clone(),
            command: self.original_command.clone(),
        }
    }
}
// These capabilities cannot be deserialized or upgraded into a send owner.
// Host retains its original cleanup channel binding after send-authority revocation.
pub(super) struct CleanupBinding {
    original: StopIdentity,
}
pub(super) struct DurableDeliveryProof(OriginalStopDelivery); // no production JSON constructor
pub(super) struct StopAckBinding {
    original: StopIdentity,
    delivery: OriginalStopDelivery,
}
impl Fence {
    pub fn cleanup_binding(
        &self,
        original_owner: &TrustedOwner,
        event_id: &str,
    ) -> R<CleanupBinding> {
        let event = self.pending_stop.as_ref().ok_or("No retained stop")?;
        if event.event_id != event_id || event.responsible != original_owner.0 {
            return Err("Wrong original stop owner/event".into());
        }
        Ok(CleanupBinding {
            original: event.identity(),
        }) // no live run validation/re-capture
    }
    fn delivery_candidate(
        &self,
        cleanup: &CleanupBinding,
        proof: &DurableDeliveryProof,
    ) -> R<(StopEvent, StopAckBinding)> {
        proof.0.validate()?;
        let mut event = self.pending_stop.clone().ok_or("No retained stop")?;
        if event.identity() != cleanup.original
            || event
                .delivery
                .as_ref()
                .is_some_and(|previous| previous != &proof.0)
        {
            return Err("Stop delivery cannot transfer original command/outcome or owner".into());
        }
        event.delivery = Some(proof.0.clone());
        event.delivered = true;
        event.validate()?;
        Ok((
            event,
            StopAckBinding {
                original: cleanup.original.clone(),
                delivery: proof.0.clone(),
            },
        ))
    }
    #[cfg(test)] // raw state transition for deterministic fixtures only
    pub fn record_durable_delivery(
        &mut self,
        cleanup: &CleanupBinding,
        proof: &DurableDeliveryProof,
    ) -> R<StopAckBinding> {
        let (event, acknowledgement) = self.delivery_candidate(cleanup, proof)?;
        self.pending_stop = Some(event);
        Ok(acknowledgement)
    }
    fn acknowledgement_candidate(&self, acknowledgement: &StopAckBinding) -> R<StopEvent> {
        let mut event = self.pending_stop.clone().ok_or("No retained stop")?;
        if event.identity() != acknowledgement.original
            || !event.delivered
            || event.delivery.as_ref() != Some(&acknowledgement.delivery)
        {
            return Err(
                "Stop ACK differs from immutable original cancellation/outcome binding".into(),
            );
        }
        event.acknowledged = true;
        event.validate()?;
        Ok(event)
    }
    #[cfg(test)] // production ACK must use Controller persist-before-publish
    pub fn acknowledge_retained(&mut self, acknowledgement: &StopAckBinding) -> R<()> {
        self.pending_stop = Some(self.acknowledgement_candidate(acknowledgement)?);
        Ok(()) // no current-run capture, clear, begin or resume
    }
}

// Source-callable private core contract. Wire/bootstrap and native browser probe
// are not implemented by these types and cannot be supplied as model authority.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct JarvisAuthorBinding {
    pub author_session_id: String,
    pub conversation_id: String,
    pub parent_turn_id: String,
    pub tool_call_id: String,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct NativeDocument {
    pub connection_incarnation: String,
    pub native_session_id: String,
    pub cdp_target_id: String,
    pub frame_id: String,
    pub document_id: String,
    pub remote_object_id: String,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct BrowserTargetBinding {
    pub adapter_id: String,
    pub surface_id: String,
    pub target_id: String,
    pub target_generation: u64,
    pub context_id: String,
    pub observation_id: String,
    pub registry_generation_token: String,
    pub native_document: Option<NativeDocument>,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct BrowserClickCommand {
    pub job_id: String,
    pub action_id: String,
    pub capability_id: String,
    pub operation_id: String,
    pub registration_revision: String,
    pub local_author: JarvisAuthorBinding,
    pub target: BrowserTargetBinding,
    pub prepared_candidate: Value,
    pub action_context: Value,
}
impl BrowserClickCommand {
    fn validate(&self) -> R<()> {
        if serde_json::to_vec(self)
            .map_err(|_| "Invalid command encoding")?
            .len()
            > 4096
        {
            return Err("Prepared browser command exceeds durable receipt budget".into());
        }
        let target = &self.target;
        let author = &self.local_author;
        if ![
            &self.job_id,
            &self.action_id,
            &self.operation_id,
            &self.registration_revision,
            &author.author_session_id,
            &author.conversation_id,
            &author.parent_turn_id,
            &author.tool_call_id,
            &target.adapter_id,
            &target.surface_id,
            &target.target_id,
            &target.context_id,
            &target.observation_id,
            &target.registry_generation_token,
        ]
        .into_iter()
        .all(|value| identifier(value))
            || self.capability_id != "browser.click"
        {
            return Err("Incomplete browser click/author correlation".into());
        }
        let native = target
            .native_document
            .as_ref()
            .ok_or("native_frame_document_producer_unavailable")?;
        if ![
            &native.connection_incarnation,
            &native.native_session_id,
            &native.cdp_target_id,
            &native.frame_id,
            &native.document_id,
            &native.remote_object_id,
        ]
        .into_iter()
        .all(|value| identifier(value))
        {
            return Err("Incomplete native frame/document/object continuity".into());
        }
        let candidate = &self.prepared_candidate;
        if !candidate["candidate_id"].as_str().is_some_and(identifier)
            || candidate["capability_id"] != self.capability_id
            || candidate["context_id"] != target.context_id
            || candidate["observation_id"] != target.observation_id
            || candidate["action"]["kind"] != "browser_click"
            || candidate["action"]["tab_id"] != target.surface_id
            || candidate["action"]["target_id"] != target.target_id
        {
            return Err("Exact prepared browser click does not match target".into());
        }
        let context = &self.action_context;
        if context["job_id"] != self.job_id
            || context["action_id"] != self.action_id
            || context["adapter_id"] != target.adapter_id
            || context["context_id"] != target.context_id
            || context["observation_id"] != target.observation_id
            || context["surface_id"] != target.surface_id
            || context["generation"].as_u64() != Some(target.target_generation)
        {
            return Err("Exact browser ActionContext does not match command".into());
        }
        Ok(())
    }
    fn actor_target(&self) -> Target {
        Target {
            adapter: self.target.adapter_id.clone(),
            authority: self.target.surface_id.clone(),
            resource: self.target.target_id.clone(),
            revision: self.target.observation_id.clone(),
        }
    }
}
// This snapshot must come from the native observation producer, not echoing
// command fields. Equality includes frame/document/object and opaque registry token.
pub(super) struct NativeBrowserSnapshot {
    target: BrowserTargetBinding,
    outputs: Value,
}
pub(super) enum NativeSendOutcome {
    Crossed, // bounded crossing ACK only; long completion is separate
    Completed(Value),
    Unknown(String),
}
pub(super) enum NativeCompletion {
    Completed(Value),
    Unknown(String),
}
// Host retains this opaque cleanup/completion capability, never model JSON.
pub(super) struct PendingBrowserOperation {
    binding: Binding,
    command: BrowserClickCommand,
    responsible: Responsible,
}
pub(super) struct BrowserDispatchResult {
    pub receipt: BrowserDispatchReceipt,
    pub pending: Option<PendingBrowserOperation>,
}
impl std::ops::Deref for BrowserDispatchResult {
    type Target = BrowserDispatchReceipt;
    fn deref(&self) -> &Self::Target {
        &self.receipt
    }
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(super) struct BrowserDispatchReceipt {
    pub contract_revision: u32,
    pub session_id: String,
    pub scope_id: String,
    pub stop_generation: u64,
    pub target_generation: u64,
    pub responsible: Responsible,
    pub original_command: BrowserClickCommand,
    pub disposition: Disposition,
    pub native_receipt: Option<Value>,
    pub error: Option<String>,
    pub verification_required: bool,
    pub completion_pending: bool,
    pub revalidation_required: bool,
    pub cancel_supported: bool,
    pub cancel_requested: bool,
}
// Physical stop is independent of this mutex and never waits for a remote reply.
pub(super) struct Controller {
    state: Mutex<Fence>,
    send_gate: Mutex<()>,
    priority: Arc<PriorityStop>,
}
impl Controller {
    pub fn new(fence: Fence) -> Self {
        Self {
            priority: fence.priority.clone(),
            state: Mutex::new(fence),
            send_gate: Mutex::new(()),
        }
    }
    pub fn lock(&self) -> std::sync::LockResult<std::sync::MutexGuard<'_, Fence>> {
        self.state.lock()
    }
    pub fn try_writer(&self) -> std::sync::TryLockResult<std::sync::MutexGuard<'_, ()>> {
        if self.operation_active() {
            return Err(std::sync::TryLockError::WouldBlock);
        }
        let writer = self.send_gate.try_lock()?;
        if self.operation_active() {
            return Err(std::sync::TryLockError::WouldBlock);
        }
        Ok(writer)
    }
    pub fn operation_active(&self) -> bool {
        self.state
            .lock()
            .map_or(true, |state| state.operation.is_some())
    }
    pub fn active_summary(&self) -> Value {
        match self.state.lock() {
            Ok(state) => match (&state.scope, &state.operation) {
                (Some(scope), Some(operation)) => json!({"task_id":scope.binding.scope_id,
                    "action_id":operation.action_id,"phase":"shared_browser_operation",
                    "stop_generation":scope.binding.stop_generation,"disposition":operation.disposition}),
                _ => Value::Null,
            },
            Err(_) => json!({"phase":"shared_control_state_unavailable"}),
        }
    }
    pub fn retain_stop(
        &self,
        source: &str,
        persist: impl FnOnce(&StopEvent) -> R<()>,
    ) -> R<Option<StopEvent>> {
        self.request_stop()?;
        let event = self
            .state
            .lock()
            .map_err(|_| "Control state poisoned")?
            .stop(source)?;
        if let Some(event) = &event {
            persist(event)?;
        }
        Ok(event)
    }
    pub fn record_durable_delivery(
        &self,
        cleanup: &CleanupBinding,
        proof: &DurableDeliveryProof,
        persist: impl FnOnce(&StopEvent) -> R<()>,
    ) -> R<StopAckBinding> {
        let mut state = self.state.lock().map_err(|_| "Control state poisoned")?;
        let (candidate, acknowledgement) = state.delivery_candidate(cleanup, proof)?;
        persist(&candidate)?;
        state.pending_stop = Some(candidate);
        Ok(acknowledgement) // publish metadata/capability only after persistence
    }
    pub fn acknowledge_retained(
        &self,
        acknowledgement: &StopAckBinding,
        persist: impl FnOnce(&StopEvent) -> R<()>,
    ) -> R<()> {
        let mut state = self.state.lock().map_err(|_| "Control state poisoned")?;
        let candidate = state.acknowledgement_candidate(acknowledgement)?;
        persist(&candidate)?;
        state.pending_stop = Some(candidate);
        Ok(())
    }
    pub fn request_stop(&self) -> R<u64> {
        self.priority.fence()
    }
    pub fn request_stop_if_live(&self) -> bool {
        if !self.priority.active.load(Ordering::SeqCst) {
            return false;
        }
        let _ = self.priority.fence();
        true
    }
    pub fn target_changed(&self, generation: u64) {
        self.priority
            .target_generation
            .fetch_max(generation, Ordering::SeqCst);
        if let Ok(mut fence) = self.state.try_lock() {
            fence.target_changed(generation);
        }
    }
    pub fn dispatch_browser_click(
        &self,
        owner: &TrustedOwner,
        binding: &Binding,
        command: &BrowserClickCommand,
        cancel: Arc<AtomicBool>,
        execute: impl FnOnce(&mut BrowserSendBoundary<'_>) -> R<()>,
    ) -> R<BrowserDispatchResult> {
        command.validate()?;
        owner.0.validate()?;
        let durable_budget = serde_json::to_vec(command)
            .map_err(|_| "Invalid command encoding")?
            .len()
            + serde_json::to_vec(&owner.0)
                .map_err(|_| "Invalid owner encoding")?
                .len()
            + 3 * serde_json::to_vec(&command.actor_target())
                .map_err(|_| "Invalid target encoding")?
                .len()
            + 6144;
        if durable_budget > 12_288 {
            return Err("Original command/owner exceeds reserved durable stop budget".into());
        }
        owner
            .0
            .native_execution
            .as_ref()
            .ok_or("trusted_native_owner_producer_unavailable")?
            .validate()?;
        let _writer = self
            .send_gate
            .try_lock()
            .map_err(|_| "Shared browser writer busy; no queue/retry admitted")?;
        {
            let mut fence = self.state.lock().map_err(|_| "Control state poisoned")?;
            if let Some((original_binding, original_receipt)) =
                fence.browser_receipts.get(&command.action_id)
            {
                if original_binding != binding
                    || original_receipt.responsible != owner.0
                    || original_receipt.original_command != *command
                {
                    return Err(
                        "Action replay conflicts with original owner/binding/command".into(),
                    );
                }
                let pending =
                    original_receipt
                        .completion_pending
                        .then(|| PendingBrowserOperation {
                            binding: original_binding.clone(),
                            command: command.clone(),
                            responsible: owner.0.clone(),
                        });
                return Ok(BrowserDispatchResult {
                    receipt: original_receipt.clone(),
                    pending,
                });
            }
            if fence.browser_receipts.len() >= 256 {
                return Err("Retained browser receipt ledger full; no new admission".into());
            }
            fence.check(binding)?;
            if fence.scope.as_ref().map(|scope| &scope.responsible) != Some(&owner.0)
                || fence.scope.as_ref().map(|scope| &scope.target) != Some(&command.actor_target())
            {
                return Err("Foreign responsible owner or exact browser target".into());
            }
            if fence.operation.is_some() || !fence.used_actions.insert(command.action_id.clone()) {
                return Err("Browser operation busy or action already consumed; no replay".into());
            }
            fence.operation = Some(OperationReceipt {
                action_id: command.action_id.clone(),
                target: command.actor_target(),
                disposition: Disposition::NotDispatched,
                cancel_supported: false,
                cancel_attempted: false,
                cancel_outcome: None,
            });
            fence.original_command = Some(command.clone());
        }
        let mut boundary = BrowserSendBoundary {
            controller: self,
            binding,
            command,
            cancel,
            invoked: false,
            disposition: Disposition::NotDispatched,
            native_receipt: None,
            error: None,
            revalidation_required: false,
            cancel_supported: false,
            crossing_acknowledged: false,
        };
        // Host must invoke this synchronously inside withValidatedOwner+policy.
        // No inverse host callback is made while holding the platform state lock.
        if let Err(error) = execute(&mut boundary) {
            boundary.error = Some(error);
        }
        if !boundary.invoked && boundary.error.is_none() {
            boundary.error = Some("Native send boundary was not invoked".into());
        }
        if !self.priority.snapshot().1 && boundary.disposition != Disposition::PossiblyDispatched {
            let mut fence = self.state.lock().map_err(|_| "Control state poisoned")?;
            fence.operation = None;
            fence.original_command = None; // action ID remains consumed
        }
        let pending = boundary
            .crossing_acknowledged
            .then(|| PendingBrowserOperation {
                binding: binding.clone(),
                command: command.clone(),
                responsible: owner.0.clone(),
            });
        let result = BrowserDispatchResult {
            pending,
            receipt: BrowserDispatchReceipt {
                contract_revision: REVISION,
                session_id: binding.session_id.clone(),
                scope_id: binding.scope_id.clone(),
                stop_generation: binding.stop_generation,
                target_generation: binding.target_generation,
                responsible: owner.0.clone(),
                original_command: command.clone(),
                disposition: boundary.disposition,
                native_receipt: boundary.native_receipt,
                error: boundary.error,
                verification_required: true,
                completion_pending: boundary.crossing_acknowledged,
                revalidation_required: boundary.revalidation_required,
                cancel_supported: boundary.cancel_supported,
                cancel_requested: boundary.cancel.load(Ordering::SeqCst),
            },
        };
        self.state
            .lock()
            .map_err(|_| "Control state poisoned")?
            .browser_receipts
            .insert(
                command.action_id.clone(),
                (binding.clone(), result.receipt.clone()),
            );
        Ok(result)
    }
    // Only an original opaque in-flight capability can report completion after
    // the live turn/channel send authority has been revoked. No fresh capture.
    pub fn complete_browser_operation(
        &self,
        pending: &PendingBrowserOperation,
        completion: NativeCompletion,
        persist: impl FnOnce(&StopEvent) -> R<()>,
    ) -> R<BrowserDispatchReceipt> {
        let mut state = self.state.lock().map_err(|_| "Control state poisoned")?;
        if let Some((original_binding, original)) =
            state.browser_receipts.get(&pending.command.action_id)
        {
            if original_binding != &pending.binding
                || original.original_command != pending.command
                || original.responsible != pending.responsible
            {
                return Err("Late completion conflicts with original binding/command".into());
            }
            if original.disposition == Disposition::Completed {
                if let NativeCompletion::Completed(receipt) = &completion {
                    if original.native_receipt.as_ref() != Some(receipt) {
                        return Err("Completion reply conflicts with original outcome".into());
                    }
                }
                let original = original.clone();
                if let Some(event) = &state.pending_stop {
                    if event.scope_id == pending.binding.scope_id {
                        persist(event)?;
                    }
                }
                return Ok(original);
            }
        }
        state.check_cleanup_owner(&pending.binding)?;
        if state.scope.as_ref().map(|scope| &scope.responsible) != Some(&pending.responsible)
            || state.original_command.as_ref() != Some(&pending.command)
        {
            return Err("Late browser completion differs from original owner/command".into());
        }
        let (disposition, native_receipt, error) = match completion {
            NativeCompletion::Completed(receipt) => {
                state.complete(&pending.binding, &pending.command.action_id)?;
                (Disposition::Completed, Some(receipt), None)
            }
            NativeCompletion::Unknown(reason) => {
                (Disposition::PossiblyDispatched, None, Some(reason))
            }
        };
        let cancel_supported = state
            .operation
            .as_ref()
            .is_some_and(|operation| operation.cancel_supported);
        if !self.priority.snapshot().1 && disposition == Disposition::Completed {
            state.operation = None;
            state.original_command = None;
        }
        let result = BrowserDispatchReceipt {
            contract_revision: REVISION,
            session_id: pending.binding.session_id.clone(),
            scope_id: pending.binding.scope_id.clone(),
            stop_generation: pending.binding.stop_generation,
            target_generation: pending.binding.target_generation,
            responsible: pending.responsible.clone(),
            original_command: pending.command.clone(),
            disposition,
            native_receipt,
            error,
            verification_required: true,
            completion_pending: false,
            revalidation_required: false,
            cancel_supported,
            cancel_requested: self.priority.snapshot().1,
        };
        state.browser_receipts.insert(
            pending.command.action_id.clone(),
            (pending.binding.clone(), result.clone()),
        );
        if let Some(event) = &state.pending_stop {
            if event.scope_id == pending.binding.scope_id {
                persist(event)?;
            }
        }
        Ok(result)
    }
}
pub(super) struct SendFence {
    priority: Arc<PriorityStop>,
    generation: u64,
    target_generation: u64,
    cancel: Arc<AtomicBool>,
}
impl SendFence {
    pub fn check(&self) -> R<()> {
        let (generation, stopped) = self.priority.snapshot();
        if stopped || generation != self.generation || self.cancel.load(Ordering::SeqCst) {
            return Err("Physical stop/revocation or exact job cancellation fenced send".into());
        }
        if self.priority.target_generation.load(Ordering::SeqCst) != self.target_generation {
            return Err("Target changed; revalidation required without task stop".into());
        }
        Ok(())
    }
}
pub(super) struct BrowserSendBoundary<'a> {
    controller: &'a Controller,
    binding: &'a Binding,
    command: &'a BrowserClickCommand,
    cancel: Arc<AtomicBool>,
    invoked: bool,
    disposition: Disposition,
    native_receipt: Option<Value>,
    error: Option<String>,
    revalidation_required: bool,
    cancel_supported: bool,
    crossing_acknowledged: bool,
}
impl BrowserSendBoundary<'_> {
    // The trusted host callback revalidates owner+policy BEFORE calling this.
    // A real native adapter supplies a fresh snapshot and sends here, never after
    // returning a precheck token. Once entered, lost replies are possibly sent.
    pub fn send_native(
        &mut self,
        current: NativeBrowserSnapshot,
        cancel_supported: bool,
        send: impl FnOnce(&SendFence) -> NativeSendOutcome,
    ) -> R<()> {
        if self.invoked {
            return Err("Browser action boundary cannot be replayed".into());
        }
        self.invoked = true;
        let guard = SendFence {
            priority: self.controller.priority.clone(),
            generation: self.binding.stop_generation,
            target_generation: self.binding.target_generation,
            cancel: self.cancel.clone(),
        };
        if let Err(error) = guard.check() {
            self.revalidation_required =
                !self.controller.priority.snapshot().1 && !self.cancel.load(Ordering::SeqCst);
            return Err(error);
        }
        if current.target != self.command.target {
            self.revalidation_required = true;
            return Err("Native target/frame/document/observation continuity changed".into());
        }
        {
            let mut fence = self
                .controller
                .state
                .lock()
                .map_err(|_| "Control state poisoned")?;
            let target = self.command.actor_target();
            fence.check(self.binding)?;
            if !fence.operation.as_ref().is_some_and(|operation| {
                operation.action_id == self.command.action_id
                    && operation.target == target
                    && operation.disposition == Disposition::NotDispatched
            }) {
                return Err("Reserved immutable browser operation changed".into());
            }
            fence
                .operation
                .as_mut()
                .ok_or("No reserved operation")?
                .cancel_supported = cancel_supported;
            guard.check()?;
            fence.crossing_send_boundary(
                self.binding,
                &self.command.action_id,
                &target,
                &current.outputs,
            )?;
        }
        self.cancel_supported = cancel_supported;
        self.disposition = Disposition::PossiblyDispatched;
        match send(&guard) {
            NativeSendOutcome::Crossed => self.crossing_acknowledged = true,
            NativeSendOutcome::Completed(receipt) => {
                self.native_receipt = Some(receipt);
                self.disposition = Disposition::Completed;
                self.controller
                    .state
                    .lock()
                    .map_err(|_| "Control state poisoned")?
                    .complete(self.binding, &self.command.action_id)?;
            }
            NativeSendOutcome::Unknown(error) => self.error = Some(error),
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn owner() -> TrustedOwner {
        TrustedOwner(Responsible {
            thread_id: "actual-thread".into(),
            run_id: "actual-run".into(),
            author_turn_id: "actual-author-turn".into(),
            conversation_id: None,
            parent_turn_id: None,
            job_id: None,
            native_execution: None,
        })
    }
    fn target() -> Target {
        Target {
            adapter: "semantic-http".into(),
            authority: "actual-app-session".into(),
            resource: "actual-document".into(),
            revision: "observed-revision".into(),
        }
    }
    fn outputs() -> Value {
        json!({"DP-5":{"logical":{"x":0,"y":0,"width":800,"height":600}},
        "eDP-1":{"logical":{"x":800,"y":0,"width":1536,"height":960}}})
    }
    fn fixture() -> (Fence, Binding) {
        let mut fence = Fence::new("actor-session".into());
        let permission = ExplicitContinuation {
            decision_id: "actual-user-decision".into(),
            session_id: "actor-session".into(),
            stopped_generation: 1,
        };
        let binding = fence
            .begin(
                &owner(),
                &permission,
                "scope-1",
                "private-capability",
                target(),
            )
            .unwrap();
        (fence, binding)
    }
    fn ready(fence: &mut Fence, binding: &Binding) {
        let inventory = outputs();
        let mapped = Fence::display_inventory(&inventory).unwrap();
        fence.indicator_ready(binding, &mapped, &inventory).unwrap();
    }
    #[test]
    fn aggregate_ready_and_exact_target_required_before_one_operation() {
        let (mut fence, binding) = fixture();
        assert!(fence
            .admit(&binding, &target(), "action", &outputs(), false)
            .is_err());
        assert!(fence
            .indicator_ready(&binding, &json!({}), &outputs())
            .is_err());
        ready(&mut fence, &binding);
        let mut foreign = target();
        foreign.authority = "foreign-session".into();
        assert!(fence
            .admit(&binding, &foreign, "action", &outputs(), false)
            .is_err());
        fence
            .admit(&binding, &target(), "action", &outputs(), false)
            .unwrap();
        assert!(fence
            .admit(&binding, &target(), "other-action", &outputs(), false)
            .is_err());
        assert!(fence
            .crossing_send_boundary(&binding, "foreign-action", &target(), &outputs())
            .is_err());
        fence
            .crossing_send_boundary(&binding, "action", &target(), &outputs())
            .unwrap();
        assert!(
            fence
                .crossing_send_boundary(&binding, "action", &target(), &outputs())
                .is_err(),
            "no send replay"
        );
    }
    #[test]
    fn ordinary_input_only_stales_target_not_scope_or_stop_generation() {
        let (mut fence, binding) = fixture();
        ready(&mut fence, &binding);
        let generation = fence.stop_generation;
        fence.target_changed(1);
        assert!(fence.active());
        assert!(!fence.stopped);
        assert!(fence.pending_stop.is_none());
        assert_eq!(fence.stop_generation, generation);
        assert!(fence
            .admit(&binding, &target(), "action", &outputs(), false)
            .is_err());
        let fresh = fence.reground(&binding, &target()).unwrap();
        fence
            .admit(&fresh, &target(), "action", &outputs(), false)
            .unwrap();
        fence
            .crossing_send_boundary(&fresh, "action", &target(), &outputs())
            .unwrap();
        fence.complete(&fresh, "action").unwrap();
        fence.end(&fresh).unwrap();
    }
    #[test]
    fn physical_stop_fences_waiting_action_retains_owner_and_ack_never_resumes() {
        let (mut fence, binding) = fixture();
        ready(&mut fence, &binding);
        fence
            .admit(&binding, &target(), "waiting", &outputs(), false)
            .unwrap();
        let event = fence.stop("physical_escape").unwrap().unwrap();
        assert_eq!(event.responsible, owner().0);
        assert_eq!(
            event.operation.as_ref().unwrap().disposition,
            Disposition::NotDispatched
        );
        assert!(fence
            .crossing_send_boundary(&binding, "waiting", &target(), &outputs())
            .is_err());
        assert!(fence.acknowledge(&event.event_id, &owner()).is_err());
        let mut foreign = owner();
        foreign.0.run_id = "foreign-run".into();
        assert!(fence.delivered(&event.event_id, &foreign).is_err());
        fence.delivered(&event.event_id, &owner()).unwrap();
        fence.acknowledge(&event.event_id, &owner()).unwrap();
        assert!(fence.stopped);
        assert!(fence
            .crossing_send_boundary(&binding, "waiting", &target(), &outputs())
            .is_err());
        fence.end(&binding).unwrap();
        assert!(fence.stopped);
        let stale = ExplicitContinuation {
            decision_id: "new-decision".into(),
            session_id: "actor-session".into(),
            stopped_generation: binding.stop_generation,
        };
        assert!(fence
            .begin(&owner(), &stale, "new-scope", "new-token", target())
            .is_err());
        let decision = ExplicitContinuation {
            decision_id: "new-decision".into(),
            session_id: "actor-session".into(),
            stopped_generation: fence.stop_generation,
        };
        assert!(fence
            .begin(&owner(), &decision, "scope-1", "new-token", target())
            .is_err());
        fence
            .begin(&owner(), &decision, "new-scope", "new-token", target())
            .unwrap();
        assert!(fence
            .crossing_send_boundary(&binding, "waiting", &target(), &outputs())
            .is_err());
    }
    #[test]
    fn already_sent_is_uncertain_until_actual_receipt_not_cancellation_ack() {
        let (mut fence, binding) = fixture();
        ready(&mut fence, &binding);
        fence
            .admit(&binding, &target(), "sent", &outputs(), true)
            .unwrap();
        fence
            .crossing_send_boundary(&binding, "sent", &target(), &outputs())
            .unwrap();
        let event = fence.stop("physical_escape").unwrap().unwrap();
        assert_eq!(
            event.operation.unwrap().disposition,
            Disposition::PossiblyDispatched
        );
        fence
            .cancel_result(&binding, "sent", "cancel_request_accepted_outcome_unknown")
            .unwrap();
        assert_eq!(
            fence
                .pending_stop
                .as_ref()
                .unwrap()
                .operation
                .as_ref()
                .unwrap()
                .disposition,
            Disposition::PossiblyDispatched
        );
        assert!(fence.end(&binding).is_err());
        let mut wrong = binding.clone();
        wrong.token = "wrong".into();
        assert!(fence.complete(&wrong, "sent").is_err());
        fence.complete(&binding, "sent").unwrap();
        assert_eq!(
            fence
                .pending_stop
                .as_ref()
                .unwrap()
                .operation
                .as_ref()
                .unwrap()
                .disposition,
            Disposition::PossiblyDispatched
        );
        assert_eq!(
            fence
                .pending_stop
                .as_ref()
                .unwrap()
                .latest_operation
                .as_ref()
                .unwrap()
                .disposition,
            Disposition::Completed
        );
        fence.end(&binding).unwrap();
        assert!(fence.stopped);
    }
    #[test]
    fn hotplug_invalidates_ready_without_aborting_scope() {
        let (mut fence, binding) = fixture();
        ready(&mut fence, &binding);
        let changed = json!({"DP-5":{"logical":{"x":0,"y":0,"width":800,"height":600}}});
        assert!(fence
            .admit(&binding, &target(), "action", &changed, false)
            .is_err());
        assert!(fence.active());
        let mapped = Fence::display_inventory(&changed).unwrap();
        fence.indicator_ready(&binding, &mapped, &changed).unwrap();
        fence
            .admit(&binding, &target(), "action", &changed, false)
            .unwrap();
        assert!(
            fence
                .crossing_send_boundary(&binding, "action", &target(), &outputs())
                .is_err(),
            "coverage changed after admission"
        );
        fence
            .crossing_send_boundary(&binding, "action", &target(), &changed)
            .unwrap();
        assert!(fence
            .cancel_result(&binding, "action", "unsupported")
            .is_err());
    }
    #[test]
    fn repeated_stop_dedupes_notification_and_restart_never_revives_owner_scope() {
        let (mut fence, binding) = fixture();
        ready(&mut fence, &binding);
        let first = fence.stop("physical_escape").unwrap().unwrap();
        let again = fence.stop("physical_escape").unwrap().unwrap();
        assert_eq!(first.event_id, again.event_id);
        let bytes = serde_json::to_vec(&again).unwrap();
        assert!(!String::from_utf8(bytes.clone())
            .unwrap()
            .contains("private-capability"));
        let restored: StopEvent = serde_json::from_slice(&bytes).unwrap();
        let mut restarted = Fence::new("new-actor-session".into());
        restarted.restore_stop(restored).unwrap();
        assert!(restarted.stopped);
        assert!(!restarted.active());
        let old_session_permission = ExplicitContinuation {
            decision_id: "actual-user-decision".into(),
            session_id: "actor-session".into(),
            stopped_generation: restarted.stop_generation,
        };
        assert!(restarted
            .begin(
                &owner(),
                &old_session_permission,
                "fresh-id",
                "fresh-token",
                target()
            )
            .is_err());
        assert_eq!(restarted.pending_stop.unwrap().responsible, owner().0);
    }
    #[test]
    fn unsupported_host_bridge_is_truthfully_unavailable() {
        let capability = capability();
        assert_eq!(capability["available"], false);
        assert_eq!(capability["trusted_host_context_available"], false);
        assert_eq!(capability["supported_transports"], json!([]));
        let mut malformed = owner();
        malformed.0.author_turn_id.clear();
        assert!(malformed.0.validate().is_err());
    }
}
#[cfg(test)]
mod browser_tests {
    use super::*;
    use std::sync::mpsc;
    // Deliberately fake native observations/host authority: these fixtures test
    // state/callback arbitration only, never a production trust source or CDP.
    fn owner() -> TrustedOwner {
        TrustedOwner(Responsible {
            thread_id: "fixture-thread".into(),
            run_id: "fixture-run".into(),
            author_turn_id: "fixture-turn".into(),
            conversation_id: None,
            parent_turn_id: None,
            job_id: None,
            native_execution: Some(NativeExecution {
                environment_id: "fixture-env".into(),
                attempt_id: "fixture-attempt".into(),
                root_node_id: "fixture-root".into(),
                provider_instance_id: "fixture-provider".into(),
                provider_session_id: "fixture-provider-session".into(),
                provider_thread_id: "fixture-provider-thread".into(),
                native_turn_id: "fixture-native-turn".into(),
                runtime_incarnation: "fixture-runtime".into(),
                native_call_id: "fixture-native-call".into(),
            }),
        })
    }
    fn outputs() -> Value {
        json!({"DP-5":{"logical":{"x":0,"y":0,"width":800,"height":600}}})
    }
    fn command() -> BrowserClickCommand {
        BrowserClickCommand {
            job_id: "job-1".into(),
            action_id: "action-1".into(),
            capability_id: "browser.click".into(),
            operation_id: "operation".into(),
            registration_revision: "registration-1".into(),
            local_author: JarvisAuthorBinding {
                author_session_id: "pi-author".into(),
                conversation_id: "app-conversation".into(),
                parent_turn_id: "app-parent-turn".into(),
                tool_call_id: "app-tool-call".into(),
            },
            target: BrowserTargetBinding {
                adapter_id: "chrome".into(),
                surface_id: "tab".into(),
                target_id: "element".into(),
                target_generation: 7,
                context_id: "context".into(),
                observation_id: "obs".into(),
                registry_generation_token: "opaque:not-a-number".into(),
                native_document: Some(NativeDocument {
                    connection_incarnation: "connection-1".into(),
                    native_session_id: "native-session".into(),
                    cdp_target_id: "native-tab".into(),
                    frame_id: "frame-1".into(),
                    document_id: "document-1".into(),
                    remote_object_id: "object-1".into(),
                }),
            },
            prepared_candidate: json!({"candidate_id":"candidate","capability_id":"browser.click","context_id":"context","observation_id":"obs",
                "action":{"kind":"browser_click","tab_id":"tab","target_id":"element"},"label":"fixture click"}),
            action_context: json!({"job_id":"job-1","action_id":"action-1","adapter_id":"chrome","context_id":"context","observation_id":"obs","surface_id":"tab","generation":7}),
        }
    }
    fn fixture() -> (Arc<Controller>, TrustedOwner, Binding, BrowserClickCommand) {
        let owner = owner();
        let command = command();
        let mut fence = Fence::new("browser-actor".into());
        let permission = ExplicitContinuation {
            decision_id: "fixture-user-decision".into(),
            session_id: "browser-actor".into(),
            stopped_generation: 1,
        };
        let binding = fence
            .begin(
                &owner,
                &permission,
                "browser-scope",
                "private-scope-token",
                command.actor_target(),
            )
            .unwrap();
        let mapped = Fence::display_inventory(&outputs()).unwrap();
        fence
            .indicator_ready(&binding, &mapped, &outputs())
            .unwrap();
        (Arc::new(Controller::new(fence)), owner, binding, command)
    }
    fn snapshot(command: &BrowserClickCommand) -> NativeBrowserSnapshot {
        NativeBrowserSnapshot {
            target: command.target.clone(),
            outputs: outputs(),
        }
    }
    fn cancel() -> Arc<AtomicBool> {
        Arc::new(AtomicBool::new(false))
    }
    #[test]
    fn browser_and_physical_writer_share_one_gate_and_unknown_keeps_reservation() {
        let (controller, owner, binding, command) = fixture();
        let physical = controller.try_writer().unwrap();
        assert!(controller
            .dispatch_browser_click(&owner, &binding, &command, cancel(), |_| panic!(
                "parallel writer"
            ))
            .is_err());
        drop(physical);
        controller
            .dispatch_browser_click(&owner, &binding, &command, cancel(), |boundary| {
                boundary.send_native(snapshot(&command), false, |_| {
                    NativeSendOutcome::Unknown("unknown remote effect".into())
                })
            })
            .unwrap();
        assert!(matches!(
            controller.try_writer(),
            Err(std::sync::TryLockError::WouldBlock)
        ));
        assert!(controller.operation_active());
    }
    #[test]
    fn durable_delivery_and_ack_report_success_only_after_persistence() {
        let (controller, owner, binding, command) = fixture();
        controller
            .dispatch_browser_click(&owner, &binding, &command, cancel(), |boundary| {
                controller.retain_stop("physical_escape", |event| event.validate())?;
                boundary.send_native(snapshot(&command), false, |_| panic!("fenced"))
            })
            .unwrap();
        let event_id = controller
            .lock()
            .unwrap()
            .pending_stop
            .as_ref()
            .unwrap()
            .event_id
            .clone();
        let cleanup = controller
            .lock()
            .unwrap()
            .cleanup_binding(&owner, &event_id)
            .unwrap();
        let proof = DurableDeliveryProof(OriginalStopDelivery {
            cancel_command: json!({"fixture_original_job":"job-1"}),
            cancel_outcome: json!({"fixture_original_outcome":"unknown"}),
            durable_acceptance_id: "fixture-durable-ledger".into(),
        });
        let original = controller.lock().unwrap().pending_stop.clone().unwrap();
        assert!(controller
            .record_durable_delivery(&cleanup, &proof, |_| Err(
                "fixture persistence failure".into()
            ))
            .is_err());
        {
            let mut state = controller.lock().unwrap();
            assert_eq!(state.pending_stop.as_ref(), Some(&original));
            assert!(!state.pending_stop.as_ref().unwrap().acknowledged);
            state.end(&binding).unwrap(); // terminal cleanup cannot bypass failed persistence
            let permission = ExplicitContinuation {
                decision_id: "fixture-explicit-decision".into(),
                session_id: binding.session_id.clone(),
                stopped_generation: state.stop_generation,
            };
            assert!(state
                .begin(
                    &owner,
                    &permission,
                    "next-scope",
                    "next-token",
                    command.actor_target()
                )
                .is_err());
            assert!(state.stopped);
        }
        let acknowledgement = controller
            .record_durable_delivery(&cleanup, &proof, |event| event.validate())
            .unwrap();
        let delivered = controller.lock().unwrap().pending_stop.clone().unwrap();
        assert!(delivered.delivered);
        assert!(!delivered.acknowledged);
        assert!(controller
            .acknowledge_retained(&acknowledgement, |_| Err(
                "fixture ACK persistence failure".into()
            ))
            .is_err());
        {
            let mut state = controller.lock().unwrap();
            assert_eq!(state.pending_stop.as_ref(), Some(&delivered));
            assert!(!state.pending_stop.as_ref().unwrap().acknowledged);
            let permission = ExplicitContinuation {
                decision_id: "fixture-explicit-decision".into(),
                session_id: binding.session_id.clone(),
                stopped_generation: state.stop_generation,
            };
            assert!(state
                .begin(
                    &owner,
                    &permission,
                    "next-scope",
                    "next-token",
                    command.actor_target()
                )
                .is_err());
            assert!(state.stopped);
        }
        controller
            .acknowledge_retained(&acknowledgement, |event| event.validate())
            .unwrap();
        let mut state = controller.lock().unwrap();
        assert!(state.stopped, "durable ACK itself never resumes");
        let acknowledged = state.pending_stop.clone().unwrap();
        assert!(acknowledged.acknowledged);
        assert!(acknowledged.identity() == original.identity());
        let permission = ExplicitContinuation {
            decision_id: "fixture-explicit-decision".into(),
            session_id: binding.session_id.clone(),
            stopped_generation: state.stop_generation,
        };
        assert!(state
            .begin(
                &owner,
                &permission,
                "next-scope",
                "next-token",
                command.actor_target()
            )
            .is_ok());
    }

    #[test]
    fn bounded_crossing_ack_releases_host_callback_and_late_receipt_uses_original_capability() {
        let (controller, owner, binding, command) = fixture();
        let result = controller
            .dispatch_browser_click(&owner, &binding, &command, cancel(), |boundary| {
                boundary.send_native(snapshot(&command), true, |_| NativeSendOutcome::Crossed)
            })
            .unwrap();
        assert!(result.completion_pending);
        assert_eq!(result.disposition, Disposition::PossiblyDispatched);
        let pending = result.pending.unwrap();
        assert!(
            controller.send_gate.try_lock().is_ok(),
            "canonical host callback need not wait for long completion"
        );
        assert!(
            controller.try_writer().is_err(),
            "unresolved operation keeps effect reservation"
        );
        controller
            .retain_stop("physical_escape", |event| event.validate())
            .unwrap();
        let completed = controller
            .complete_browser_operation(
                &pending,
                NativeCompletion::Completed(json!({"native_rpc":"matched","clicked":true})),
                |event| event.validate(),
            )
            .unwrap();
        assert_eq!(completed.disposition, Disposition::Completed);
        assert_eq!(completed.original_command, command);
        let replay = controller
            .complete_browser_operation(
                &pending,
                NativeCompletion::Completed(json!({"native_rpc":"matched","clicked":true})),
                |event| event.validate(),
            )
            .unwrap();
        assert_eq!(replay, completed);
        assert!(controller
            .complete_browser_operation(
                &pending,
                NativeCompletion::Completed(json!({"foreign":"reply"})),
                |_| Ok(())
            )
            .is_err());
        assert!(controller.lock().unwrap().stopped);
    }

    #[test]
    fn exact_browser_command_is_correlated_and_consumed_once() {
        let (controller, owner, binding, command) = fixture();
        let effects = AtomicUsize::new(0);
        let receipt = controller
            .dispatch_browser_click(&owner, &binding, &command, cancel(), |boundary| {
                boundary.send_native(snapshot(&command), false, |fence| {
                    fence.check().unwrap();
                    effects.fetch_add(1, Ordering::SeqCst);
                    NativeSendOutcome::Completed(json!({"clicked":true}))
                })
            })
            .unwrap();
        assert_eq!(receipt.original_command, command);
        assert_eq!(receipt.responsible, owner.0);
        assert_eq!(receipt.disposition, Disposition::Completed);
        assert!(receipt.verification_required);
        let replay = controller
            .dispatch_browser_click(&owner, &binding, &command, cancel(), |_| {
                panic!("replayed send")
            })
            .unwrap();
        assert_eq!(replay.receipt, receipt.receipt);
        let mut conflict = command.clone();
        conflict.registration_revision = "conflicting-command".into();
        assert!(controller
            .dispatch_browser_click(&owner, &binding, &conflict, cancel(), |_| panic!(
                "conflicting replay"
            ))
            .is_err());
        assert_eq!(effects.load(Ordering::SeqCst), 1);
    }
    #[test]
    fn missing_native_producer_or_owner_never_invokes_callback() {
        let (controller, owner, binding, mut command) = fixture();
        command.target.native_document = None;
        assert!(controller
            .dispatch_browser_click(&owner, &binding, &command, cancel(), |_| panic!(
                "missing native probe"
            ))
            .is_err());
        let mut unbound = owner;
        unbound.0.native_execution = None;
        assert!(controller
            .dispatch_browser_click(&unbound, &binding, &self::command(), cancel(), |_| panic!(
                "copied local author became owner"
            ))
            .is_err());
    }
    #[test]
    fn frame_document_object_registry_and_candidate_continuity_refuse_before_send() {
        for change in [
            "frame",
            "document",
            "object",
            "connection",
            "registry",
            "generation",
        ] {
            let (controller, owner, binding, command) = fixture();
            let mut current = snapshot(&command);
            match change {
                "frame" => {
                    current.target.native_document.as_mut().unwrap().frame_id = "new-frame".into()
                }
                "document" => {
                    current.target.native_document.as_mut().unwrap().document_id =
                        "new-document".into()
                }
                "object" => {
                    current
                        .target
                        .native_document
                        .as_mut()
                        .unwrap()
                        .remote_object_id = "new-object".into()
                }
                "connection" => {
                    current
                        .target
                        .native_document
                        .as_mut()
                        .unwrap()
                        .connection_incarnation = "new-connection".into()
                }
                "registry" => {
                    current.target.registry_generation_token = "different-opaque-token".into()
                }
                "generation" => current.target.target_generation += 1,
                _ => unreachable!(),
            }
            let receipt = controller
                .dispatch_browser_click(&owner, &binding, &command, cancel(), |boundary| {
                    boundary.send_native(current, false, |_| panic!("stale native target sent"))
                })
                .unwrap();
            assert_eq!(receipt.disposition, Disposition::NotDispatched, "{change}");
            assert!(receipt.revalidation_required);
            assert!(controller.lock().unwrap().active());
        }
        let (controller, owner, binding, mut command) = fixture();
        command.prepared_candidate["action"]["target_id"] = json!("foreign");
        assert!(controller
            .dispatch_browser_click(&owner, &binding, &command, cancel(), |_| panic!(
                "wrong candidate"
            ))
            .is_err());
    }
    #[test]
    fn ordinary_input_requires_regrounding_without_stop_and_pre_cancel_never_sends() {
        let (controller, owner, binding, command) = fixture();
        let receipt = controller
            .dispatch_browser_click(&owner, &binding, &command, cancel(), |boundary| {
                controller.target_changed(1);
                boundary.send_native(snapshot(&command), false, |_| panic!("stale target sent"))
            })
            .unwrap();
        assert!(receipt.revalidation_required);
        assert_eq!(receipt.disposition, Disposition::NotDispatched);
        let fence = controller.lock().unwrap();
        assert!(fence.active());
        assert!(fence.pending_stop.is_none());
        drop(fence);
        let (controller, owner, binding, command) = fixture();
        let cancelled = cancel();
        cancelled.store(true, Ordering::SeqCst);
        let receipt = controller
            .dispatch_browser_click(&owner, &binding, &command, cancelled, |boundary| {
                boundary.send_native(snapshot(&command), true, |_| panic!("cancelled send"))
            })
            .unwrap();
        assert_eq!(receipt.disposition, Disposition::NotDispatched);
        assert!(receipt.cancel_requested);
    }
    #[test]
    fn shared_escape_priority_fence_does_not_wait_for_held_state_lock() {
        let (controller, _owner, binding, _command) = fixture();
        let state = controller.lock().unwrap();
        let worker_controller = controller.clone();
        let (done_tx, done_rx) = mpsc::channel();
        let worker = thread::spawn(move || {
            done_tx
                .send(worker_controller.request_stop_if_live())
                .unwrap();
        });
        assert!(done_rx.recv_timeout(Duration::from_secs(2)).unwrap());
        let guard = SendFence {
            priority: controller.priority.clone(),
            generation: binding.stop_generation,
            target_generation: binding.target_generation,
            cancel: cancel(),
        };
        assert!(
            guard.check().is_err(),
            "shared send fenced while bookkeeping is locked"
        );
        drop(state);
        worker.join().unwrap();
    }

    #[test]
    fn physical_stop_retains_waiting_command_before_crossing() {
        let (controller, owner, binding, command) = fixture();
        let receipt = controller
            .dispatch_browser_click(&owner, &binding, &command, cancel(), |boundary| {
                assert!(controller.request_stop_if_live());
                let event = controller.lock().unwrap().stop("physical_escape")?.unwrap();
                assert_eq!(event.original_command.as_ref(), Some(&command));
                assert_eq!(
                    event.operation.unwrap().disposition,
                    Disposition::NotDispatched
                );
                boundary.send_native(snapshot(&command), false, |_| {
                    panic!("physical ESC fenced send")
                })
            })
            .unwrap();
        assert_eq!(receipt.disposition, Disposition::NotDispatched);
        assert!(controller.lock().unwrap().stopped);
    }
    #[test]
    fn priority_stop_does_not_wait_for_network_and_cleanup_ack_keeps_original_identity() {
        let (controller, owner, binding, command) = fixture();
        let (entered_tx, entered_rx) = mpsc::channel();
        let (release_tx, release_rx) = mpsc::channel();
        let worker_controller = controller.clone();
        let worker_owner = owner.clone();
        let worker_binding = binding.clone();
        let worker_command = command.clone();
        let worker = thread::spawn(move || {
            worker_controller
                .dispatch_browser_click(
                    &worker_owner,
                    &worker_binding,
                    &worker_command,
                    cancel(),
                    |boundary| {
                        boundary.send_native(snapshot(&worker_command), true, |fence| {
                            entered_tx.send(()).unwrap();
                            release_rx.recv_timeout(Duration::from_secs(2)).unwrap();
                            assert!(fence.check().is_err());
                            NativeSendOutcome::Unknown("reply unknown after physical ESC".into())
                        })
                    },
                )
                .unwrap()
        });
        entered_rx.recv_timeout(Duration::from_secs(2)).unwrap();
        assert!(controller.request_stop_if_live());
        let mut state = controller
            .state
            .try_lock()
            .expect("remote send must not hold actor state");
        let event = state.stop("physical_escape").unwrap().unwrap();
        assert_eq!(event.original_command.as_ref(), Some(&command));
        assert_eq!(
            event.operation.as_ref().unwrap().disposition,
            Disposition::PossiblyDispatched
        );
        let cleanup = state.cleanup_binding(&owner, &event.event_id).unwrap();
        let proof = DurableDeliveryProof(OriginalStopDelivery {
            cancel_command: json!({"fixture_original_cancel_job":command.job_id}),
            cancel_outcome: json!({"fixture_outcome":"accepted-not-rollback"}),
            durable_acceptance_id: "fixture-durable-1".into(),
        });
        let ack = state.record_durable_delivery(&cleanup, &proof).unwrap();
        state.acknowledge_retained(&ack).unwrap();
        assert!(state.stopped);
        let mut new_owner = owner.clone();
        new_owner.0.run_id = "new-run".into();
        assert!(state.cleanup_binding(&new_owner, &event.event_id).is_err());
        assert!(state
            .crossing_send_boundary(
                &binding,
                &command.action_id,
                &command.actor_target(),
                &outputs()
            )
            .is_err());
        let saved = state.pending_stop.clone().unwrap();
        drop(state);
        release_tx.send(()).unwrap();
        let receipt = worker.join().unwrap();
        assert_eq!(receipt.disposition, Disposition::PossiblyDispatched);
        let mut restarted = Fence::new("new-runtime".into());
        restarted.restore_stop(saved).unwrap();
        restarted.acknowledge_retained(&ack).unwrap();
        assert!(restarted.stopped);
        assert_eq!(restarted.pending_stop.unwrap().responsible, owner.0);
    }
    #[test]
    fn callback_failure_or_unknown_reply_never_becomes_completed_or_replayed() {
        let (controller, owner, binding, command) = fixture();
        let receipt = controller
            .dispatch_browser_click(&owner, &binding, &command, cancel(), |_| {
                Err("host owner rollover before send".into())
            })
            .unwrap();
        assert_eq!(receipt.disposition, Disposition::NotDispatched);
        let replay = controller
            .dispatch_browser_click(&owner, &binding, &command, cancel(), |_| {
                panic!("rollover replay")
            })
            .unwrap();
        assert_eq!(replay.receipt, receipt.receipt);
        let (controller, owner, binding, command) = fixture();
        let receipt = controller
            .dispatch_browser_click(&owner, &binding, &command, cancel(), |boundary| {
                boundary.send_native(snapshot(&command), false, |_| {
                    NativeSendOutcome::Unknown("lost actual reply".into())
                })
            })
            .unwrap();
        assert_eq!(receipt.disposition, Disposition::PossiblyDispatched);
        assert!(receipt.native_receipt.is_none());
        assert!(controller.lock().unwrap().end(&binding).is_err());
    }
    #[test]
    fn cleanup_capability_refuses_conflicting_original_cancellation_outcome() {
        let (controller, owner, binding, command) = fixture();
        controller
            .dispatch_browser_click(&owner, &binding, &command, cancel(), |boundary| {
                controller.request_stop()?;
                controller.lock().unwrap().stop("physical_escape")?;
                boundary.send_native(snapshot(&command), false, |_| panic!("stopped"))
            })
            .unwrap();
        let mut state = controller.lock().unwrap();
        let event_id = state.pending_stop.as_ref().unwrap().event_id.clone();
        let cleanup = state.cleanup_binding(&owner, &event_id).unwrap();
        let proof = DurableDeliveryProof(OriginalStopDelivery {
            cancel_command: json!({"fixture_job":"job-1"}),
            cancel_outcome: json!({"fixture_receipt":"original"}),
            durable_acceptance_id: "fixture-ledger".into(),
        });
        let ack = state.record_durable_delivery(&cleanup, &proof).unwrap();
        let altered = DurableDeliveryProof(OriginalStopDelivery {
            cancel_command: json!({"fixture_job":"job-other"}),
            ..proof.0.clone()
        });
        assert!(state.record_durable_delivery(&cleanup, &altered).is_err());
        state.acknowledge_retained(&ack).unwrap();
        assert!(state.stopped);
    }
}

pub(super) fn capability() -> Value {
    json!({"contract_revision":REVISION,"state_core":true,"available":false,
        "trusted_host_context_available":false,"responsible_turn_delivery_available":false,
        "external_dispatch_bridge_available":false,"native_browser_probe_available":false,
        "browser_callback_kernel":true,"supported_transports":[],
        "reason":"Authenticated live T3 run/author-turn binding and durable delivery bridge are not implemented; no shared-control endpoint is enabled",
        "ack_clears_stop":false,"automatic_resume":false})
}
