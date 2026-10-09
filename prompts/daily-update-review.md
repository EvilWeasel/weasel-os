Du führst den autorisierten täglichen Update-Batch für `/home/evilweasel/weasel-os`
auf `nixy-laptop` aus. Ziel ist ein möglichst vollständig aktueller, funktionierender
Stand: möglichst viele Paket-Pins und alle konfigurierten Kanäle gemeinsam
aktualisieren, breit testen und Fehler selbst eingrenzen und reparieren.
Nach bestandenen Prüfungen und Home-Snapshot ist die Aktivierung autorisiert.
Der native T3-Task startet täglich um 12:00 Uhr Europe/Berlin im vorhandenen
Codex-Harness. Dafür müssen Laptop und T3 verfügbar sein; Standby-Ausführung
oder Fertigstellung bis zu einer Uhrzeit wird nicht versprochen. Ein Termin
rechtfertigt keine ausgelassenen Prüfungen. Arbeite offene Fehler weiter ab.

Lies `AGENTS.md`, `docs/daily-updates.md`, `docs/update-pin-review.md`,
`config/update-pins.json` und relevante `agent-learnings.md`-Einträge.
Nutze vorhandene Memories/Skills; technische Recherche bevorzugt mit Parallel
und offiziellen Quellen. Keine neuen Modellrunner, Zugangsdaten oder Käufe.
Der Factorio Companion bleibt pausiert; starte keine seiner Workloads.

1. Beginne mit `/run/current-system/sw/bin/weasel-update --status` und
   `/run/current-system/sw/bin/weasel-update --review-start`. Alle Helper-Aktionen
   verwenden diesen absoluten Pfad. Lies auch die installierte `--help`, bevor
   du einen neuen Batch-/Worktree-Befehl verwendest. Wenn die benötigte Version
   noch nicht installiert ist, melde das konkrete Bootstrap-Defizit und bereite
   Quellenprüfungen vor; erfinde keinen alternativen Privilegienweg.
   Prüfe Main-Commit, aktive und gebootete Generation, Journale und Worktrees.
   Eine ungeklärte Transaktion blockiert eine weitere Aktivierung. Erhalte Main,
   fremde Änderungen und laufende Apps; kein Reset, Stash, Force-Push oder Reboot.

2. Erzeuge den isolierten Worktree mit
   `/run/current-system/sw/bin/weasel-update --new-batch --mode batch`
   oder ausdrücklich `--mode release-migration`. Der Helper liefert ID, SOURCE
   und die exakte saubere signierte Main-Baseline in seinem privaten Namensraum.
   Nur SOURCE erhält Updates und Reparaturen. Eine neue Main-Baseline verlangt
   erneute Vorbereitung; alte Tests beweisen keinen neuen Kandidaten.

3. Aktualisiere zuerst möglichst viele Quellen zusammen. Aktualisiere mit
   `nix flake update` ausschließlich im Kandidaten alle konfigurierten Inputs
   innerhalb ihrer gewählten Kanäle. Prüfe auch feste Release-/Commit-Pins:
   Ein unveränderter festgeschriebener Ref ist kein Nachweis der Aktualität.
   Aktualisiere alle anwendbaren eigenen Paket-Pins aus offiziellen Quellen,
   einschließlich zusammengehöriger App-/Helper-/nixpkgs-Paare. Ermittle für
   T3, Codex und ChatGPT mit `/run/current-system/sw/bin/weasel-update --discover LANE` exakte Metadaten.
   T3 bleibt im gewählten regulären Nightly-Kanal ohne Maintainer-Preview oder
   stillen Downgrade; verwende die veröffentlichten Hash-/Manifest-Belege.
   Neue URLs, Hashes, Vendor-Locks und Versionswerte müssen zusammenpassen.

4. Prüfe jeden Registry-Eintrag und jeden tatsächlichen `flake.lock`-Knoten,
   einschließlich transitiver Quellen, lokaler Wrapper und neuer Pins.
   Hinterfrage alte Haltegründe und Patches anhand der konkreten neuen Version.
   Bei Transitivem prüfe den aktualisierten Parent und dessen Lock-/Releasewahl;
   follows-Aliasse verweisen auf ihre realen Zielknoten. Erfinde keine aktuelle
   Einzelrecherche, wenn nur der Parent geprüft wurde. Die anfänglichen 37 Pins
   und 70 Nodes sind ein Inventar, keine Obergrenze und keine 37 Update-Sperren.
   Fehlende Spezialadapter verhindern keinen breiten Kandidaten mit den
   gemeinsamen Gates. Ergänze konkrete Funktionsproben bei geändertem Verhalten.

5. Verifiziere den Release-Support. Die Ausgangsbasis 25.11 war seit 2026-06-30
   EOL; 26.05 war bis 2026-12-31 unterstützt. Prüfe die offiziellen Daten erneut.
   Benenne den Wechsel ausdrücklich als `release-migration` und bereite die
   stabile NixOS-/passende Home-Manager-Basis im gleichen geschützten Ablauf vor.
   Ein normaler `batch` wechselt keine Release-Basis still. `system.stateVersion`
   bleibt ein bewusstes Kompatibilitätsdatum. Migration prüft besonders Initrd,
   Kernel/EVDI/NVIDIA, Netzwerk und veränderliche Dienstdaten. Sie bleibt aktive
   Arbeit und wird nicht wegen eines alten Registry-Holds dauerhaft vertagt.
   Prüfe Ersatzbedarf wie Azure Data Studio unter Erhalt vorhandener Einstellungen.

