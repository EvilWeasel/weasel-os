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

The second patch adds seven focused memory-transport tests to the same locked
`codex-rmcp-client` package. The Nix check phase runs those tests; installation
checks both binaries. Full Nix checks and actual T3/Codex interruption tests are
separate acceptance steps. A fresh client process is required to load a changed
Codex executable; reconnecting only the desktop MCP does not replace Codex.

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
