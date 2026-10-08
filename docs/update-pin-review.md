# Tägliche Pin-Prüfung

Die Registry in `config/update-pins.json` erfasst die Gründe bestehender Pins
und die nötigen Prüfungen. Sie ist ein Ausgangsinventar, keine Liste dauerhaft
verbotener Updates. Die tägliche T3-Aufgabe liest zusätzlich die aktuellen
Quellen und alle transitiven `flake.lock`-Nodes; neue Pins gehören in die lokale
Tagesprüfung. Bei Einrichtung wurden 37 Einträge und 70 Lock-Nodes erfasst.

Der LLM beurteilt Gründe und recherchiert Kandidaten. Der Discovery-Helfer
ermittelt exakte offizielle Artefakte. Vorbereitung und Submitter müssen die
konkreten Builds und Funktionsprüfungen selbst nachweisen. Ein Registry-Status
`implemented-pending-integration-verification` behauptet keinen bestandenen
Kandidatentest und keine Aktivierung. Lanes ohne Adapter bleiben in der
täglichen Prüfung und erzeugen begrenzte Implementierungs-/Migrationstasks.

Aktuell erlauben die automatischen Adapter T3-Quell-JSON und ausschließlich
Version/`src.hash` in den vorhandenen Codex-/ChatGPT-Derivationen. Sie erhalten
die Nix-URL-Templates und sämtliche Patches. Andere Code-, Paket-, Input- oder
OS-Änderungen brauchen ihre eigenen geprüften Adapter bzw. Migrationstasks.

## Quellen und Holds

Jede Tagesentscheidung enthält ID, aktuelle Quelle/Version, Pin-Grund,
exakte offizielle Beleg-URLs, betroffene Versionen, Prüfnachweis und nächsten
Termin. Ein unbekannter Grund wird spätestens am nächsten Tag untersucht.
`adapter-needed` verlangt einen konkreten Adaptertask; es ist kein dauerhafter
Hold. `hold-with-evidence` braucht weiter aktuelle Belege und eine endliche
Überprüfung. Wiederholte Fehlschläge werden sichtbar zusammengefasst.

Die lokale Review-Datei nutzt `schema_version: 1`, `reviewed_at`, `entries`;
jeder Eintrag hat `id`, `current`, `decision`, `reason`, `evidence_urls` und
`next_review`. Optional sind `affected_versions`, `checks`, `candidate` und
`investigation`. `weasel-update --record-review PATH` validiert die Datei.
Die genaue Bedienung und Recovery stehen in [daily-updates.md](daily-updates.md).
Der native T3-Task verwendet [daily-update-review.md](../prompts/daily-update-review.md)
mit der vorhandenen Codex-Anmeldung.

## Discovery-Vertrag

`scripts/weasel-update-discover.py --lane t3|codex|chatgpt --repository PATH
--output PRIVATE.json` schreibt einen neuen privaten JSON-Beleg und verändert
keine Quellen. T3 unterstützt `--channel nightly|stable`; standardmäßig wird
der ausdrücklich gewählte reguläre Nightly-Kanal geprüft. Maintainer-Previews
werden anhand strikter Tags und Release-Metadaten ausgeschlossen.

Der JSON-Vertrag ist `schema_version: 1`, `lane`, `channel`, `current`,
`candidate`, `evidence`, `checked_at`, `status`, `source_files`. Pins enthalten
exakt `version`, versionierte `url` und SHA-256-SRI-`hash`. `candidate` ist bei
unverändertem Stand oder älterem Upstream `null`. Ein älteres stabiles T3 bei
installierter neuerer Nightly ergibt `held-prerelease` und keinen Downgrade.
Gleiche T3-Version mit geändertem veröffentlichten Hash ist ein Fehler.

- T3: offizielle Release-API, x86_64-AppImage, offizieller Asset-Digest und
  passender Eintrag in `SHA256SUMS`; neue Kandidaten zusätzlich vollständig
  gehasht. Aktuelle Nightlies führen dort nur CLI-Archive: Alle CLI-Einträge
  müssen mit den offiziellen Asset-Digests übereinstimmen, und zusätzlich ist
  das offizielle Desktop-Manifest `nightly-linux.yml` mit exakter Version,
  AppImage-Datei, Größe und SHA-512 erforderlich. Kandidatenbytes müssen beide
  Desktop-Hashes erfüllen. Der Beleg nennt diesen manifest scope ausdrücklich.
  Keine fehlenden Digests, Drafts oder Kanalabweichungen akzeptieren.
