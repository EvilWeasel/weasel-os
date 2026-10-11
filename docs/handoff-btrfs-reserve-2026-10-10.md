# Btrfs-Reserve: abgestimmte Übergabe

Stand: 10. Oktober 2026. Task-Worktree:
`/home/evilweasel/.t3/worktrees/weasel-os/t3-4c234a3d`, Branch
`t3/btrfs-headroom-warning`, Ausgangsbasis `98dc94fa45244e0d5b7e849be899a381b8ea215f`.

## Tatsächlich ausgeführt

- Nach ausdrücklicher Alarm-/Fix-Anweisung begrenzte Daten-Balance: leere
  Bereiche ergaben keinen Gewinn; vier schwach belegte Bereiche und dreimal je
  acht weitere Bereiche schufen 28 GiB unzugewiesene Reserve. Keine Löschung,
  Metadaten-Balance oder Profil-Konvertierung. Gerätefehler null, keine aktive
  Balance, ursprünglicher Wächter `ok:true`.
- In Abstimmung mit dem Update-Thread ausschließlich zwei sichtbare Launcher
  `~/.local/share/applications/weasel-t3code.desktop` und `weasel-mtcode.desktop`
  angelegt, ohne MIME-Typen. Desktop-Datei-Validator bestanden. Originale und
  MIME-Identitäten beim Abschluss unverändert. Keine GUI-Probe, App-/DMS-
  Neustarts, Cache-Aktualisierung, Mikrofon- oder physische Eingabe.
- Update-Thread unterbrach selbst seinen exakten Cloud-Build zur Entlastung.
  Der Cloud-Build ist unterbrochen, nicht bestanden; dessen fertig gebauter
  Laptop bleibt als eigener, unabhängiger Nachweis erhalten.

## Vorbereitete Änderung

`modules/btrfs-reserve.nix` und `programs/storage-health.nix` liefern begrenzte
Reservepflege und Mess-/Benachrichtigungsdienste. `scripts/weasel-btrfs-health.py`
trennt tatsächliche Belegung, Reservierungen und freien Geräteplatz. Der alte,
bekannte Minuten-Timer wird erst bei Aktivierung stillgelegt; pausierte
Factorio-Companion-Quelldateien bleiben unverändert.

`weasel-snapshot-excludes.py` inventarisiert eindeutig erkannte, nicht
Git-verfolgte Buildverzeichnisse. Eine explizite Migration erhält deren Pfad,
prüft offene Zugriffe einschließlich Projekt-cwd, aktive Builds, Update-Locks,
Reserve und Datenintegrität. Noch **keine Migration ausgeführt oder live
qualifiziert**. Der Helfer ist lokal durch Sicherheitsprüfungen und als
gebautes Paket geprüft; sein tatsächlicher Kopier-/Subvolume-Workflow braucht
die erste kontrollierte Pilotmigration nach Freigabe.

Inventar: `.t3-artifacts/storage/2026-10-10/project-snapshot-excludes.json`,
24 Kandidaten, nominell 12.37 GiB. Das Inventar ist privat/ignoriert und vor der
Migration neu zu erstellen. Größen enthalten geteilte Btrfs-Blöcke und sind
keine Prognose sofort frei werdender Bytes. Testnachweise und Saves sind keine
Caches. Ganze Projekte, `.local/state`, `.t3` oder `Documents` werden nicht
pauschal ausgenommen. Eine Neuorganisation der Quellpfade ist nicht erforderlich.

## Tatsächliche Validierung

- Sieben Sicherheitsprüfungen, Python AST, Nix parse/nixfmt, diff check.
- Laptop und Desktop mit `nix eval --no-write-lock-file ...drvPath` geprüft;
  vollständiger `nix flake check --no-build --no-write-lock-file` bestanden.
- Zwei Hosts seriell unter einer reservierten Validierungsphase gebaut, jeweils
  `--no-write-lock-file --max-jobs 1 --cores 8`. RAM-/Reserve-Wächter mit
  identitätsgebundenem eigenem SIGINT; kein Interrupt nötig, Reserve 28 GiB.
- Finaler r2 Laptop: Exit 0, 47.79s,
  `/nix/store/ds466qdxk4fjzkrxsl9vl8lk9whkl849-nixos-system-nixy-laptop-25.11.20260501.26ef669`,
  registrierter Deriver `z64asypv7622bsdi4qgvrdnnxpbsgiwk`.
