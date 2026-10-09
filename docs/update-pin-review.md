# Tägliche Updates als gemeinsamer Batch

Ziel ist ein möglichst vollständig aktueller und funktionierender Laptop. Die
Routine aktualisiert möglichst viele eigene Paket-Pins und alle konfigurierten
Flake-Kanäle zusammen in einem isolierten Kandidaten. Sie baut diesen Stand,
prüft ihn breit und grenzt Fehler gezielt ein. Die Registry in
`config/update-pins.json` liefert Gründe und Prüfschwerpunkte; sie ist kein
Katalog dauerhaft gesperrter Updates. Die anfänglichen 37 Einträge und 70
Lock-Knoten begrenzen den Auftrag nicht.

Der native T3-Task startet täglich um 12:00 Uhr Europe/Berlin mit dem vorhandenen
Codex-Harness. Laptop und T3 müssen verfügbar sein. Eine Ausführung während
Standby oder eine Fertigstellung bis zu einer Uhrzeit ist dadurch nicht
belegt. Das Ziel für den nächsten Mittag wird durch tatsächliche Vorbereitung,
Reparaturen und Aktivierung verfolgt; ein Termin ersetzt keine bestandenen
Prüfungen. [Der Task-Prompt](../prompts/daily-update-review.md) beschreibt den
Ablauf; [daily-updates.md](daily-updates.md) beschreibt Installation und Recovery.

## Gemeinsam aktualisieren, Fehler zuordnen

1. `--status` und `--review-start` liefern aktuellen Main-Commit, Systemzustand,
   Registry und sämtliche aufgelösten Lock-Knoten. Eine aktive oder ungeklärte
   Transaktion blockiert eine weitere Aktivierung. Der eigene Kandidat beginnt
   auf exakt dieser sauberen Baseline; Main und andere Worktrees bleiben erhalten.
2. Alle konfigurierten Inputs werden zunächst gemeinsam im Kandidaten
   aktualisiert. Festgeschriebene Releases oder Commits werden zusätzlich mit
   aktuellem Upstream abgeglichen: `nix flake update` kann solche Pins unverändert
   lassen. Eigene Pakete, Vendor-Locks und zusammengehörige App-/Helper-Paare
   gehören in denselben Batch. Bereits erfolgte Downloads und Builds werden
   wiederverwendet, sofern ihr exakter Quellenstand weiterhin passt.
3. Der breite Stand wird früh evaluiert und gebaut. Bei einem Fehler werden
   Logs und Quellenstand gesichert, zusammenhängende Updategruppen eingegrenzt
   und nötige Paket-/Build-Kompatibilitätsreparaturen im eigenen Worktree
   vorgenommen. Erlaubte Nix-Konfigurationspfade legt der geschützte Helfer fest.
   Privilegierter Updater, Sicherheitsregeln, SSH-/Vault-Zugänge und Credentials
   werden durch einen Paket-Batch nicht verändert.
4. Ein nicht reparierbares Update erhält einen belegten, befristeten Hold. Nur
   sein nachgewiesener Verursacher wird zurückgenommen; die übrigen Updates
   bleiben im Kandidaten. Der resultierende Gesamtstand wird erneut geprüft.
   Neue Änderungen oder Fehler verlangen neue Belege. Ein Komplettlauf für
   jedes einzelne Paket ist nicht der normale Ablauf.

Spezialisierte Adapter beschreiben zusätzliche Prüfmöglichkeiten. Ein fehlender
Adapter sperrt nicht automatisch den gesamten Input oder den Batch. Die
gemeinsamen Gates und konkrete ergänzende Proben müssen für die Änderung
aussagekräftig sein. Wenn ein bestimmtes Verhalten noch nicht geprüft werden
kann, wird genau diese Grenze festgehalten und bearbeitet. Alte Gründe und
Workarounds werden am konkreten neuen Stand überprüft.

## Vorbereitung und unabhängige Aktivierung

Der Helper erzeugt den eigenen SOURCE-Worktree unter
`STATE/candidates/<ID>/source` mit Branch `weasel-update-<ID>` auf der exakten
sauberen signierten Main-Baseline. Nur dieser private Namensraum wird als
Batch-Quelle akzeptiert. Updates und Reparaturen dürfen dort vor Vorbereitung
noch dirty und uncommitted sein. Der Helper erzeugt nach bestandenen Prüfungen
selbst einen fokussierten signierten direkten Child-Commit und den
deterministischen Learning-Eintrag. Keine Zugangsdaten gehören in Git.

```sh
/run/current-system/sw/bin/weasel-update --new-batch --mode batch
/run/current-system/sw/bin/weasel-update --prepare-batch SOURCE --mode batch
/run/current-system/sw/bin/weasel-update --submit CANDIDATE_ID
```