- Codex: offizielles npm-`latest`, exakt dessen `-linux-x64`-Version und
  Tarball-URL. Neue Kandidaten werden gegen npm-SHA-512-Integrity geprüft und
  erhalten den aus denselben Bytes berechneten SHA-256-SRI-Pin.
- ChatGPT: maximal 2 MiB RPM-Header vom offiziellen mutable `latest`-Endpunkt;
  Name `chatgpt`, Release `1`, Architektur `x86_64` und Version prüfen. Dann das
  konkrete versionierte RPM vollständig hashen und dessen Identität erneut
  prüfen. Es werden weder Payload noch RPM-Scriptlets ausgeführt.

Unveränderte Codex-/ChatGPT-Payloads werden nicht täglich erneut heruntergeladen;
der Beleg benennt diese Grenze. Neue Kandidaten und unabhängige Submission
prüfen immer die exakte Version. Eine inzwischen neuere `latest`-Version macht
einen korrekt getesteten älteren Kandidaten nicht ungültig.

Netzwerkzugriff nutzt pro Lane feste HTTPS-Hosts mit kontrollierten Redirects.
JSON und Checksummen sind auf 4 MiB bzw. 1 MiB begrenzt, Artefakte auf 768 MiB,
RPM-Metadaten auf 2 MiB. Streaming-Reads verwenden 1-MiB-Blöcke und höchstens
300 Sekunden Gesamtbudget. Das Budget begrenzt keine anderen LLM-Recherchen;
diese müssen selbst begrenzt werden. Ausgabe überschreibt keine vorhandenen
Dateien oder Symlinks und wird mit Modus `0600` angelegt.

Die importierbaren APIs sind `read_pin(lane, bytes)`,
`replace_pin(lane, old_bytes, pin)` und
`validate_transition(lane, before_bytes, after_bytes, network=True)`.
Der letzte Aufruf validiert den exakten veröffentlichten Kandidaten unabhängig
von `latest` und gibt `{old: pin, new: pin}` zurück. `DiscoveryError` stoppt den
Kandidaten. Nix-Übergänge dürfen außerhalb der beiden Literale kein Byte ändern;
T3-JSON erlaubt nur die drei Quellfelder. Der deterministische
`learning_suffix(id,lane,old_version,new_version)` wird erst nach bestandenen
Builds/Gates angehängt und verweist für Aktivierung auf das spätere Root-Journal.

## Migrationen und erneute Prüfung alter Workarounds

Die Ausgangsbasis 25.11 ist seit 2026-06-30 außerhalb des Supports; 26.05 wird
bis 2026-12-31 unterstützt. Stabiler NixOS- und Home-Manager-Wechsel gehören in
einen eigenen Migrationstask; `system.stateVersion` bleibt ein bewusstes
Kompatibilitätsdatum. Diese Angaben wurden am 2026-10-08 offiziell geprüft und
müssen vor Migration aktualisiert werden.
[NixOS-Releaseankündigung](https://nixos.org/blog/announcements/2026/nixos-2605/)

Die 6.18-Kernelwahl entstand, als EVDI 1.14.12 gegen 7.0.3 nicht baute. EVDI
führt inzwischen vorläufigen Support für Kernel 7 in neueren Releases auf.
Das rechtfertigt eine erneute Kandidatenprüfung; Hotplug, suspend und NVIDIA
müssen weiterhin am konkreten Laptop geprüft werden.
[EVDI-Releases](https://github.com/DisplayLink/evdi/releases)

NetBird #7331 ist als `not_planned` geschlossen und beschreibt einen
Kernel-Fehler. `NB_DISABLE_EBPF_WG_PROXY=true` entfällt erst, wenn der genaue
Kernel-Fix im Kandidaten nachgewiesen und die Netzwerkfunktion geprüft wurde.
[NetBird-Issue](https://github.com/netbirdio/netbird/issues/7331)

Azure Data Studio ist seit 2026-02-28 stillgelegt. Der weiterhin installierte
Eintrag verlangt Nutzungsaudit und Ersatzplanung unter Erhalt bestehender
Einstellungen; Microsoft empfiehlt VS Code mit MSSQL-Erweiterung.
[Microsoft-Migrationshinweise](https://learn.microsoft.com/en-us/sql/tools/whats-happening-azure-data-studio?view=sql-server-ver17)

Die alte ew-cloud/Fontconfig-Flake-Störung ist kein aktueller Hold: Die vollständige
Flake-Prüfung bestand bei dieser Einrichtung. Spätere Fehler müssen anhand
aktueller Belege untersucht werden. Lokale Helium-, Frosty- und Screenpipe-
Derivationen sind gesonderte Nutzungsaudits; daraus startet keine Aufnahme,
Spielsession oder andere pausierte Arbeit automatisch.
