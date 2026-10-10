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