- Desktop: Exit 0, 20.10s, vorhandene Closure
  `/nix/store/z64i98g181r7xwgrn8b4dvqzr9zg4xjq-nixos-system-nixy-desktop-25.11.20260501.26ef669`,
  registrierter Deriver `mksdll1na6fc3l5lz5f563xc4w8p6hf3`.
- Belege: `/tmp/weasel-storage-validation-20261010-r2/receipt.json`;
  getesteter Code-Diff SHA256
  `d111e0f624914d325c9c233dbf1dba0162e8f56388e2aebc54a750fa98754b6b`.
  Diese Übergabe und der abschließende Log-Eintrag kamen anschließend hinzu;
  die getesteten Nix-/Python-Dateien bleiben unverändert.

## Noch auszuführen, in dieser Reihenfolge

1. Explizites Integrationsfenster mit Thread `bfff85a1-86b8-452d-bf31-ca6274b921a3`
   vereinbaren. Main/Kandidaten bleiben bis dahin unverändert. Kein fremdes
   Reset/Stash, kein paralleler Aktivierungsvorgang. Bei neuer Main-Basis frisch
   integrieren und die resultierende Konfiguration neu validieren.
2. Geschützte Aktivierung koordinieren. Die jetzt gebaute 25.11-Konfiguration
   nicht über eine später aktivierte 26.05-Generation zurückschalten.
3. Neuer Messdienst/Wartung/Benachrichtigung prüfen; alter Timer gezielt
   deaktiviert, Originaldateien erhalten. Reservepflege erstmals kontrolliert
   prüfen, bevor der regelmäßige Timer als wirksam gilt.
4. Aktuelle Projekt-Inventur erstellen. Einen kleinen, sicher ruhenden
   Kandidaten pilotieren. Originalpfad, bytes/Rechte/Hardlinks/Links, eigene
   Subvolume-Grenze sowie Ausschluss aus einem separaten Testsnapshot unabhängig
   nachweisen. Kein Projekt- oder Game-Start erforderlich.
5. Erst nach bestandenem Piloten weitere Kandidaten einzeln migrieren. Aktive
   Projekte/Tools zurückstellen. Keine pauschalen `build/dist/bin/obj`-Ausschlüsse,
   keine Löschung von Build-Caches. Fehlerjournale und Originale erhalten.
6. Normale Snapshot-Aufbewahrung später prüfen; alte Snapshots halten ihre
   früheren Cache-Blöcke bis zu ihrem regulären Ablauf. Gesamtbelegung erneut
   messen; das Ziel unter 80 Prozent ist noch nicht erreicht.

Die Validierungsreservierung ist ausdrücklich freigegeben. Es läuft kein eigener
Compiler mehr, es wurde nichts aktiviert. Update-/Storage-Arbeit ist damit
quellenmäßig vorbereitet und übergabefähig, aber noch nicht vollständig live
abgeschlossen.

## Fortschreibung am 11. Oktober nach dem Release-Update

Das 26.05-Update ist tatsächlich aktiviert; freigegebene neue Basis ist
`02b5d10d0d5058952d348bc5755e49dc6ca739c7`. Der alte 53d01c24-Checkpoint
und alle alten Belege bleiben historisch erhalten. Der eigene Branch führt
beide Quellen zusammen; die damaligen 25.11-Closures werden nicht aktiviert.
Reservepflege beginnt nun unter 40 GiB Geräte-Reserve und stoppt ab 50 GiB;
alle Run-/Bootstrap-/Manual-Journale werden auf offene Transaktionen geprüft.

Frischer r1 Flake-Check Exit0/40.82s und Laptop26-Build Exit0/14.27s,
Closure `93qir7szbqmm4yg96fwwk4s3rb8bqyyi`. Der Desktop-Build wurde nach
unerwarteter NVIDIA-Kernelmodul-Kompilierung exakt selbst unterbrochen:
Exit1/67.66s, kein PASS. Alle Storage-Imports sind laptop-only; der Desktop-
Deriver `r83zjdjqa8qkrym96f70lslk050hc1ma` ist exakt derselbe wie auf
signierter Main02b5. Keine weitere Desktop-Kompilierung erforderlich.

Sieben neuere Main-Laufzeitdateien sind privat unter
`/tmp/weasel-storage26-runtime-preservation-20261011` mit Hash/Inode/mtime
bewahrt. T3-Liste bestätigt Update-/MT-Threads beendet; keine fremde aktive
Quellarbeit beobachtet. Vor Integration müssen die aktuellen Bytes separat
erhalten sein. Projektmigrationen bleiben ausdrücklich deferred; die Freigabe
der Quellarbeit ist keine implizite Freigabe des Piloten.

