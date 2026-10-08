# T3 Code auf nixy-laptop

T3 verwendet die vorhandene Codex-Installation unter
`/etc/profiles/per-user/evilweasel/bin/codex` und deren bestehendes Home
`/home/evilweasel/.codex`. Skills, MCP-Konfiguration und Anmeldung bleiben dort.
Die sechs registrierten Projektordner verweisen auf die vorhandenen Dateien;
Chats wurden nicht importiert. Zwei vorhandene Projekte und sechs vorhandene
T3-Chats blieben erhalten. T3 verwaltet Projektliste und Archivdarstellung selbst;
gemeinsame lokale Codex-Sitzungen belegen keinen vollständigen Sync der
ChatGPT-Seitenleiste oder ihrer App-Connectoren.

Home Manager ergänzt in `.codex/AGENTS.md` einen abgegrenzten Hinweis auf die
vorhandenen Memories und Skills. Eigene Anweisungen außerhalb dieses Blocks
bleiben erhalten. Die Registrierung eines Projekts setzt pausierte Arbeit
nicht fort. Der Factorio Companion bleibt pausiert.

## Deklarative Version und spätere Updates

Die genaue T3-Paketquelle steht in `packages/t3code/source.json` mit
Version, versionierter URL und SHA-256. Seit dem Update vom 8. Oktober 2026
wird der reguläre Nightly-Kanal verwendet; Maintainer-Preview-Testbuilds werden
nicht installiert. Der Launcher deaktiviert den eingebauten App-Updater. Neue Versionen sollen weiterhin über geprüfte deklarative
Kandidaten installiert werden.

Der nächste Auftrag ist in [t3-update-handoff.md](t3-update-handoff.md)
vorbereitet: eine LLM-gestützte tägliche Update-Automatik, die die Gründe von
Pins prüft und überholte Ausnahmen beseitigt. Der LLM trifft die begründete
Updateentscheidung; überprüfbare Build-, Snapshot- und Aktivierungsschritte
sollen die Ausführung absichern.

## Parallel arbeiten

Für neue parallele Threads in diesem T3-Projekt beim Start `Worktree` auswählen. Der
Hauptcheckout `/home/evilweasel/weasel-os` bleibt auf `main` und dient als
gemeinsame Integrationsbasis. Jeder schreibende Task arbeitet auf seiner
eigenen Branch; mehrere Threads im selben lokalen Checkout würden weiterhin
dieselben Dateien und denselben Git-Index verändern. T3s Projektoption für die
Standardumgebung neuer Threads kann diese Auswahl voreinstellen.

T3 stellt dafür native Worktree-Starts und einen Worktree-Handoff für bestehende
Threads bereit. Vor einem Handoff zuerst die aktuelle Bindung prüfen.
Unabhängige Reviews dürfen dieselbe Quelle lesen. Systemaktivierungen bleiben
koordiniert und dürfen sich auch bei getrennten Worktrees nicht überlappen.

Dieser Migrationsauftrag installiert und aktiviert keinen Update-Timer und
ändert weder NixOS-Version noch Flake-Inputs. Ein bisheriger deterministischer
Updaterentwurf ist als unveröffentlichtes Referenzmaterial unter
`/home/evilweasel/.local/state/weasel-os/update-design-20261008` aufgehoben.
Sein Offline-GUI-Gate war nicht erfolgreich: Ein frisches T3-Profil benötigt
externen Clerk-UI-Code. Der Entwurf ist deshalb keine einsatzfertige Automatik.

## Audio

Rena ist in den bestehenden privaten Cartesia-Einstellungen ausgewählt.
Der gemeinsame Skill nutzt Proton Pass und setzt bei jeder Sprachgenerierung
eine Emotion. Deutsche Emotionseffekte sind experimentell.

Der T3-Launcher setzt `WEASEL_T3_CLIENT=1`. Damit legt der Audio-Helfer neue
Dateien unter `.t3-artifacts/audio/` im aktuellen Projekt ab, privat und durch
eine eigene `.gitignore` ausgeschlossen. Der Skill liefert einen Markdown-Link
für T3s native Dateivorschau mit Audioplayer. Explizite Ausgabepfade bleiben
möglich; in Codex bleibt das bisherige globale Audio-Verzeichnis Standard.

## Verifizierter Stand der Migration

Am 8. Oktober 2026 wurden acht Projekte, unveränderte sechs T3-Thread-IDs und
ein bereiter Codex-Provider mit 66 Skills beobachtet. Die Rena-Erklärung wurde
im nativen T3-Audioplayer vollständig geladen und ohne Autoplay geöffnet.
T3 wurde normal ohne Debug-Port mit dem neuen Store-Wrapper gestartet; beide
Wrapperflags sind im Backendprozess angekommen.

MCP-Konfiguration ist gemeinsam verfügbar, aber die Anmeldung und
Funktionsfähigkeit jedes externen Dienstes ist separat zu prüfen. Linear,
Stitch und Supabase meldeten beim lesenden Inventar `not_logged_in`.
`cua_repl` war deaktiviert; `node_repl` verwendet noch ChatGPT-App-Ressourcen.
Der Migrationsbeleg liegt privat unter
`/home/evilweasel/.local/state/weasel-os/t3-migration-20261008.json`.

## Parallel Search in T3

Die vorhandene Parallel-CLI und OAuth-Anmeldung funktionieren. Eine restriktive
T3-/Codex-Netzwerksandbox kann trotzdem `APIConnectionError` verursachen. Der
gemeinsame Kontext beschreibt deshalb den gezielten erneuten Search-/Extract-
Aufruf mit Netzwerkfreigabe und Prüfung des gespeicherten JSON-Ergebnisses.
Home Manager ergänzt dafür die separate Regel
`.codex/rules/parallel-search.rules`; vorhandene Regeln bleiben erhalten.
Die Freigabe gilt ausschließlich für Search und Extract. Sie schließt Login,
Guthabenänderungen, Monitors und Research-Aufträge nicht ein. Regeln werden
beim Start einer Codex-Sitzung geladen; eine bereits laufende restriktive
Sitzung kann weiterhin eine explizite Tool-Eskalation benötigen.