Erzeugung und Vorbereitung verwenden denselben Modus. Die Ausgabe von
`--new-batch` liefert SOURCE, ID und Baseline. Die installierte `--help` ist
maßgeblich; fehlende Helper-Funktionen werden nicht durch einen Privilegienweg
außerhalb der Routine ersetzt. Nach einem Fehler kann der eigene Kandidat
gezielt repariert und erneut vorbereitet werden.

Der Batch-Helfer prüft betroffene Host-Evaluationen, den vollständigen
Flake-Check, den tatsächlichen Laptop-Systembuild und dessen Closure- und
Paketinventar. Hinzu kommen die aktuellen T3-, Codex-/ACP- und ChatGPT-Proben
sowie die Niri-Konfigurationsprüfung. Die Programme stammen aus dem konkreten
Build und benutzen isolierte Profile. Weitere relevante App-Proben können
begrenzt parallel laufen. Ein Versionstext, Prozess-Exit, Screenshot oder
historischer Test allein beweist das Verhalten des Kandidaten nicht.

`--prepare-batch` liefert die Kandidaten-ID und Prüfbelege. Der unabhängige
Root-Helfer prüft bei Submission Signatur, Quellen und Inodes, unveränderte
Baseline, Artefakte, Gates, Speicher, Strom und Home-Snapshot erneut. Er
aktiviert ausschließlich die getestete Closure über denselben geschützten
Inbox-/Journal-Ablauf. Ein Quell- oder Baseline-Wechsel verlangt neue Prüfung.
Eine ungeklärte Transaktion blockiert weitere Aktivierungen. Ein
Generationen-Rollback ist keine Rücksetzung veränderlicher Home-Daten.

Das Batch-Kandidatenschema ist Version 2. Die weiterhin vorhandenen einzelnen
T3-/Codex-/ChatGPT-Lanes behalten ihren engeren Metadatenvertrag; ihre
Version-/Hash-Beschränkung ist keine Beschränkung des breiten Batch-Vertrags.

## Vollständige Tagesprüfung und Rest-Ausnahmen

Die private Review-Datei verwendet weiterhin `schema_version: 1`,
`reviewed_at`, `baseline_commit`, `entries` und `lock_nodes`. Jeder Pin enthält
`id`, `current`, `decision`, `reason`, `evidence_urls` und `next_review`.
Jeder Nicht-root-Lock-Knoten enthält das exakte Baseline-`locked`-Objekt als
`current_locked` sowie Entscheidung, Grund, Belege und nächsten Termin.
Optionale Felder halten Kandidatenversionen, Reparaturen, bestandene Checks,
Rest-Holds und Untersuchungsgrenzen fest.

```sh
/run/current-system/sw/bin/weasel-update --record-review PRIVATE_JSON
```

Die Abdeckung folgt den tatsächlichen Quellen und wächst mit neuen Pins.
Follows-Aliasse besitzen keinen eigenen Lock-Hash; ihre realen Zielknoten und
verantwortlichen Parent-Inputs werden genannt. Ein aktueller Parent kann ältere
transitive Versionen absichtlich festlegen. Das wird als Parent-Wahl mit ihren
Belegen dokumentiert, nicht als ungeprüfte Behauptung, jeder transitive Pin sei
die neueste Einzelversion. Sicherheits- und Kompatibilitätsfragen bleiben aktiv.

`hold-with-evidence` braucht einen konkreten Fehler oder weiterhin belegten
Grund. `investigate` und zurückgenommene Updates werden spätestens morgen
wieder untersucht. `adapter-needed` beschreibt benötigte zusätzliche Prüfung
und keine dauerhafte Versionssperre. Der Abschlussbericht nennt aktualisierte
Gruppen, echte Reparaturen und verbleibende Ausnahmen und trennt vorbereitet,
gebaut, aktiviert und tatsächlich beobachtet.

## Exakte Artefakt-Discovery

`--discover t3|codex|chatgpt` schreibt private Metadaten und ändert Main nicht.
T3 folgt dem gewählten regulären Nightly-Kanal; Maintainer-Previews und stille
Downgrades sind ausgeschlossen. Der Discovery-Vertrag bleibt Version 1 mit
`lane`, `channel`, `current`, `candidate`, `evidence`, `checked_at`, `status`
und `source_files`. Quell-Pins für T3 und ChatGPT enthalten exakt `version`, versionierte `url`
und SHA-256-SRI-`hash`.

- T3 prüft offizielle Releases und Asset-Digests. Nightly-`SHA256SUMS` enthält
  derzeit CLI-Archive; das Desktop-Manifest `nightly-linux.yml` liefert daneben
  Version, AppImage-Datei, Größe und SHA-512. Neue Kandidatenbytes müssen die
  veröffentlichten Desktop-Hashes erfüllen. Drafts und Kanalabweichungen stoppen
  die Discovery; dieselbe Version mit verändertem Hash ist ein Fehler.