Finaler Lauf 26-r2 mit den erhaltenen sieben Laufzeitdateien: Flake-Check
Exit0/39.49s, Laptop Exit0/16.63s mit derselben Closure93qir7, isolierter
Niri-Parser ohne GUI Exit0/3.32s. Beleg
`/tmp/weasel-storage-validation-20261011-26-r2/receipt.json`.
Reservierung freigegeben; historische unterbrochene Desktop-Prüfung bleibt
FAILED. Desktop-drvPath unverändert. Projektmigrationen weiterhin deferred.

Main-Fast-forward wurde durch automatische Freigabeprüfung abgewiesen:
unklare aktuelle Freigabe nach früherer Main-Sperre. Keine Umgehung,
keine Main-Integration oder Aktivierung. Fertiger Aufgabenbranch bereit
für explizite Freigabe der Integration; Live-Dateien unverändert erhalten.


## Abschluss am 11. Oktober 2026 · tatsächlich live

Die spätere ausdrückliche Nutzerfreigabe umfasst Integration, Aktivierung und
Projekt-Ausschlüsse; die vorherigen Sperren/Abweisungen oben sind historische
Belege. Signierte Storage-Quelle `1b1f3d32` ist integriert und normal gepusht.
Aktive und ausgewählte Laptop26-Closure ist `0qrbxxkxwda0pqyf48lqavj1c46v3asr`.
Eigene Root-Aktivierung r5 endete Exit0/3.53s, Journal `phase=complete`, Snapshot27.
Die vorherigen eigenen Fehlversuche sind getrennt erhalten; der relevante
Busy-Lock-Fehler des Wartungsdienstes wurde eng korrigiert (zehn Tests PASS und
betroffener Laptop-Build PASS). Keine Desktop-Aktivierung, keine GUI-Eingabe.

Alle 24 inventarisierten, ruhenden Cache-/Build-Verzeichnisse wurden mit
Pfaderhalt zu verschachtelten Subvolumes migriert: 20 `node_modules` und vier
Rust-`target`-Verzeichnisse, nominell 13.280.923.648 Bytes / 12,37 GiB. Die
serielle Hauptmigration dauerte 91,54s; der vorherige Pilot zusätzlich 0,82s.
Jede Migration hat zwei Prüfsummen-/Metadatenvergleiche und ein privates
Phasenjournal. Der Pilot wurde unabhängig gegen Recovery-Snapshot27 verglichen
(Rsync Exit0, keine Unterschiede). Abschließender echter Snapshot29: alle24
Caches als leere Platzhalter, Live-Caches nicht leer, Projektmanifest vorhanden,
Snapshot read-only. Eigene temporäre Testsnapshots28/29 nach Beweissicherung
gezielt entfernt; Recovery26/27 und sämtliche früheren Update-Belege erhalten.

Privater Beleg: `/tmp/weasel-storage26-final-exclusion-proof-20261011.json`;
Batch `/tmp/weasel-storage26-migration-batch-20261011/receipt.json`;
Aktivierung `/tmp/weasel-storage26-activation-20261011/receipt.json`.
Root-Health/Reserve-Dienste Exit0, alle drei neuen Timer aktiv, bekannter alter
Minuten-Alarmtimer deaktiviert. Geräte-Reserve47GiB, Gesamtfreiraum rund129GiB
(Reserve darin enthalten), keine aktive Balance und alle Gerätefehlerzähler0.
Alte Snapshots behalten ihre alten Cache-Blöcke bis zur regulären Aufbewahrung;
die Migration ist keine Löschung von 12GiB Nutzdaten. Normales Cache-Löschen als
UID1000 wurde separat mit einem Wegwerf-Subvolume erfolgreich geprüft.

Alle sieben MIME-/DMS-/Farbdateien haben weiterhin dieselben Bytes und Inodes;
MIME zusätzlich identische mtime. Drei identische Farbdateien erhielten während
des Rollouts neuere mtimes. Die Launcher-Einträge werden jetzt dauerhaft von
Home Manager bereitgestellt; keine GUI-Prüfung oder App-Neustarts durchgeführt.
Die in AGENTS.md ergänzten Regeln für fokussierte Iteration vermeiden redundante
Prüfrunden und trennen Upgrader-Entwicklung vom eigentlichen Laptop-Upgrade.
