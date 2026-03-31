# Flake-parts- und `ew-cloud`-Migrationsplan

## Ziel

Die Flake soll auf `flake-parts` im dendritischen Stil umgestellt werden, ohne bestehende Client-Hosts zu beschädigen. Danach soll eine wiederverwendbare Server-Baseline mit `sops-nix`, `tailscale`, `disko` und einer ersten `OpenClaw`-Rolle eingeführt werden. Der erste Server-Host ist `ew-cloud`.

## Rahmenbedingungen

- Bestehende Hosts müssen mindestens weiter evaluieren.
- `nixy-laptop` ist der primäre Regressionshost.
- Server sollen im Regelbetrieb ausschließlich über Tailscale erreichbar sein.
- Secrets laufen über `sops-nix`.
- Der erste Secrets-Bootstrap neuer Server erfolgt mit einem vorab erzeugten dedizierten Age-Key pro Host.
- `OpenClaw` wird in der ersten Iteration als Scaffold installiert, nicht als vollständig produktiv verdrahteter Agent.

## Checkliste

### 1. Plan- und Prüfbasis festschreiben

- [x] Diese Datei aktuell halten, falls sich während der Umsetzung technische Annahmen ändern.
- [x] Für jeden größeren Umbauabschnitt konkrete Verifikationsschritte ausführen und abhaken.

**Erfolgskriterien**

- Es gibt genau eine aktuelle Plan-Datei für diese Migration.
- Jeder abgeschlossene Block hat mindestens ein messbares Prüfergebnis.

### 2. Flake auf `flake-parts` umstellen

- [x] `flake.nix` auf `flake-parts.lib.mkFlake` umstellen.
- [x] Flake-Outputs in dedizierte `flake-parts`-Module aufteilen.
- [x] Bestehende Outputs funktional erhalten: `formatter`, `packages`, `devShells`, `apps`, `nixosConfigurations`.
- [x] Host-Inventarisierung in eine flake-parts-kompatible Struktur überführen.

**Erfolgskriterien**

- `nix flake show --all-systems` zeigt weiterhin `apps`, `devShells`, `formatter`, `nixosConfigurations` und `packages`.
- `nix flake check` läuft ohne neue Evaluationsfehler.
- `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath` läuft erfolgreich.
- `nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath` läuft erfolgreich.

### 3. Gemeinsame Baselines in `common`, `client`, `server` schneiden

- [x] System-Baseline in universelle, client-spezifische und server-spezifische Module zerlegen.
- [x] Home-Manager-Baseline analog in universelle, client- und serverbezogene Module zerlegen.
- [x] Desktop-/Laptop-spezifische GUI- und Consumer-Stacks aus der Shared-Base entfernen.
- [x] Serverseitige Terminal-Umgebung mit `neovim`, `yazi`, Shell-Tooling und Helpern bereitstellen.

**Erfolgskriterien**

- `nixy-laptop` evaluiert nach dem Refactor weiter erfolgreich.
- `nixy-desktop` evaluiert nach dem Refactor weiter erfolgreich.
- Der Serverpfad importiert keine DMS-, GTK-, Rofi-, VS-Code-, Audio- oder Gaming-Komponenten.
- Die Flake-DevShell ist weiterhin verfügbar und der Server-Home-Pfad enthält die terminalorientierten Konfigurationen.

### 4. Server-Baseline mit Least-Privilege-Defaults einführen

- [x] Gemeinsame Server-Baseline mit minimalem Paket- und Dienstesatz anlegen.
- [x] SSH auf Key-only und Root-Login-Verbot härten.
- [x] Öffentliche Inbound-Ports standardmäßig schließen.
- [x] Freigaben pro Host explizit statt global öffnen.
- [x] `users.mutableUsers = false` für Server setzen.

**Erfolgskriterien**

- Ein Server-Host evaluiert ohne Desktop-spezifische Abhängigkeiten.
- Auf dem Serverpfad ist `openssh` gehärtet und kein öffentlicher Port standardmäßig freigegeben.
- Host-spezifische Port-Freigaben sind als gezielte Overrides möglich.

### 5. `sops-nix` integrieren

- [x] `sops-nix` als Input und Modul integrieren.
- [x] Repo-Struktur für Secrets und `.sops.yaml` anlegen.
- [x] Standardpfad für per-Host-Age-Key und Host-Secrets definieren.
- [x] Serverpfad so aufbauen, dass `tailscale` seinen Auth-Key aus `sops-nix` beziehen kann.

