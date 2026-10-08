# Auftrag für T3: sichere tägliche Updates mit LLM-Prüfung

Du arbeitest im Projekt `/home/evilweasel/weasel-os` auf `nixy-laptop`.
Lies zuerst `AGENTS.md`, relevante Einträge aus `agent-learnings.md`,
`docs/t3-code.md` und die dort referenzierten lokalen Memories. Ermittle dann
den tatsächlichen aktuellen Zustand; übernimm historische Versionsangaben
nicht ungeprüft.

## Ziel und ausdrücklich gewählte Policy

Richte eine tägliche LLM-gestützte Update-Routine für meine deklarative
NixOS-Flake ein. T3 Code ist mein neuer Client; nutze einen tatsächlich
vorhandenen unterstützten Harness oder einen lokal deklarativ eingerichteten
Scheduler. Prüfe zunächst, welche wiederkehrenden Jobs T3/Codex wirklich
unterstützen. Falls T3 keinen Scheduler anbietet, ist beispielsweise ein
systemd-Timer mit dem vorhandenen Codex-Harness möglich. Erfinde keine
T3-Automationsfunktion. Keine Abhängigkeit von einer geöffneten ChatGPT-App.

Meine gewählte Policy lautet: täglich prüfen und bauen; erfolgreiche,
ausreichend geprüfte Updates nach Home-Snapshot automatisch aktivieren.
Dafür ist keine tägliche manuelle Bestätigung nötig. Der frühere Auftrag hat
noch keinen Update-Timer eingerichtet.

Pins haben oft gute Gründe: inkompatible APIs, defekte Builds, Regressionen
oder lokale Patches. Sie sind aber keine unbefristeten Verbote. Ermittle pro
Pin den konkreten Grund aus Code, Historie und Upstream-Issues. Prüfe, ob er
noch gilt, und aktualisiere den Pin oder entferne überholte Workarounds, sobald
ein geprüfter Kandidat sie ersetzt. Unbekannte Gründe verlangen Untersuchung;
sie dürfen nicht dauerhaft stumm jede Aktualisierung verhindern. Dokumentiere
kurz Upstream, Pin-Grund, betroffene Versionen, Prüfnachweis und nächsten
Überprüfungstermin. Prüfe auch stillgelegte oder veraltete Software auf Ersatz.

Erfasse sowohl `flake.lock`-Inputs als auch eigene Paketversionen/Hashes,
insbesondere T3, Codex und ChatGPT. Das langfristige Ziel umfasst das System.
Die bestehende NixOS-Basis wurde bei der Clientmigration absichtlich nicht
geändert. Prüfe vor breiten OS-Updates deren Supportstatus; plane einen
notwendigen Major-/Minor-Wechsel ausdrücklich als eigenen nachvollziehbaren
Migrationsschritt, statt ihn in einen normalen täglichen Paketlauf zu mischen.

## Umsetzung und Sicherheitsgrenzen

Lass den LLM recherchieren, Pin-Gründe bewerten, Kandidaten vorschlagen und
Fehler analysieren. Exakte Quellen, Hashes, Builds, Speicher-/Stromgrenzen,
Snapshots, erlaubte Diffs und Aktivierung müssen überprüfbare deterministische
Schritte absichern. Ein überzeugender LLM-Text allein gilt nicht als bestandener
Test. Kandidaten dürfen erst nach objektiven Prüfungen aktiviert werden.

Bewahre die vorhandenen schmutzigen Worktrees, lokalen OpenRazer-/MIME-Änderungen,
Dateien und Remotehistorie. Kein Reset, Stash oder Force-Push über fremde Arbeit.
Nutze isolierte Kandidaten mit exakten Pins und nachvollziehbarem Diff. Die
Baseline muss den tatsächlich laufenden Systemstand reproduzieren; noch nicht
aktivierte oder parallel geänderte Quellen blockieren den Switch.

Prüfe mindestens Nix-Syntax, die betroffene Host-Evaluation, Paket- und
Laptop-Build sowie passende echte Start-/Funktionsprüfungen. Aktiviere exakt
den gebauten und geprüften Systempfad. Neue Nightlies nicht pauschal als
stabile Updates behandeln. Ein vorhandener unveröffentlichter Updaterentwurf
unter `~/.local/state/weasel-os/update-design-20261008` kann Hinweise liefern,
ist aber nicht fertig: Der vollständig offline isolierte GUI-Test scheiterte
am erforderlichen externen Clerk-UI-Code. Übernimm ihn nicht ungeprüft.

Schütze mutable Home-Daten separat mit Snapper. Prüfe Mounts und tatsächlichen
freien Platz, Netzstrom und Akku. Die bisherige Reserve beträgt 50 GiB vor
Snapshots; für Builds sind zusätzliche Reserven nötig. Begrenze eigene
Kandidaten/Snapshots und bereinige bei Platzdruck nur ausdrücklich dafür
vorgesehene Daten. Keine automatische Löschung persönlicher Daten, Saves,
Modelle oder VM-Disks. Generationen-Rollback ersetzt keinen Home-Snapshot.
Home niemals pauschal automatisch zurücksetzen; das könnte neuere Arbeit
überschreiben. Kein überraschender Reboot oder Schließen geöffneter Apps.

Plane fehlgeschlagene Aktivierung, Stromausfall und gleichzeitige Editor-Saves
als echte Recoveryfälle. Bewahre alte Dateifassungen, Tested-Closure und
Snapshot-ID; blockiere weitere Updates, solange eine Transaktion ungeklärt ist.
Berichte bei erfolgreichem Update, Fehler oder nötiger Entscheidung und bleibe
bei unverändertem, unauffälligem Zustand still.

Nutze die vorhandene Codex-Anmeldung und Skills aus `~/.codex`/`~/.agents`.
Secrets bleiben in Proton Pass bzw. ihren bisherigen privaten Speichern und
gehören weder in Jobprompts noch Nix, Git oder Logs. Gib dem Job nur die
notwendigen Rechte. Prüfe insbesondere, welche Tools im Hintergrund tatsächlich
verfügbar sind. Der Factorio Companion bleibt pausiert.

Setze den geeigneten Ansatz um, teste ihn mit echten Nachweisen und sinnvollen
Fehlerfällen, dokumentiere Bedienung/Anhalten/Rollback und erfülle die
Signatur-/Push-Regeln des Repos. Trenne in deinem Ergebnis klar: vorbereitet,
gebaut, aktiviert und tatsächlich im Betrieb beobachtet. Frage nur nach
Informationen oder zusätzlichen Befugnissen, die dafür wirklich fehlen.
