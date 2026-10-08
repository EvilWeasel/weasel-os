# T3 nativ starten und sudo im Auto-Modus verwenden

Der Laptop erlaubt bereits passwortloses sudo für die Gruppe `wheel` über
`security.sudo.wheelNeedsPassword = false`. Die T3-AppImage-Paketierung mit
einem FHS/Bubblewrap-Launcher setzt allerdings `NoNewPrivs=1` auf T3 und seine
Backend-/Codex-Prozesse. Auch genehmigte Codex-Kommandos außerhalb der
Codex-Sandbox können diese geerbte Sperre nicht entfernen.

`packages/t3code/flake.nix` paketiert daher denselben Upstream-Payload nativ
mit `autoPatchelfHook` und den benötigten Laufzeitbibliotheken. Das
Anwendungsarchiv bleibt bytegleich; es gibt keinen T3-Fork, keine neue
sudoers-Regel und keine Abfrage eines Administratorpassworts aus Proton Pass.
Der Launcher fügt keine `--no-sandbox`-Option hinzu. T3s Berechtigungsmodus und
Codex-Sandbox bleiben eigenständige Kontrollen.

## Einmaliger Start aus dem normalen Host-Terminal

Eine bereits laufende T3-/Codex-Sitzung mit `NoNewPrivs=1` kann weder sudo
benutzen noch durch den Start eines Kindprozesses die Sperre loswerden.
Beende die alte T3-App vollständig und starte den gebauten Kandidaten aus
einem normalen Laptop-Terminal:

```sh
env -u ELECTRON_RUN_AS_NODE /tmp/t3code-native-sudo-candidate/bin/t3code
```

Dieser Teststart benötigt keinen System-Switch und verwendet die vorhandenen
T3-Daten. Er wirkt bis zum Beenden der App. Der Symlink in `/tmp` ist ein
lokales Build-Artefakt. Zum erneuten Bauen aus dem Repository:

```sh
nix build --no-write-lock-file .#t3code --out-link /tmp/t3code-native-sudo-candidate
```

Lass den Thread im T3-Modus `Auto`. Nach dem Neustart prüft der Agent mit einer
vom automatischen Reviewer behandelten Eskalation zunächst rein lesend
`sudo -n id -u`. Erst `0` belegt tatsächlich funktionierendes Root. Danach
können beispielsweise laufende Firewallregeln und VPN-Paketköpfe geprüft
werden. Dieser Start und Root-Test müssen außerhalb der alten Launcher-
Umgebung erfolgen; sie sind durch einen Paketbuild allein nicht bewiesen.

## Dauerhafte Installation und Grenzen

Die Änderung gehört zur deklarativen Laptop-Konfiguration. Eine spätere
Aktivierung folgt dem normalen NixOS-Workflow; aktive oder ungeklärte
Update-Transaktionen müssen vorher geklärt sein. Der am 2026-10-08 gebaute
Main-Kandidat enthält auch bereits veröffentlichte, noch nicht aktivierte
Codex-/ChatGPT-/Updater-Änderungen. Deshalb wurde für diesen Task kein
System-Switch ausgeführt.

Windows/UAC auf Blain37 wird durch diese Linux-Paketkorrektur nicht verändert.
Passwortloses sudo ist die Betriebssystemberechtigung; der Auto-Reviewer
entscheidet weiterhin über die an ihn gerichteten Codex-Anfragen.

## Verifikation am 2026-10-08

- Nix-Syntax, Formatierung und `git diff --check` erfolgreich.
- `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`
  und vollständiger Laptop-Build erfolgreich; `flake.lock` unverändert.
- `nix flake check --no-build --no-write-lock-file` erfolgreich.
- Native Terminal-, Keyring-, FFI- und Accessibility-Module laden;
  PTY-Shell und SQLite-In-Memory-Abfrage erfolgreich.
- Isolierter nativer T3-Start mit eigenen XDG-/T3-Daten: tatsächliches
  Nightly-Fenster und HTTP 200 am Environment-Endpunkt beobachtet.
- SHA-256 des `app.asar` stimmt mit dem ursprünglichen Upstream-Payload
  überein. Kein Root-Test oder produktiver Neustart als bestanden behauptet.