**Erfolgskriterien**

- `nix eval --no-write-lock-file .#nixosConfigurations.ew-cloud.config.system.build.toplevel.drvPath` scheitert nicht an fehlender `sops-nix`-Verdrahtung.
- Es existiert ein klarer Secrets-Pfad pro Host.
- Die Laufzeitkonfiguration verweist auf einen dedizierten Host-Age-Key statt auf unverschlüsselte Werte im Repo.

### 6. `ew-cloud`-Host mit `disko` und `tailscale` anlegen

- [x] `hosts/ew-cloud/` mit Host-, User-, Variablen-, Disko- und Hardware-Dateien anlegen.
- [x] Btrfs-Disko-Layout mit EFI und getrennten Subvolumes definieren.
- [x] Server-Home-Profil für den Admin-User verdrahten.
- [x] Tailscale als Pflichtdienst mit SSH-Unterstützung einbauen.
- [x] Öffentlichen SSH-Zugang im Zielzustand schließen und Tailnet-only-Zugang als Standard umsetzen.

**Erfolgskriterien**

- `nix eval --no-write-lock-file .#nixosConfigurations.ew-cloud.config.system.build.toplevel.drvPath` läuft erfolgreich.
- Der Host importiert die Server-Baseline und keine Client-Baseline.
- Firewall-Regeln öffnen standardmäßig nur `tailscale0`.
- Der Host kann nach einem echten Install ausschließlich über Tailnet-Zugang administriert werden.

### 7. `OpenClaw` als Server-Rolle hinzufügen

- [x] `nix-openclaw` als Input integrieren.
- [x] Dedizierte `OpenClaw`-Rolle oder Hostmodul anlegen.
- [x] Paket, Laufzeitstruktur und persistente Verzeichnisse bereitstellen.
- [x] Secrets und privilegierte Rebuild-/GitHub-Aktionen noch nicht produktiv erzwingen.

**Erfolgskriterien**

- `ew-cloud` evaluiert mit aktivierter `OpenClaw`-Rolle.
- `OpenClaw` ist als klar separater Baustein implementiert und nicht Teil der generellen Server-Baseline.
- Die Rolle ist auf weitere Server wiederverwendbar.

### 8. Validierung, Dokumentation und Abschluss

- [x] Alle betroffenen Hosts evaluieren.
- [x] `nix flake check` laufen lassen.
- [x] Relevante Nix-Dateien syntaxprüfen.
- [ ] `agent-learnings.md` append-only ergänzen.
- [ ] Änderungen in einem signierten Commit festhalten und nach erfolgreicher Verifikation nach `origin/main` pushen.

**Erfolgskriterien**

- Alle definierten Evaluationskommandos laufen erfolgreich.
- Es bleiben keine unbewussten Worktree-Konflikte mit den bestehenden User-Änderungen zurück.
- `agent-learnings.md` enthält einen neuen faktenbasierten Eintrag zu dieser Migration.
- Commit und Push sind signiert und erfolgreich.

## Verifikationsmatrix

### Pflichtprüfungen während der Umsetzung

- `nix flake show --all-systems`
- `nix flake check`
- `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`
- `nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath`
- `nix eval --no-write-lock-file .#nixosConfigurations.ew-cloud.config.system.build.toplevel.drvPath`

### Zusätzliche Prüfungen vor dem echten Server-Install

- `ssh` oder gleichwertiger Plain-OpenSSH-Zugriff über die Tailscale-Adresse des Ubuntu-Systems funktioniert.
- Zielblockdevice auf dem VPS ist mit `lsblk` verifiziert.
- Ein per-Host-Bootstrap-Age-Key liegt lokal vor.
- Der Tailscale-Auth-Key kann per `sops-nix` verschlüsselt eingebunden werden.

## Noch offene Ausführungsprämissen

- Das konkrete Blockdevice des Hostinger-VPS wird erst unmittelbar vor dem Install bestätigt.
- Der Admin-SSH-Public-Key wird beim Umsetzungszeitpunkt aus deiner lokalen Umgebung übernommen oder von dir bestätigt.
- Falls `nixos-anywhere` im Zielsetup nicht direkt über Tailnet-Plain-SSH nutzbar ist, bleibt ein einmaliger Bootstrap-Fallback über das bestehende Ubuntu-SSH die Reserveoption. Der Zielzustand bleibt trotzdem Tailnet-only.
