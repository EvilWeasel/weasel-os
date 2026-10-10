//! MCP presentation only. The daemon response, stored observations, guards,
//! event receipts and last_result never pass through this projection.
use serde_json::{json, Value};

// Abbreviate only exact known prose at exact paths. A changed capability or
// future backend warning passes through verbatim, rather than being masked by
// a generic "supported" flag. Operational numeric/boolean state is untouched.
const PROSE: &[(&str, &str, &str)] = &[
    ("/capabilities/keyboard/shortcuts", "app shortcuts: persistent canonical German evdev Wayland keyboard; keymap refreshed before every chord. key_scope=compositor or chords containing Super/meta/logo use an owned Linux uinput device so Niri compositor bindings can process them; permission/monitor/device-open failures refuse before any batch input. Device creation is a capability side effect; open/write acknowledgement is not UI success", "App: persistent German-evdev Wayland keyboard; refresh keymap per chord. Compositor/Super/meta/logo: owned uinput. Permission/monitor/device-open failure refuses the whole batch. Device creation has effects; acknowledgement is not UI success."),
    ("/capabilities/keyboard/unicode_text/auto", "plain clipboard for known Electron app IDs or >1000characters; wtype for shorter text in other apps", "Known Electron or >1000 chars: plain clipboard; otherwise wtype."),
    ("/capabilities/keyboard/unicode_text/electron_keyboard", "known unreliable due physical DomCode and supplementary Unicode; explicit override requires app-specific proof", "Electron keyboard: unreliable DomCode/supplementary Unicode; override needs app-specific proof."),
    ("/capabilities/clipboard/backend", "Rust wlr-data-control helper with an owned user scope", "Rust wlr-data-control; owned user scope."),
    ("/capabilities/clipboard/holder_lifetime", "separate user scope; source replacement or graphical session shutdown", "Separate scope until source replacement/session shutdown."),
    ("/capabilities/clipboard/plain_text_restore", "best effort; source ownership checked, no atomic selection CAS; skipped after cancel/takeover", "Best effort; check ownership; no atomic CAS; skip after cancel/takeover."),
    ("/capabilities/clipboard/rich_or_nontext_restore", "supported bounded MIME payloads including HTML, COMPOUND_TEXT and original Chromium metadata; no portal handles/password hints", "Bounded MIME: HTML/COMPOUND_TEXT/original Chromium metadata; exclude portal handles/password hints."),
    ("/capabilities/clipboard/rich_preserve_request", "snapshot same offer before replacement; unknown/oversized/sensitive formats refuse", "Same-offer snapshot; refuse unknown/oversized/sensitive formats."),
    ("/capabilities/semantic_tree", "desktop_semantic: read-only Cua application/PID tree; unique window inventory mapping does not attest node window scope; Cua bounds are not screenshot coordinates", "Read-only Cua app/PID tree; mapping does not attest node window scope; Cua bounds are not screenshot coordinates."),
    ("/capabilities/takeover", "physical Escape or explicit takeover latches; ordinary physical activity only invalidates targets and stops a conflicting batch without task cancellation; fresh observe then deliberate continuation", "Physical Escape/explicit takeover latch. Ordinary input invalidates targets/stops conflicting batch, not task; fresh observe + deliberate continuation."),
    ("/global_keyboard/readiness", "authenticated Niri peer has own exact event node open; not proof of configured/UI acceptance", "Authenticated Niri peer opened exact own event node; not configured/UI acceptance proof."),
    ("/input_policy/collision_limit", "evdev observation and input dispatch cannot be atomic; overlapping dispatched input may have partial effects", "Evdev/dispatch are not atomic; overlap may cause partial effects."),
    ("/input_policy/recovery", "ordinary activity or held controls require release, known input monitor state, fresh observation and deliberate continuation; no desktop_resume needed", "Ordinary input/holds: release, known monitor state, fresh observe, deliberate continuation; no resume."),
    ("/input_readiness/note", "Image remains available for reasoning during ordinary activity or held controls. Input readiness is a snapshot, not input permission; desktop_act always freshly revalidates the original generation, released controls, focus and target.", "Image usable during input/holds. Readiness is a snapshot, not permission; act freshly validates original generation, released controls, focus and target."),
];