- Codex verwendet einen typisierten pinned-source-Pin mit Version, Commit,
  exakter Codeload-URL und rekursivem Fetchzip-NAR-Hash. Sein Bundle enthält
  default.nix, toolchain.nix, beide Scoped-Cancel-Patches und README.md.
  Die Registry erfasst zusätzlich Cargo-Hash, das gepaarte V8-Archiv/Binding und
  den außerhalb von flake.lock eingefrorenen Nixpkgs/Rust-1.95-Pin. Offizielles
  npm-latest ist allein ein Versionshinweis: Discovery gibt held-local-patch,
  candidate: null und den nächsten Review am Folgetag zurück. Source-/Patch-
  Änderungen benötigen einen geprüften Source-Adapter und einen Patch-Rebase;
  npm-Downloads ersetzen den Source-Build nicht. Andere Batchupdates bleiben
  möglich, wenn Bundle und tatsächliche Codex/ACP-Profilbindung geprüft bestehen.
  Der nächste datierte Rebase-Review ist am 10.10.2026 fällig. Historische
  npm-Proben bleiben ausdrücklich historische Belege.
- ChatGPT prüft den begrenzten RPM-Header des offiziellen `latest`-Endpunkts,
  dann die konkrete versionierte RPM-Identität und den vollständig berechneten
  Hash. Payload und RPM-Scriptlets werden dabei nicht ausgeführt.

Unveränderte Codex-/ChatGPT-Payloads werden nicht täglich neu heruntergeladen;
der Beleg nennt diese Grenze. Neue Kandidaten werden vollständig geprüft. Ein
später neueres `latest` macht einen korrekt getesteten exakten Kandidaten nicht
rückwirkend ungültig. Downloads haben feste HTTPS-Hosts, kontrollierte Redirects,
Größen- und Zeitlimits; vorhandene Ausgabedateien werden nicht überschrieben.
Credentials und Benutzerprofile gehören weder in die Quellen noch in Belege.

## Benannte Release-Migration und alte Workarounds

Ein Wechsel der stabilen NixOS- und passenden Home-Manager-Basis wird ausdrücklich
als `release-migration` vorbereitet. Er nutzt denselben geschützten Batch- und
Aktivierungsablauf; ein normaler `batch` wechselt die Release-Basis nicht still.
Andere anwendbare Updates können mit dieser benannten Migration zusammen geprüft
werden. `system.stateVersion` bleibt ein bewusstes Kompatibilitätsdatum.

```sh
/run/current-system/sw/bin/weasel-update --new-batch --mode release-migration
/run/current-system/sw/bin/weasel-update --prepare-batch SOURCE --mode release-migration
/run/current-system/sw/bin/weasel-update --submit CANDIDATE_ID
```

Die Ausgangsbasis 25.11 ist seit 2026-06-30 außerhalb des Supports; 26.05 wird
bis 2026-12-31 unterstützt. Diese Daten wurden am 2026-10-08 offiziell geprüft
und müssen vor Migration erneut verifiziert werden. Initrd, Kernel/EVDI/NVIDIA,
Netzwerk und veränderliche Dienstdaten brauchen passende konkrete Belege.
[NixOS-Releaseankündigung](https://nixos.org/blog/announcements/2026/nixos-2605/)

Die 6.18-Kernelwahl entstand beim EVDI-1.14.12-Buildfehler gegen Kernel 7.0.3.
Neuere EVDI-Releases nennen vorläufigen Kernel-7-Support. Das verlangt neue
Kandidatenprüfung; physische Hotplug-, Suspend- und NVIDIA-Funktion wird dadurch
noch nicht belegt. [EVDI-Releases](https://github.com/DisplayLink/evdi/releases)

NetBird #7331 ist als `not_planned` geschlossen und beschreibt einen Kernel-Fehler.
`NB_DISABLE_EBPF_WG_PROXY=true` entfällt erst mit Nachweis des genauen Kernel-Fixes
und bestandener Netzwerkprüfung. [NetBird-Issue](https://github.com/netbirdio/netbird/issues/7331)

Azure Data Studio ist seit 2026-02-28 stillgelegt. Nutzung und Ersatz durch
VS Code mit MSSQL-Erweiterung werden unter Erhalt vorhandener Einstellungen
geprüft. [Microsoft-Migrationshinweise](https://learn.microsoft.com/en-us/sql/tools/whats-happening-azure-data-studio?view=sql-server-ver17)

Die historische ew-cloud/Fontconfig-Störung wurde bei Einrichtung nicht erneut
beobachtet; der vollständige Flake-Check bestand. Ein neuer Fehler braucht neue
Belege. Dormante Helium-, Frosty- und Screenpipe-Derivationen werden auf tatsächliche
Nutzung geprüft. Daraus startet keine Aufnahme, Spielsession oder pausierte
Factorio-Companion-Arbeit automatisch.
