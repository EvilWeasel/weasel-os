# Codex with scoped MCP cancellation

The laptop and its Codex ACP adapter use the same source-built Codex 0.162.0.
`default.nix` pins upstream commit
`c1382380de69521303b416720a52f42d51af6248`, the locked Cargo dependencies,
Rust 1.95.0 from the immutable Nixpkgs revision in `toolchain.nix`, and upstream's matching
V8 pointer-compression/sandbox archive and binding. Both `codex` and
`codex-code-mode-host` come from that build. No authentication is replaced.
The toolchain pin matches the package set used for this build, while other
libraries use the caller's configured package set. Advancing the general
unstable input therefore does not implicitly replace the required Rust compiler.

The stock client drops its MCP response waiter when a tool is interrupted,
without forwarding `notifications/cancelled`. A persistent server can therefore
continue a desktop batch after the local agent reports interruption. The patch
captures the original request ID and peer synchronously, then forwards one
request-scoped cancellation attempt when that waiter is dropped. Both legacy
and modern tool-input paths are patched. Terminal replies disarm the guard.

Cancellation delivery is bounded and best effort: the detached send has a
two-second timeout, and connection/runtime shutdown can prevent delivery.
The local agent's interruption acknowledgement is not confirmation that physical
input has stopped. The desktop actor's released state, empty queue, fresh UI,
and completed effects must still be checked. A separate desktop cancel and the
Niri takeover shortcut remain available.

The same production patch also connects each code-mode cell's nested tool
callbacks to the original `functions.exec` invocation cancellation token.
That token stays attached after a cell yields. An explicit stop cancels the
callback token before its response waiter is dropped, reaching the existing
request-scoped MCP cancellation guard. Later callbacks from that stopped owner
are refused before dispatch. Normal yield, preemption and successful callbacks
retain their existing behavior; other owners and sessions are unaffected.

An explicit session interrupt also revokes the session's callback admission
generation before its first await, including delegates from completed turns
and an idle session. A guard keeps admission closed throughout overlapping
interrupts; a task starting during an interrupt cannot reopen it. Only a
subsequent task can obtain a fresh generation, and old delegates remain
revoked. Normal yield and successful turn completion do not revoke admission.

These guards do not terminate the host JavaScript cell. Its existing
`code_mode_interrupt` feature policy is separate. Actual T3 delivery of a
session interrupt after a turn has completed still needs a live check. The
original live T3 test that exposed this gap remains a failed normal stop; its
separate safety fallback prevented the subsequent canary input. A build or
in-memory test cannot replace the repeated live cancellation check.

The second patch retains seven focused memory-transport tests in the locked
`codex-rmcp-client` package and adds seven owner-cancellation helper tests and
ten admission tests, plus four delegate integration tests in `codex-core`.
The Nix check phase runs the helper and admission tests and all six delegate
tests, including the two existing tests, after the original MCP tests;
installation checks both binaries. Full Nix
checks and actual T3/Codex interruption tests are separate acceptance steps.
A fresh client process is required to load a changed Codex executable;
reconnecting only the desktop MCP does not replace Codex.

The release build disables LTO explicitly with `CARGO_PROFILE_RELEASE_LTO=off`
and uses 16 codegen units. Release optimization remains at level 3, debug
information stays disabled, and Cargo still uses two build jobs. This avoids
the previous whole-program LTO configuration after an observed build put severe
pressure on the laptop's RAM and swap. It does not impose a memory limit on Nix
builders or establish a measured speed improvement; build memory and runtime
behavior still require verification. All four focused check groups remain
enabled. Cargo's `false` value would retain local Thin-LTO, so `off` is
intentional. See the [Cargo profile documentation](https://doc.rust-lang.org/cargo/reference/profiles.html).

On a future upstream update, inspect the new SDK's waiter/drop cancellation
behavior and both call paths before rebasing or removing the patch. Keep the
source, Cargo lock, Rust toolchain pin and matching V8 assets together. The reference
sources are [the pinned Codex revision](https://github.com/openai/codex/tree/c1382380de69521303b416720a52f42d51af6248)
and [its pinned MCP SDK](https://github.com/modelcontextprotocol/rust-sdk/tree/3e636cab26c013eca5131103c03d20237f12c4df).

The daily updater reads the official latest release as a review hint and keeps
this five-file source bundle unchanged until a reviewed source adapter can
rebase or remove the patches. It does not replace the source package with an
npm binary. Other reviewed batch updates remain available and verify the
candidate's selected source derivation, actual Home Manager CLI/ACP links and
the ACP wrapper's unique `CODEX_PATH` export, including when the Codex output
itself did not change. The initial dated rebase review is 10 October 2026.