// Non-security inventory fingerprint: exposes catalog/capability changes even
// where the bulky display mode catalog is available through detailed discovery.
fn fingerprint(value: &Value) -> String {
    let mut hash = 0xcbf29ce484222325u64;
    for byte in value.to_string().as_bytes() {
        hash = (hash ^ u64::from(*byte)).wrapping_mul(0x100000001b3);
    }
    format!("fnv1a64:{hash:016x}")
}

// Only a fully understood inventory may be omitted. A malformed or future
// field anywhere in the catalog can carry information the presenter cannot
// safely summarize, including on a mode that is not currently selected.
fn known_valid_mode(mode: &Value) -> bool {
    let Some(object) = mode.as_object() else {
        return false;
    };
    object.keys().all(|key| {
        matches!(
            key.as_str(),
            "width" | "height" | "refresh_rate" | "is_preferred"
        )
    }) && ["width", "height", "refresh_rate"]
        .iter()
        .all(|key| mode[*key].as_u64().is_some_and(|value| value > 0))
        && object.get("is_preferred").is_none_or(Value::is_boolean)
}

fn compact_observation(data: &mut Value) -> bool {
    if !data["observation_id"].is_string()
        || !data["capture"].is_object()
        || data.get("_presentation").is_some()
    {
        return false;
    }
    let capabilities_fingerprint = fingerprint(&data["capabilities"]);
    if let Some(outputs) = data["outputs"].as_object_mut() {
        for output in outputs.values_mut() {
            // A future backend may use these names itself; retain its fields
            // and full catalog rather than overwrite unfamiliar metadata.
            if [
                "selected_mode",
                "available_mode_count",
                "mode_inventory_fingerprint",
            ]
            .iter()
            .any(|key| output.get(*key).is_some())
            {
                continue;
            }
            // Preserve the original current_mode index and its exact entry.
            // Any unfamiliar or invalid catalog entry keeps the whole catalog.
            let selected = output["current_mode"]
                .as_u64()
                .and_then(|n| usize::try_from(n).ok())
                .and_then(|n| {
                    let modes = output["modes"].as_array()?;
                    if !modes.iter().all(known_valid_mode) {
                        return None;
                    }
                    modes.get(n).cloned()
                });
            if let Some(selected) = selected {
                let modes = output["modes"].clone();
                let mode_count = modes.as_array().map(Vec::len).unwrap_or(0);
                if let Some(object) = output.as_object_mut() {
                    object.remove("modes");
                    object.insert("selected_mode".into(), selected);
                    object.insert("available_mode_count".into(), json!(mode_count));
                    object.insert(
                        "mode_inventory_fingerprint".into(),
                        json!(fingerprint(&modes)),
                    );
                }
            }
        }
    }
    for (path, original, concise) in PROSE {
        if data.pointer(path).and_then(Value::as_str) == Some(*original) {
            if let Some(value) = data.pointer_mut(path) {
                *value = json!(concise);
            }
        }
    }
    data["_presentation"] = json!({
        "format":"compact-v1",
        "capabilities_fingerprint":capabilities_fingerprint,
        "full_details":"detailed=true; desktop_windows also returns full mode catalogs",
        "omissions":"Fully known valid mode catalogs omitted; unfamiliar or malformed entries retain the whole catalog. Exact known explanatory prose abbreviated. All window/layout/workspace/capture/guard fields retained."
    });
    true
}

// Field order is presentation only. IDs, fresh readiness and action effects
// precede bulky inventories; no keys, values or array order are removed.
const FIRST: &[&str] = &[
    "schema",
    "task_id",
    "status",
    "error",
    "input_conflict",
    "completed_actions",
    "requested_actions",
    "effects",
    "actor_release_confirmed",
    "fresh_observation_required",
    "automatic_replay",
    "observation_id",
    "epoch",
    "input_generation",
    "expected_input_generation",
    "current_input_generation",
    "observed_unix_ms",
    "monotonic_ms",
    "monotonic_system_ms",
    "expires_after_ms",
    "input_ready",
    "action_ready",
    "takeover_latched",
    "input_activity_during_capture",
    "fresh_observation_required_for_input",
    "input_readiness",
    "input_policy",
    "focused_window",
    "capture",
    "timing_ms",
    "total_ms",
    "after_observation_error",
    "verification",
];
const LAST: &[&str] = &[
    "capabilities",
    "windows",
    "workspaces",
    "outputs",
    "after_observation",
];

