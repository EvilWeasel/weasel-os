//! One bounded, explicit retry of release/receipt on already owned actuators.
//! The executor has no press/move/create operation. No epoch or latch access.
use std::time::{Duration, Instant};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Backend {
    Pointer,
    Keyboard,
    GlobalKeyboard,
}

impl Backend {
    pub(crate) fn name(self) -> &'static str {
        match self {
            Self::Pointer => "pointer",
            Self::Keyboard => "keyboard",
            Self::GlobalKeyboard => "global_keyboard",
        }
    }
}

#[derive(Debug)]
pub(crate) struct Stage {
    pub(crate) backend: Backend,
    pub(crate) status: &'static str,
    pub(crate) error: Option<String>,
}

#[derive(Debug)]
pub(crate) struct Report {
    pub(crate) confirmed: bool,
    pub(crate) stages: Vec<Stage>,
}

/// False from the executor means no actuator exists, never UI success.
/// Divide remaining time among remaining backends so a slow receipt does not
/// consume the budget of other release attempts. Each gets only one attempt.
pub(crate) fn retry(
    budget: Duration,
    mut now: impl FnMut() -> Instant,
    mut execute: impl FnMut(Backend, Instant) -> Result<bool, String>,
) -> Result<Report, String> {
    if !(Duration::from_millis(200)..=Duration::from_millis(2000)).contains(&budget) {
        return Err("Release recovery timeout_ms must be 200..2000".into());
    }
    let deadline = now() + budget;
    let backends = [Backend::Pointer, Backend::Keyboard, Backend::GlobalKeyboard];
    let mut report = Report {
        confirmed: true,
        stages: Vec::new(),
    };
    for (i, backend) in backends.into_iter().enumerate() {
        let stage_start = now();
        let remaining = deadline.saturating_duration_since(stage_start);
        let slot = remaining / (3 - i) as u32;
        if slot.is_zero() {
            report.confirmed = false;
            report.stages.push(Stage {
                backend,
                status: "deadline_exhausted",
                error: Some("Release recovery deadline exhausted; no additional call made".into()),
            });
            continue;
        }
        let result = execute(backend, stage_start + slot);
        let late = now() > deadline;
        let (status, error) = match result {
            Ok(_) if late => (
                "unconfirmed",
                Some("Release acknowledgement arrived after recovery deadline".into()),
            ),
            Ok(true) => ("receipt_confirmed", None),
            Ok(false) => ("no_owned_actuator", None),
            Err(error) => ("unconfirmed", Some(error)),
        };
        report.confirmed &= error.is_none();
        report.stages.push(Stage {
            backend,
            status,
            error,
        });
    }
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::{Cell, RefCell};

    #[test]
    fn invalid_budget_calls_no_backend() {
        for ms in [0, 199, 2001] {
            let calls = Cell::new(0);
            assert!(retry(Duration::from_millis(ms), Instant::now, |_, _| {
                calls.set(calls.get() + 1);
                Ok(true)
            })
            .is_err());
            assert_eq!(calls.get(), 0);
        }
    }

    #[test]
    fn successful_retry_is_once_per_existing_backend() {
        let calls = RefCell::new(Vec::new());
        let report = retry(Duration::from_millis(1500), Instant::now, |b, t| {
            assert!(t.saturating_duration_since(Instant::now()) <= Duration::from_millis(1500));
            calls.borrow_mut().push(b);
            Ok(true)
        })
        .unwrap();
        assert!(report.confirmed);
        assert_eq!(
            *calls.borrow(),
            [Backend::Pointer, Backend::Keyboard, Backend::GlobalKeyboard]
        );
        assert!(report
            .stages
            .iter()
            .all(|s| s.status == "receipt_confirmed"));
    }

    #[test]
    fn absent_actuator_is_explicit_and_not_ui_evidence() {
        let report = retry(Duration::from_millis(200), Instant::now, |_, _| Ok(false)).unwrap();
        assert!(report.confirmed);
        assert!(report
            .stages
            .iter()
            .all(|s| s.status == "no_owned_actuator"));
    }

    #[test]
    fn failed_receipt_does_not_skip_other_release_attempts_or_claim_success() {
        let calls = RefCell::new(Vec::new());
        let report = retry(Duration::from_millis(1500), Instant::now, |b, _| {
            calls.borrow_mut().push(b);
            if b == Backend::Pointer {
                Err("original compositor timeout".into())
            } else {
                Ok(true)
            }
        })
        .unwrap();
        assert!(!report.confirmed);
        assert_eq!(calls.borrow().len(), 3);
        assert_eq!(
            report.stages[0].error.as_deref(),
            Some("original compositor timeout")
        );
        assert_eq!(report.stages[1].status, "receipt_confirmed");
    }

    #[test]
    fn one_shared_deadline_and_fair_slots_are_enforced() {
        let start = Instant::now();
        let elapsed = Cell::new(Duration::ZERO);
        let slots = RefCell::new(Vec::new());
        let report = retry(
            Duration::from_millis(1500),
            || start + elapsed.get(),
            |_, until| {
                let slot = until.saturating_duration_since(start + elapsed.get());
                slots.borrow_mut().push(slot);
                elapsed.set(elapsed.get() + slot);
                Ok(true)
            },
        )
        .unwrap();
        assert!(report.confirmed);
        assert_eq!(*slots.borrow(), [Duration::from_millis(500); 3]);
        assert_eq!(elapsed.get(), Duration::from_millis(1500));
    }

    #[test]
    fn late_acknowledgement_never_turns_a_timeout_green() {
        let start = Instant::now();
        let elapsed = Cell::new(Duration::ZERO);
        let calls = Cell::new(0);
        let report = retry(
            Duration::from_millis(200),
            || start + elapsed.get(),
            |_, _| {
                calls.set(calls.get() + 1);
                elapsed.set(Duration::from_millis(201));
                Ok(true)
            },
        )
        .unwrap();
        assert!(!report.confirmed);
        assert_eq!(calls.get(), 1);
        assert_eq!(report.stages[0].status, "unconfirmed");
        assert_eq!(report.stages[1].status, "deadline_exhausted");
    }
}
