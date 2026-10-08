# Tägliche geprüfte Updates

Die tägliche T3-Aufgabe prüft mit dem vorhandenen Codex-Harness alle bekannten
Pins und aktuellen Flake-Inputs. Sie bereitet Kandidaten in eigenen Worktrees
vor. Ein fest installierter Root-Dienst prüft die Quellen und Artefakte erneut,
erstellt einen Home-Snapshot und aktiviert ausschließlich den geprüften
Systempfad. Der Auftrag erlaubt diese Aktivierung ohne tägliche Rückfrage.

## Betriebszustand und Abdeckung

Die Software wird durch `modules/daily-updates.nix` auf `nixy-laptop` installiert.
Vor dem einmaligen Bootstrap fehlen der laufenden Generation der Helper und
Root-Dienst. `weasel-update --status` zeigt danach den öffentlichen Zustand;
ein vorbereitetes oder gebautes Ergebnis beweist noch keine Aktivierung.
T3s Schedulerstatus `succeeded` bestätigt ausschließlich die Zustellung.
Eine tatsächlich ausgeführte Tagesprüfung hat einen privaten Review-Beleg;
eine abgeschlossene Aktivierung zusätzlich ein Root-Journal mit `complete`.

Die Einrichtung am 2026-10-08 prüfte reale Kandidaten Codex 0.162.0 und
ChatGPT 26.1002.52244 einschließlich vollständiger einzelner Laptop-Builds,
nativer/GUI-Gates und struktureller Closure-Vergleiche. Ihre Pin-Commits sind
signiert. Der vorhandene T3-Nightly-Stand bestand Start und eine tatsächliche
synthetische Migration von stabilem 0.0.45 (54 Migrationen) auf die Nightly
(60), ohne persönliche Daten zu verwenden. Es gab keinen neueren T3-Kandidaten.
Diese Befunde belegen noch keinen Root-Switch oder täglichen Hintergrundlauf.
Der manuelle Scheduler-Test wurde durch T3s Capability-Prüfung in `runtime auto`
abgewiesen; kein Ersatz-Dispatch umgeht diese Grenze. Der dauerhaft laufende
Proton-SSH-Benutzerdienst ist davon unabhängig bereits beobachtet.

Der native T3-Task heißt „Weasel OS: tägliche geprüfte Updates“, ist an diesen
Update-Thread gebunden und verwendet `prompts/daily-update-review.md`. Seine
Uhrzeit ist 14:00 in der Zeitzone des laufenden T3-Prozesses. T3 muss laufen;
der Scheduler ist kein Dienst auf einem ausgeschalteten Laptop. Eine geöffnete
ChatGPT-App ist nicht erforderlich. Die konkrete Task-ID und der beobachtete
nächste Termin gehören in den Einrichtungsbeleg, statt einer angenommenen
Zeitzone. Nach Bootstrap wird ein echter Hintergrundlauf separat beobachtet.

`config/update-pins.json` erfasst zunächst 37 Pins und 70 aufgelöste Lock-Nodes;
der virtuelle Root-Knoten kommt im geladenen Graphen zusätzlich hinzu. Das ist
keine Obergrenze: Der Tageslauf liest den aktuellen Quellstand und ergänzt
neue Pins. Alle Einträge werden recherchiert und mit endlichem nächsten
Prüftermin dokumentiert. `--record-review` verlangt zusätzlich zu jedem Pin
einen expliziten Befund für jeden tatsächlichen transitiven Lock-Knoten,
gebunden an den aktuellen Main-Commit und dessen genaue `locked`-Daten.
Fehlende Nodes, veraltete Revisionen und Quellenänderungen während der
Aufzeichnung blockieren den Beleg. Ein mit `investigate` erfasster Knoten
meldet offen fehlende Upstream-Prüfung und wird spätestens morgen untersucht.
**Automatische Aktivierung ist derzeit auf drei
Adapter begrenzt:** T3-Quell-JSON sowie Version und Quellhash der bestehenden
Codex-/ChatGPT-Pakete. Packaging-Code, Patches, weitere Pakete und Flake-Inputs
können diese Adapter nicht verändern. Andere Kandidaten erhalten eigene
Builds und geprüfte Adapter; ein fehlender Adapter wird ausdrücklich gemeldet.

NixOS 25.11 ist außerhalb des Supports. Der Wechsel zu einer unterstützten
stabilen Basis gehört zusammen mit Home Manager in eine eigene Migration.
`system.stateVersion` wird dabei nicht automatisch geändert. Siehe
[Pin-Prüfung und offizielle Belege](update-pin-review.md).

## Bedienung

Der Modellprozess arbeitet als `evilweasel`. Die Codex-Regel erlaubt nur die
fest installierte Helper-Datei mit den vorgesehenen Aktionen. Sie erlaubt
keine freien Root-Kommandos. Secrets verbleiben in vorhandenen privaten
Stores und gelangen weder in Nix noch Git oder Review-Dateien.

