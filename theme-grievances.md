# Theme Grievances

Date: 2026-03-22

This file is the working memory for the current theme migration cleanup. It should stay separate from `current-plan.md`.

## Observed regressions

- Many app icons are missing in the application launcher.
  - Firefox no longer shows an image in the launcher.
  - Handy no longer shows an image in the launcher.
  - Several other entries that previously had icons now render as text-only entries.
  - Some apps still show images, for example Steam and Google Chrome, so this is partial rather than total breakage.
- Several status bar / tray / workspace icons look broken after the Stylix removal and Matugen migration.
- App theming is incomplete or inconsistent.
  - Handy is showing a light theme.
  - Firefox is showing a light theme.
  - The file manager is showing a light theme.
  - Kitty is still rendered as a flat black terminal instead of following the wallpaper-driven theme.
- DMS font selections are not taking effect correctly.
  - Monaspace fonts are selected in DMS, including Nerd Font variants.
  - The configured fonts are likely not installed system-wide anymore.
  - The desktop should have the GitHub Monaspace family and the Nerd Font variants available.

## Likely root-cause areas to inspect

- Matugen output generation and where the generated files are being consumed.
- Desktop entry metadata and icon resolution for launcher/menu entries.
- Font packages and `fontconfig` wiring after Stylix removal.
- App-specific theme integration for Firefox, Kitty, and any apps that do not consume the generated Matugen outputs yet.
- DMS theme refresh behavior when changing wallpaper or colors in the UI.

## Confirmed causes

- Kitty had theme files, but `kitty.conf` never included them.
- GTK had `dank-colors.css`, but no `gtk.css` import file and no dark GTK theme anchor.
- Qt was forced onto `kvantum`, but no Kvantum theme was installed or configured.
- Monaspace fonts were not installed system-wide, so the DMS font selector could not resolve them.
- The DMS launcher icon theme was still set to `System Default`, which likely hid app icons that Papirus can resolve.
- DMS Matugen failed on startup because the merged TOML contained a duplicate `dmskittytabs` template key.
- Qt color writes were landing on read-only symlink targets, so `Apply Qt Colors` could not update the active config files.

## Constraints

- Do not use `current-plan.md` for this investigation.
- Prefer repo-owned, reproducible config over ad hoc local state.
- Keep DMS editable from the UI; do not replace mutable config with read-only state unless writeback still works.

## Working goal

- Restore visible app icons.
- Restore wallpaper-driven app theming across the desktop.
- Ensure Monaspace and Nerd Font variants are installed and selectable in DMS.
- Keep this file updated while debugging so the investigation survives context truncation.