// Use serde_json for every key and primitive, including Unicode/control
// escaping and exact Number formatting. Never manually escape or coerce data.
fn prioritized_json(value: &Value) -> String {
    fn field(out: &mut String, first: &mut bool, key: &str, value: &Value) {
        if !*first {
            out.push(',');
        }
        *first = false;
        out.push_str(&json!(key).to_string());
        out.push(':');
        write(out, value);
    }
    fn write(out: &mut String, value: &Value) {
        match value {
            Value::Object(object) => {
                out.push('{');
                let mut first = true;
                for key in FIRST {
                    if let Some(value) = object.get(*key) {
                        field(out, &mut first, key, value);
                    }
                }
                for (key, value) in object {
                    if !FIRST.contains(&key.as_str()) && !LAST.contains(&key.as_str()) {
                        field(out, &mut first, key, value);
                    }
                }
                for key in LAST {
                    if let Some(value) = object.get(*key) {
                        field(out, &mut first, key, value);
                    }
                }
                out.push('}');
            }
            Value::Array(values) => {
                out.push('[');
                for (index, value) in values.iter().enumerate() {
                    if index != 0 {
                        out.push(',');
                    }
                    write(out, value);
                }
                out.push(']');
            }
            _ => out.push_str(&value.to_string()),
        }
    }
    let mut out = String::new();
    write(&mut out, value);
    out
}