```sh
/run/current-system/sw/bin/weasel-update --status
/run/current-system/sw/bin/weasel-update --review-start
/run/current-system/sw/bin/weasel-update --record-review /absoluter/pfad/review.json
/run/current-system/sw/bin/weasel-update --discover codex
/run/current-system/sw/bin/weasel-update --prepare codex --metadata /ausgabe/metadata.json
/run/current-system/sw/bin/weasel-update --submit 20261008T120000Z-0123abcd
```

Die letzte ID ist ein Formatbeispiel. Verwende die tatsächlich ausgegebene ID.
Der Helper erzeugt seinen eigenen Kandidaten unter
`~/.local/state/weasel-updates/candidates/ID/source` und einen signierten
Branch `weasel-update-ID`. Eigene Reviews und Metadaten liegen unter demselben
privaten Zustand. `--output` schreibt ausschließlich neue Receipt-Dateien im
Update-Zustand oder `/tmp`; bestehende Dateien und Symlink-Eltern werden
abgelehnt. `--state /tmp/weasel-updates-NAME` erlaubt private Testzustände.
Der festgelegte Integrationscheckout kann nicht durch einen anderen ersetzt
werden. Keine Kandidatenprüfungen schreiben in Main.

`--submit` veröffentlicht exklusiv eine vollständig geschriebene Anfrage in
`/var/lib/weasel-updates-inbox/request.json`. Sie enthält nur vollständige
Commit-IDs, einen Update-Branch, ID und Baseline-Systempfad. Eine vorhandene
Anfrage bleibt erhalten. `weasel-update-activate.path` startet darauf den
festen Dienst `weasel-update-activate.service`.

## Prüfungen und Aktivierung

Vorbereitung und unabhängiger Submitter verlangen sauberes Main, kanonisches
Origin, übereinstimmenden Remote-Stand und eine Baseline, die die tatsächlich
laufende und als Bootprofil ausgewählte Generation reproduziert. Änderungen
an Dateien, Index, Branch, Remote oder System während der Prüfung blockieren
Integration bzw. Aktivierung. Auch per `assume-unchanged` versteckte
Editoränderungen werden anhand der Dateiinhalte erkannt.

Der Root-Verifier verlangt einen direkten signierten Nachfolger der Baseline
vom eingerichteten Signierschlüssel und prüft Git-Objekte anhand ihrer
Inhalts-Hashes. Der Diff darf nur die unterstützten Pins und den unabhängig
erzeugten Zusatz im Lernlog enthalten. Er friert die geprüften Quellen in
schreibgeschützten Root-Verzeichnissen ein. Nix-Evaluationen, Builds,
Netzwerk-Discovery und App-Prüfungen laufen weiterhin als normaler Benutzer.

Jeder Kandidat braucht Nix-Syntax, Evaluation aller betroffenen Hosts,
Paket- und vollständigen Laptop-Build. T3 betrifft zusätzlich `michapc` und
`michapc-debug`. Die Closure-Prüfung erlaubt App-Abhängigkeiten und paarweise
verglichene erzeugte Dateien mit ansonsten identischen Inhalten, Modi und
Linkzielen. Ein bloßer Namens-Whitelist-Treffer beweist keine Gleichheit.

Die realen Funktions-Gates verwenden leere Profile in privaten Benutzer-,
PID- und Netzwerk-Namespaces. Sie lesen keine persönlichen App-Daten und
stellen keine Modellanfragen. Codex startet den CLI- und app-server-Handshake
sowie den an den Kandidaten gebundenen ACP-Adapter. ChatGPT prüft Renderer,
Verpackung des nativen Watchers und Audio-Bibliotheken. T3 prüft Renderer,
Backend und eine synthetische Migration von der alten zur neuen Datenbank
mit Projekt, Thread, Nachricht und deaktiviertem Zeitplan. Nur T3s öffentlicher
Clerk-Frontend-Host ist über einen begrenzten Proxy erreichbar; andere
Internetziele bleiben gesperrt. Ein leerer Recovery-Screen besteht nicht.
Software-Rendering auf Xvfb beweist keine GPU-/Niri-/Overlay-Kompatibilität.

Vor Builds sind mindestens 65 GiB verfügbar; vor Snapshot und Aktivierung
mindestens 50 GiB auf Home-, Store- und Zustandsdateisystemen. Netzstrom und
mindestens 30 Prozent Akku sind erforderlich. Der Snapshot muss tatsächlich
ein schreibgeschütztes Btrfs-Subvolume auf dem Home-Mount sein. Ein
Generationenrollback schützt mutable Home-Daten nicht.

