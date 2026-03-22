# Aktueller Umsetzungsplan

Ziel: die aktuellen Probleme am Laptop-Setup so lösen, dass die sauberen Defaults für alle Geräte gelten und host-spezifische Ausnahmen nur noch dort liegen, wo sie wirklich nötig sind.

## Was wir gerade wissen

- `Super+Space` ist als DMS-Default-Bind in `programs/niri/dms/binds.kdl` vorhanden und wird per Repo-Ownership in die Home-Konfiguration gezogen.
- `DisplayLink` ist im Repo bereits aktiviert, aber der aktuelle Michael-Repro zeigt nur einen externen Output in Niri. Das ist ein Hinweis auf Output-Mapping/Erkennung, nicht auf ein reines USB-Problem.
- Das Audio-Problem wirkt global: im Greeter läuft schon WirePlumber und schreibt State nach `/var/empty`, und die Session hat eine kaputte `environment.d`-Zeile. Das ist nicht sinnvoll und kann zu zufälligen Audio-Ausfällen führen.
- Hypridle, Hyprlock, Hyprland-Waybar und Wlogout-Reste wurden entfernt; DMS übernimmt Lock- und Power-Aktionen.
- `weasel-collect-session-debug` sammelt schon viel, aber die Ausgabe ist noch zu grob für große Debug-Sessions.

## Zielbild

1. Die Standard-Niri-Config für alle Hosts soll meine normalen Keybindings enthalten, inklusive eines funktionierenden Launcher-Binds auf `Super+Space`.
2. `DisplayLink` soll standardmäßig für alle Laptops aktiviert sein. Falls ein Host trotzdem Sonderbehandlung braucht, dann nur als host-spezifischer Override.
3. Audio soll für alle Hosts robust und deterministisch funktionieren, ohne Audio-Stack im Greeter und ohne zufällige Sink-Auswahl.
4. Das Debug-Tooling soll deutlich mehr strukturierte Infos liefern, ohne große Logs unkontrolliert in ein einziges Riesenfile zu kippen.
5. Hyprland- bzw. Hypridle-Reste sind weitgehend entfernt; nur echte Restreferenzen oder Folgeprobleme sollen noch bleiben.

## Arbeitspakete

### 1. Globale Niri-/DMS-Defaults vereinheitlichen

- Den Launcher-Bind global in die gemeinsame Niri-Konfiguration ziehen, damit neue Hosts und Neuinstallationen direkt die gleiche Basis haben.
- `Mod+Shift+Return` kann als Alternative bleiben, aber `Super+Space` soll der normale Launcher-Weg sein.
- Die gemeinsame Default-Konfiguration so aufbauen, dass Michael nur noch lokale Anpassungen macht statt eine andere Basis zu haben.

### 2. DisplayLink als allgemeines Laptop-Feature

- `DisplayLink` für alle Laptop-Setups standardmäßig aktivieren.
- Falls die Kombination aus Dock, GPU und Output-Topologie bei Michael trotzdem nicht sauber läuft, dort zusätzlich host-spezifische Output-Regeln hinterlegen.
- Repro mit beiden Dock-Monitoren erzwingen und dann auf stabile Ausgabe prüfen: beide Monitore müssen in `niri msg outputs` auftauchen und beim Reconnect gleich bleiben.

### 3. Audio global stabilisieren

- Audio-Dienste aus dem Greeter entfernen bzw. sicherstellen, dass sie dort nicht als eigener zweiter Stack laufen.
- Die kaputte Environment-Datei reparieren, damit der Environment-Generator nicht mehr mit Syntaxfehlern wegwirft.
- Eine feste Default-Sink- und State-Restore-Policy für PipeWire/WirePlumber einziehen, damit App-Wechsel und Hotplug nicht mehr zufällig das Ausgabegerät verlieren.
- Danach mit typischen Szenarien testen: Boot, Firefox/YouTube, Steam/Factorio, Vesktop, Dock rein/raus.

### 4. Debug-Collection sauberer und feiner machen

- `weasel-collect-session-debug` in getrennte Bereiche aufteilen:
  - kurze, allgemeine Übersicht
  - gezielte Audio-Ausgaben
  - gezielte Niri-/Output-/DRM-Ausgaben
  - gezielte Input-/Lid-/Dock-Ausgaben
  - große Rohlogs nur noch als bewusstes, getrenntes Artefakt
- Die Abfrage so aufbauen, dass relevante Infos leicht mit `rg` gefunden werden können, statt große Files manuell komplett zu lesen.
- In `AGENTS.md` eine neue Anweisung ergänzen:
  - große Logfiles nicht blind komplett lesen
  - stattdessen gezielt mit `rg` nach dem konkreten Problem suchen
  - während der Analyse eine temporäre Markdown-Datei als Scratchpad nutzen, damit wichtige Erkenntnisse bei Context-Compaction nicht verloren gehen
- Zusätzliches Ziel: Debug-Bundles sollen mehr Daten sammeln, aber besser sortiert, damit AI-Kontext nicht durch ein einziges Monolith-Log verloren geht.

### 5. Hyprland-Reste aufräumen

- Verwaiste Hyprland-Tools und Konfigs sind bereits großteils entfernt; nur noch echte Restreferenzen oder fehlende Fallbacks nachziehen.

### 6. Michael-spezifische Fallbacks nur wenn nötig

- Wenn der globale DisplayLink- oder Audio-Fix bei Michaels HP-Laptop nicht voll ausreicht, dann dort gezielt host-spezifische Overrides hinzufügen.
- Host-spezifische Lösungen sollen immer Fallback bleiben, nicht die Standard-Architektur für alle Geräte.

## Reihenfolge

1. Debug-Collection und AGENTS-Anweisungen verbessern, damit die nächsten Repros schneller und sauberer analysierbar sind.
2. Niri-Defaults für Launcher und globale Defaults vereinheitlichen.
3. DisplayLink global aktivieren und danach auf beiden Monitoren verifizieren.
4. Audio global stabilisieren.
5. Hyprland-/Hypridle-Reste verifizieren und nur echte Restreferenzen nachziehen.
6. Nur falls nötig Michael-spezifische Overrides nachziehen.

## Verifikation

- `nix flake check`
- `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`
- Repro mit angeschlossenem Dock:
  - beide Monitore sichtbar
  - Audio nach Boot und nach App-Wechsel vorhanden
  - `Super+Space` öffnet den Launcher
  - internes Keyboard/Touchpad verhalten sich im Dock-/Lid-Fall korrekt

## Offene Punkte

- Falls Michael nicht auf dem gemeinsamen Laptop-Host landet, brauchen wir einen expliziten Host-Override statt nur globaler Defaults.
- Falls der interne Keyboard-/Touchpad-Fall nur mit einem hardware-spezifischen Unbind sauber lösbar ist, wird das als letzter Schritt host-spezifisch gelöst.