6. Baue und teste den breiten Stand früh. Der Batch-Helfer prüft betroffene
   Host-Evaluationen, vollständigen Flake-Check, echten Laptop-Systembuild,
   Closure-/Paketinventar und die aktuellen T3-, Codex-/ACP- und ChatGPT-Proben
   sowie die Niri-Konfiguration. Verwende die frisch gebauten Programme und
   isolierte Profile. Andere relevante App-Proben können begrenzt parallel
   laufen; keine Modellanfrage ersetzt einen lokalen Funktionsnachweis.
   Ein Prozess-Exit, Versionstext oder historischer Test genügt nicht.

7. Bei Fehlern halte Logs, Commit und betroffene Quellen fest. Nutze vorhandene
   Build-Caches und teile den fehlgeschlagenen Batch in sinnvolle Quellgruppen,
   bis der auslösende Input oder die nötige Reparatur belegt ist. Repariere
   Paket-/Build-Kompatibilität im eigenen Worktree innerhalb der erlaubten
   bestehenden Nix-Konfigurationspfade. Ändere dabei weder privilegierten
   Updater, Sicherheitsregeln, SSH-/Vault-Zugänge noch Credentials oder Gates.
   Keine App-Quellpatches oder lokalen Workarounds blind behalten oder entfernen.
   Falls ein Update noch nicht reparierbar ist, nimm nur den belegten Verursacher
   zurück und behalte die übrigen Updates. Teste den daraus entstehenden exakten
   Gesamtstand erneut. Wiederhole teure Checks bei neuen Änderungen oder Fehlern,
   sonst nutze gültige Cache-Ergebnisse. Kein serieller Komplettlauf pro Paket.

8. Prüfe den Diff des eigenen SOURCE-Worktrees. Er darf vor Vorbereitung dirty
   und uncommitted sein; Signatur und Commit erzeugt der geschützte Helper erst
   nach den bestandenen Tests. Halte Zwischenbefunde privat, ohne Zugangsdaten.
   Übergebe SOURCE mit dem bereits bei Erzeugung gewählten Modus an
   `/run/current-system/sw/bin/weasel-update --prepare-batch SOURCE --mode batch`
   beziehungsweise `--mode release-migration`. Der Helper prüft und baut den
   exakten Stand, ergänzt den deterministischen Learning-Eintrag und signiert
   einen fokussierten direkten Child-Commit. Er liefert ID und frische Belege.
   Nach einem Fehler repariere/bisecte nur den eigenen Kandidaten und bereite
   erneut vor. Kein eigener Commit oder Push ersetzt diese Kandidatenprüfung.

9. Erfasse die Tagesprüfung als private JSON-Datei mit `schema_version: 1`,
   `reviewed_at`, `baseline_commit`, `entries` und vollständigem `lock_nodes`.
   Jeder Pin hat `id`, `current`, `decision`, `reason`, `evidence_urls`,
   `next_review`; jeder Nicht-root-Node hat sein exaktes Baseline-`locked` als
   `current_locked` sowie Entscheidung, Begründung, Belege und nächsten Termin.
   Dokumentiere auch vorgeschlagenen/bestandenen Kandidaten, reparierte Fehler,
   Rest-Holds und tatsächliche Grenzen der Recherche. Unbekannte Gründe und
   Rücknahmen werden spätestens morgen wieder geprüft; keine endlosen Holds.
   `/run/current-system/sw/bin/weasel-update --record-review PRIVATE_JSON` prüft die Abdeckung.
   Review-Schema 1 und Batch-Kandidatenschema 2 sind unterschiedliche Verträge.

10. Reiche nur den vollständig bestandenen Gesamtstand mit
    `/run/current-system/sw/bin/weasel-update --submit CANDIDATE_ID` ein.
    Der unabhängige Root-Helfer prüft Signatur, Quellen/Inodes, Baseline, Gates,
    Speicher/Strom und Snapshot erneut und aktiviert nur die getestete Closure.
    Kein manuelles `nh`/`nixos-rebuild switch` als Ersatz für diese Transaktion.
    Bewahre bei Fehlern Quellen und Diagnose; ungeklärte Journale blockieren
    weitere Aktivierungen. Ein Generationen-Rollback setzt mutable Home nicht
    zurück. Fordere nur wirklich fehlende Befugnisse oder Informationen an.

Berichte die gemeinsame Aktualisierung, echte Reparaturen und Rest-Ausnahmen;
trenne vorbereitet, gebaut, aktiviert und tatsächlich beobachtet. Bei vollständig
unverändertem, unauffälligem Ergebnis bleibe still. Versprich nicht „alles aktuell“,
wenn Quellenrecherche, Tests oder Aktivierung noch offen sind; arbeite sie weiter ab.

Codex-Source-Ausnahme (09.10.2026): Prüfe täglich die offizielle Upstream-Version
und die konkrete Rebase-/Entfernungsoption der Scoped-Cancel-Patches; nächste
Prüfung 10.10.2026. --discover codex meldet einen endlichen held-local-patch
mit candidate: null; --prepare codex ist bis zum geprüften Source-Adapter
abgewiesen. Alle fünf Dateien unter packages/codex-source/, Cargo/V8 und der
separate Rust-1.95-Toolchain-Pin sind ein geprüftes Bundle. Keine npm-Substitution
und kein automatischer Patchverlust. Führe andere geprüfte Batchupdates weiter;
belege unverändertes Bundle, erwartete Source-Derivation je Kandidatenquelle und
die tatsächlichen gebauten Codex-/ACP-Profillinks. Benenne einen erforderlichen
Source-Adapter/Rebase ausdrücklich und mit neuem Reviewdatum.