Die Quelle wird unter Compare-and-swap-Prüfungen integriert. Die ursprünglichen
Datei- und Index-Inodes verbleiben geschützt unter
`/home/.weasel-update-transactions/ID`, damit Saves über bereits offene
Dateideskriptoren erhalten bleiben. Journale werden vor jedem Übergang
synchronisiert. Erst danach wählt der Dienst den exakten getesteten Storepfad
und prüft Netzwerkdienste und DNS. Er veröffentlicht ausschließlich den
geprüften Commit ohne Force-Push.

## Parallel arbeiten, anhalten und Recovery

Andere T3-Threads bekommen jeweils einen eigenen Worktree. Sie dürfen parallel
editieren, evaluieren und bauen. Der Laptop hat aber nur eine laufende
Systemgeneration: Aktivierungen und Updates werden koordiniert. Vor `fr`,
`fu`, `nh os switch` oder einem manuellen Switch zuerst den Updatestatus prüfen
und einen laufenden Lauf abwarten. Der Dienst prüft andere Aktivierungsprozesse,
aber ein beliebiger Adminprozess respektiert seinen Lock nicht automatisch.
Veröffentlichte, noch nicht aktivierte Quellen blockieren den nächsten
Update-Switch, bis die Baseline wieder den laufenden Stand reproduziert.

Zum Pausieren den bestehenden T3-Task deaktivieren, nicht einen zweiten
anlegen. Das beendet keine bereits laufende Root-Transaktion. Der normale
Terminalbefehl `sudo systemctl stop weasel-update-activate.path` verhindert
weitere Trigger. Einen aktiven Dienst nicht ohne Diagnose abbrechen;
Unterbrechungen nach dem Snapshot oder während Integration benötigen Recovery.

```sh
weasel-update --status
systemctl status weasel-update-activate.path weasel-update-activate.service
sudo journalctl -u weasel-update-activate.service
sudo cat /var/lib/weasel-updates/runs/ID/journal.json
sudo snapper -c home list
```

Jedes ungeklärte Journal blockiert weitere Updates. Bei Aktivierungsfehlern
versucht der Dienst nur, die vorherige Systemgeneration wieder auszuwählen.
Home wird niemals automatisch restauriert. Originale, Snapshot-ID und beide
Systemclosures bleiben erhalten. Zuerst aktive Generation, Bootprofil,
Quellen, Remote und behaltene Originale vergleichen; fremde Editoränderungen
separat sichern bzw. integrieren. Danach einen konkreten Reparaturkandidaten
bauen und prüfen. Journale nicht einfach löschen oder auf `complete` setzen.
Der Helper bietet bewusst keinen pauschalen Recovery-/Home-Reset-Befehl.

Der Updater begrenzt ausschließlich seine markierten aufgelösten Kandidaten
und abgeschlossenen Transaktionen auf drei. Geänderte Originale, offene
Dateideskriptoren und ungeklärte Transaktionen werden erhalten. Gelöscht werden
nur eindeutig zugeordnete Updater-Snapshots und eigene Artefakte. Persönliche
Daten, Spiele, Modelle, VM-Disks und fremde Worktrees sind keine Cleanup-Ziele.
Ein Stromausfall während Cleanup hinterlässt ebenfalls einen Recoveryfall.

## Einmaliger Bootstrap

Die erste Installation des festen Root-Dienstes braucht normale Hostrechte.
Im aktuellen T3-Harness verhindert `NoNewPrivs` die Privilegienerhöhung auch
bei freigegebenen Build-/Netzwerkbefehlen. Ein anderer User-Executor ist kein
zulässiger Ausweg. Alle Quellen, Tests und Builds werden deshalb zuerst
fertiggestellt; erst dann wird ein konkreter Bootstrap-Beleg erzeugt.

Der endgültige Terminalbefehl nennt einen unveränderlichen Store-Wrapper und
einen unveränderlichen Beleg mit exaktem signiertem Commit, Quellmanifest,
vorherigem System und gebautem neuen System. Der Bootstrap prüft diese
Bindung erneut, erstellt den Home-Snapshot und aktiviert exakt diesen Pfad.
Wenn Main, Remote oder aktive Generation inzwischen gewechselt haben, muss
zuerst neu gebaut und der Beleg erneuert werden. Ein späteres unbeschränktes
`nixos-rebuild switch` aus mutable Quellen ersetzt diesen Nachweis nicht.

## Remote Builds und mehrere Maschinen

Die aktuelle Installation aktiviert ausschließlich `nixy-laptop`. Sie richtet
noch keinen VPS-Builder und keinen Flotten-Rollout ein. Die dafür geeignete
Trennung steht in [remote-update-builds.md](remote-update-builds.md): zentrale
Kandidaten-/Build-/VM-Tests, maschinenspezifische Gates und lokale Aktivierung.
Ein VPS-Test ersetzt weder echte Laptop-Hardwareprüfungen noch Backups von
produktiven VM-Daten.