/// Clone-free ownership projection at the stdio MCP edge only. Non-text
/// content, including actual PNG blocks and metadata, stays byte-for-byte.
/// Malformed or unfamiliar envelopes/text pass through unchanged.
pub(crate) fn present(tool: &str, args: &Value, mut result: Value) -> Value {
    if args["detailed"] == true || !matches!(tool, "desktop_observe" | "desktop_act") {
        return result;
    }
    if let Some(content) = result.get_mut("content").and_then(Value::as_array_mut) {
        for block in content {
            if block["type"] != "text" {
                continue;
            }
            let Some(text) = block["text"].as_str() else {
                continue;
            };
            let Ok(mut data) = serde_json::from_str::<Value>(text) else {
                continue;
            };
            let changed = if tool == "desktop_observe" {
                compact_observation(&mut data)
            } else if data["after_observation"].is_object() {
                compact_observation(&mut data["after_observation"])
            } else {
                false
            };
            // Exact untouched text remains exact, including formatting on
            // unrecognized/failed responses without a fresh observation.
            if changed {
                block["text"] = json!(prioritized_json(&data));
            }
        }
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    fn observation() -> Value {
        let mut value = json!({
            "schema":1,"observation_id":"obs-session-19","epoch":7,"input_generation":9,
            "current_input_generation":10,"takeover_latched":true,"action_ready":false,
            "input_ready":false,"input_activity_during_capture":true,
            "fresh_observation_required_for_input":true,"monotonic_ms":42.125,
            "monotonic_system_ms":777.5,"observed_unix_ms":888,"expires_after_ms":60000,
            "capture":{"path":"/private/crop.png","reference_path":"/private/full.png","view":{"x":3,"y":5,"width":10,"height":20},"image_width":10,"image_height":20,"output_logical":{"scale":1.25,"x":1536},"full_output_width":2752,"full_output_height":1152},
            "focused_window":{"id":11,"pid":22,"app_id":"test","title":"äöüß 🦦","workspace_id":33,"layout":{"window_size":[101,201]}},
            "windows":[{"id":11,"pid":22,"workspace_id":33,"layout":{"window_size":[101,201]}},{"id":12,"pid":23,"workspace_id":44,"layout":{"window_size":[301,401]}}],
            "workspaces":[{"id":33,"output":"DP-6","is_focused":true},{"id":44,"output":"DP-5","is_focused":false}],
            "outputs":{"DP-6":{"current_mode":1,"logical":{"x":1536,"width":2752,"scale":1.25},"modes":[{"width":100,"height":80,"refresh_rate":60000},{"width":200,"height":160,"refresh_rate":120000}]}},
            "input_policy":{"held_state_known":false,"held_controls":1,"automatic_replay":false},
            "input_readiness":{"action_ready":false,"takeover_latched":true},
            "capabilities":{"capture":false,"window_focus":false,"future_bridge":{"ready":false,"error":"not supported"}},
            "timing_ms":{"capture":87.041,"observe_total":154.814},
            "future_safety_field":{"invalid":true,"reason":"new guard failure"}
        });
        for (path, original, _) in PROSE {
            let mut current = &mut value;
            let parts: Vec<&str> = path.trim_start_matches('/').split('/').collect();
            for key in &parts[..parts.len() - 1] {
                if current[*key].is_null() {
                    current[*key] = json!({});
                }
                current = &mut current[*key];
            }
            current[parts[parts.len() - 1]] = json!(original);
        }
        value
    }
    fn envelope(data: Value) -> Value {
        json!({"content":[{"type":"text","text":data.to_string()},{"type":"image","mimeType":"image/png","data":"ACTUAL_IMAGE_BYTES_BASE64","_meta":{"detail":"original"}}],"isError":false,"_meta":{"future":"preserve"}})
    }
    fn text(result: &Value) -> Value {
        serde_json::from_str(result["content"][0]["text"].as_str().unwrap()).unwrap()
    }
    #[test]
    fn priority_order_keeps_exact_strict_projection_and_moves_observation_guards_first() {
        let mut strict = observation();
        assert!(compact_observation(&mut strict));
        let ordered = present("desktop_observe", &json!({}), envelope(observation()));
        assert_eq!(text(&ordered), strict);
        let raw = ordered["content"][0]["text"].as_str().unwrap();
        for key in [
            "observation_id",
            "epoch",
            "input_generation",
            "input_ready",
            "action_ready",
            "takeover_latched",
            "focused_window",
            "capture",
        ] {
            assert!(
                raw.find(&format!("\"{key}\"")).unwrap() < raw.find("\"windows\"").unwrap(),
                "{key}"
            );
        }
        assert!(raw.find("\"observation_id\"").unwrap() < 100);
    }
    #[test]
    fn priority_act_errors_effects_release_and_unknown_metadata_precede_after_observation() {
        let original = json!({"schema":1,"status":"input_conflict","task_id":"owned","error":"partial effects remain","completed_actions":2,"requested_actions":5,"effects":[{"kind":"paste","uncertain":true}],"actor_release_confirmed":false,"unknown_future":{"warning":"keep"},"after_observation":observation()});
        let mut strict = original.clone();
        assert!(compact_observation(&mut strict["after_observation"]));
        let mut raw = envelope(original);
        raw["isError"] = json!(true);
        let ordered = present("desktop_act", &json!({}), raw);
        assert_eq!(text(&ordered), strict);
        assert_eq!(ordered["isError"], true);
        let raw = ordered["content"][0]["text"].as_str().unwrap();
        let after = raw.find("\"after_observation\"").unwrap();
        for key in [
            "status",
            "error",
            "effects",
            "actor_release_confirmed",
            "unknown_future",
        ] {
            assert!(raw.find(&format!("\"{key}\"")).unwrap() < after, "{key}");
        }
    }
    #[test]
    fn priority_roundtrip_preserves_unicode_escaped_controls_arrays_numbers_and_large_integers() {
        let values = [
            json!({"unknown\"\\\nkey":"äöüß 🦦\n\r\t\u{0000}\"\\", "after_observation":{"unknown":{"arrays":[null,true,false,42,-11,0.5,1e-12,-5e100,{"Überraschung":"✓"}]}},"status":"known", "u64":u64::MAX,"i64":i64::MIN,"numeric_string":"18446744073709551615","empty":{},"array":[]}),
            json!([null,true,false,0,u64::MAX,i64::MIN,"\n\t\u{0000}\"\\🦦",{"status":"nested","after_observation":null}]),
            json!(null),
            json!(true),
            json!(false),
            json!(1.25),
            json!(u64::MAX),
            json!(i64::MIN),
            json!("äöüß 🦦"),
        ];
        for value in values {
            let ordered = prioritized_json(&value);
            let parsed: Value = serde_json::from_str(&ordered).unwrap();
            assert_eq!(parsed, value);
            assert_eq!(ordered.len(), value.to_string().len());
        }
    }
    #[test]
    fn priority_preserves_arbitrarily_named_nested_fields_and_array_order() {
        let mut value = json!({"after_observation":null,"array":[9,1,7,2],"unknown":{"id":12,"layout":{"capture":[4,3,2,1]},"status":{"opaque":true}}});
        for depth in 0..24 {
            value = json!({"before":depth,"nested":value,"after_observation":{"null":null},"outputs":[depth,24-depth]});
        }
        assert_eq!(
            serde_json::from_str::<Value>(&prioritized_json(&value)).unwrap(),
            value
        );
    }
    #[test]
    fn priority_missing_scalar_or_non_array_content_keeps_unfamiliar_envelopes_exact() {
        for raw in [
            json!(null),
            json!(true),
            json!("unknown"),
            json!([]),
            json!({"error":"transport normalized failure"}),
            json!({"content":null}),
            json!({"content":"unknown format"}),
            json!({"content":{"future":true}}),
        ] {
            for tool in ["desktop_observe", "desktop_act"] {
                assert_eq!(present(tool, &json!({}), raw.clone()), raw);
            }
        }
    }
    #[test]
    fn priority_keeps_non_json_error_text_non_text_blocks_and_other_metadata_exact() {
        let mut raw = envelope(observation());
        raw["content"].as_array_mut().unwrap().extend([
            json!({"type":"text","text":"Backend unavailable\nNo blind input","_meta":{"error":true}}),
            json!({"type":"text","text":" {\"error\":\"No current capture\",\"status\":\"failed\"} "}),
            json!({"type":"resource_link","uri":"private:opaque","name":"keep"}),
            json!({"type":"image","mimeType":"image/svg+xml","data":"SVG_BYTES","_meta":{"codex/imageDetail":"low"}}),
        ]);
        raw["isError"] = json!(true);
        let ordered = present("desktop_observe", &json!({}), raw.clone());
        assert_eq!(
            &ordered["content"].as_array().unwrap()[1..],
            &raw["content"].as_array().unwrap()[1..]
        );
        assert_eq!(ordered["isError"], raw["isError"]);
        assert_eq!(ordered["_meta"], raw["_meta"]);
    }
    #[test]
    fn guard_id_geometry_images_and_unknown_fields_are_unchanged() {
        let original = observation();
        let raw = envelope(original.clone());
        let compact = present("desktop_observe", &json!({}), raw.clone());
        let data = text(&compact);
        for (key, value) in original.as_object().unwrap() {
            if !matches!(
                key.as_str(),
                "outputs" | "capabilities" | "global_keyboard" | "input_policy" | "input_readiness"
            ) {
                assert_eq!(&data[key], value, "preserved field {key}");
            }
        }
        assert_eq!(data["input_policy"]["held_state_known"], false);
        assert_eq!(data["input_policy"]["held_controls"], 1);
        assert_eq!(
            data["capabilities"]["future_bridge"],
            original["capabilities"]["future_bridge"]
        );
        assert_eq!(compact["content"][1], raw["content"][1]);
        assert_eq!(compact["_meta"], raw["_meta"]);
        assert_eq!(compact["isError"], raw["isError"]);
    }
    #[test]
    fn mode_index_is_not_relabelled_and_exact_selected_entry_is_retained() {
        let original = observation();
        let data = text(&present(
            "desktop_observe",
            &json!({}),
            envelope(original.clone()),
        ));
        assert_eq!(data["outputs"]["DP-6"]["current_mode"], 1);
        assert_eq!(
            data["outputs"]["DP-6"]["selected_mode"],
            original["outputs"]["DP-6"]["modes"][1]
        );
        assert_eq!(
            data["outputs"]["DP-6"]["logical"],
            original["outputs"]["DP-6"]["logical"]
        );
        assert_eq!(data["outputs"]["DP-6"]["available_mode_count"], 2);
        assert!(data["outputs"]["DP-6"].get("modes").is_none());
    }
    #[test]
    fn unknown_mode_selection_keeps_full_catalog_including_disabled_outputs() {
        for selection in [json!(null), json!(-1), json!(999), json!("1"), json!(1.5)] {
            let mut original = observation();
            original["outputs"]["DP-6"]["current_mode"] = selection;
            let data = text(&present(
                "desktop_observe",
                &json!({}),
                envelope(original.clone()),
            ));
            assert_eq!(data["outputs"], original["outputs"]);
        }
    }
    #[test]
    fn malformed_selected_mode_keeps_whole_catalog() {
        for mode in [
            json!(null),
            json!("unknown"),
            json!([]),
            json!({"width":200}),
            json!({"width":0,"height":160,"refresh_rate":120000}),
        ] {
            let mut original = observation();
            original["outputs"]["DP-6"]["modes"][1] = mode;
            let data = text(&present(
                "desktop_observe",
                &json!({}),
                envelope(original.clone()),
            ));
            assert_eq!(data["outputs"], original["outputs"]);
        }
    }
    #[test]
    fn unfamiliar_nonselected_mode_fields_keep_whole_catalog() {
        let mut original = observation();
        original["outputs"]["DP-6"]["modes"][0]["future_guard"] =
            json!({"warning":"requires a new capability","limit":[null,3,"äöüß"]});
        let data = text(&present(
            "desktop_observe",
            &json!({}),
            envelope(original.clone()),
        ));
        assert_eq!(data["outputs"], original["outputs"]);
    }
    #[test]
    fn malformed_nonselected_mode_entries_keep_whole_catalog() {
        for mode in [
            json!(null),
            json!("unknown"),
            json!([]),
            json!({"width":100,"height":80}),
            json!({"width":0,"height":80,"refresh_rate":60000}),
            json!({"width":"100","height":80,"refresh_rate":60000}),
            json!({"width":100,"height":80,"refresh_rate":60000,"is_preferred":1}),
            json!({"width":100,"height":80,"refresh_rate":60000,"is_preferred":null}),
        ] {
            let mut original = observation();
            original["outputs"]["DP-6"]["modes"][0] = mode;
            let data = text(&present(
                "desktop_observe",
                &json!({}),
                envelope(original.clone()),
            ));
            assert_eq!(data["outputs"], original["outputs"]);
        }
    }
    #[test]
    fn known_valid_inventory_with_optional_preference_omits_catalog_preserving_selection() {
        let mut original = observation();
        original["outputs"]["DP-6"]["modes"][0]["is_preferred"] = json!(false);
        original["outputs"]["DP-6"]["modes"][1]["is_preferred"] = json!(true);
        let data = text(&present(
            "desktop_observe",
            &json!({}),
            envelope(original.clone()),
        ));
        assert_eq!(data["outputs"]["DP-6"]["current_mode"], 1);
        assert_eq!(
            data["outputs"]["DP-6"]["selected_mode"],
            original["outputs"]["DP-6"]["modes"][1]
        );
        assert_eq!(data["outputs"]["DP-6"]["available_mode_count"], 2);
        assert!(data["outputs"]["DP-6"].get("modes").is_none());
    }
    #[test]
    fn changed_capability_warning_is_verbatim_and_changes_fingerprint() {
        let original = observation();
        let before = text(&present(
            "desktop_observe",
            &json!({}),
            envelope(original.clone()),
        ));
        let mut changed = original;
        changed["capabilities"]["keyboard"]["shortcuts"] =
            json!("UNAVAILABLE: bridge changed; do not dispatch");
        let after = text(&present(
            "desktop_observe",
            &json!({}),
            envelope(changed.clone()),
        ));
        assert_eq!(
            after["capabilities"]["keyboard"]["shortcuts"],
            changed["capabilities"]["keyboard"]["shortcuts"]
        );
        assert_ne!(
            before["_presentation"]["capabilities_fingerprint"],
            after["_presentation"]["capabilities_fingerprint"]
        );
    }
    #[test]
    fn every_abbreviated_prose_path_keeps_changed_unknown_values_verbatim() {
        for (path, _, _) in PROSE {
            let mut original = observation();
            *original.pointer_mut(path).unwrap() =
                json!("NEW LIMITATION: requires explicit review");
            let data = text(&present(
                "desktop_observe",
                &json!({}),
                envelope(original.clone()),
            ));
            assert_eq!(data.pointer(path), original.pointer(path), "{path}");
        }
    }
    #[test]
    fn future_presentation_or_mode_metadata_is_never_overwritten() {
        let mut original = observation();
        original["_presentation"] = json!({"format":"future-v2","warning":"new limitation"});
        let raw = envelope(original);
        assert_eq!(present("desktop_observe", &json!({}), raw.clone()), raw);
        for key in [
            "selected_mode",
            "available_mode_count",
            "mode_inventory_fingerprint",
        ] {
            let mut original = observation();
            original["outputs"]["DP-6"][key] = json!({"future":"preserve verbatim"});
            let data = text(&present(
                "desktop_observe",
                &json!({}),
                envelope(original.clone()),
            ));
            assert_eq!(data["outputs"], original["outputs"]);
        }
    }
    #[test]
    fn mode_inventory_change_is_visible_even_for_same_selected_mode() {
        let original = observation();
        let before = text(&present(
            "desktop_observe",
            &json!({}),
            envelope(original.clone()),
        ));
        let mut changed = original;
        changed["outputs"]["DP-6"]["modes"][0]["refresh_rate"] = json!(59999);
        let after = text(&present("desktop_observe", &json!({}), envelope(changed)));
        assert_eq!(
            before["outputs"]["DP-6"]["selected_mode"],
            after["outputs"]["DP-6"]["selected_mode"]
        );
        assert_ne!(
            before["outputs"]["DP-6"]["mode_inventory_fingerprint"],
            after["outputs"]["DP-6"]["mode_inventory_fingerprint"]
        );
    }
    #[test]
    fn act_effects_errors_uncertainty_and_failed_iserror_are_exact() {
        let raw = envelope(
            json!({"schema":1,"status":"input_conflict","completed_actions":2,"requested_actions":5,"effects":[{"kind":"paste","uncertain":true}],"error":"generation changed","after_observation_error":"frame late","actor_release_confirmed":false,"fresh_observation_required":true,"timing_ms":{"dispatch_and_release":11.125},"after_observation":observation()}),
        );
        let mut failed = raw.clone();
        failed["isError"] = json!(true);
        let compact = present("desktop_act", &json!({}), failed.clone());
        let after = text(&compact);
        let before = text(&failed);
        for (key, value) in before.as_object().unwrap() {
            if key != "after_observation" {
                assert_eq!(&after[key], value);
            }
        }
        assert_eq!(compact["isError"], true);
        assert_eq!(compact["content"][1], failed["content"][1]);
    }
    #[test]
    fn detailed_true_is_exact_full_reply_for_both_tools() {
        let raw = envelope(observation());
        assert_eq!(
            present("desktop_observe", &json!({"detailed":true}), raw.clone()),
            raw
        );
        let raw = envelope(json!({"after_observation":observation(),"effects":[]}));
        assert_eq!(
            present("desktop_act", &json!({"detailed":true}), raw.clone()),
            raw
        );
    }
    #[test]
    fn non_observation_tools_failed_or_malformed_text_are_unchanged() {
        for tool in [
            "desktop_windows",
            "desktop_status",
            "desktop_semantic",
            "desktop_cancel",
        ] {
            let raw = envelope(observation());
            assert_eq!(present(tool, &json!({}), raw.clone()), raw);
        }
        for tool in ["desktop_observe", "desktop_act"] {
            for text in [
                "not JSON",
                " {\"error\":\"No capture available\"} ",
                "null",
                "[]",
            ] {
                let raw = json!({"content":[{"type":"text","text":text}],"isError":true});
                assert_eq!(present(tool, &json!({}), raw.clone()), raw);
            }
        }
    }
}
