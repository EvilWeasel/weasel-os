# Optionaler UI-Evaluator: gebauter Vorschlag, tatsächlicher Prototype-Benchmark

Der Python-Stdlib-Evaluator ergänzt eine schmale paid API für Predicate/Choice.
Er besitzt keine Desktop-Eingabe, keine Capture-Funktion, keine Shell und keine
freie Aktionsplanung. Die lokale Prototypausführung wurde am 9. Oktober 2026
real gegen OpenAI geprüft. Das deklarative Paket und die Systemd-/MCP-Anbindung
sind vorbereitet und gebaut, aber deren Aktivierung und ordinary-client
Live-Nachweis stehen noch aus. Dieser Unterschied bleibt auch nach Kopieren
der Dateien in den Repository-Quellstand bestehen.

`decisiond.py` hält eine persistente Unix-Verbindung und HTTP-Keepalive sowie
ein SQLite-Kostenledger. `mcp.py` bietet `desktop_decide` und den kostenlosen
`desktop_decision_status`; bei ausgeschaltetem Dienst folgt schnell ein klarer
Capability-Fehler, danach verwendet der Agent den normalen Desktopweg.
`benchmark.py` kann einen explizit gestarteten gepaarten Vergleich ausführen;
ohne `--execute` erfolgt kein API-Aufruf. Für die Vorbereitung bestanden
15 Offline-Prüfungen und der Paketbuild.

Das tatsächliche eingefrorene Zen-Formular-Textprädikat ergab zehn korrekte Paare:
Decisions warm Median 250,78 ms, Responses 1.952,00 ms; mediane paarweise Ratio
6,8269. Es gab neun warme Samples je Endpoint und je einen ersten Lauf, keinen
p95 und keinen Bild-/Gesamtworkflow-Vergleich. Der Beleg liegt privat in
`~/.local/state/weasel-os/computer-use/2026-10-09/decisions/paired-form-text-10.json`.

Das bestehende Ledger bleibt unverändert:

```text
stateDirectory = ~/.local/state/weasel-os/computer-use/2026-10-09/decisions/ledger
jobId = computer-use-20261009
priorCalls = 2
maxCalls = 200
budgetUsd = 10
```

Zehn Decisions-Aufrufe nutzten 2.480 Inputtokens/0 Outputtokens, zehn Responses-
Aufrufe 1.560/454. Der Benchmark ergibt nach dokumentierten Standardpreisen
0,0006310 USD; zwei frühere Proben zusätzlich 0,0000227 USD. Insgesamt 22 Calls,
geschätzt 0,0006537 USD, tatsächliche Rechnung unbekannt. Konservativ bleiben
1,10 USD reserviert und 178 Versuche verfügbar. Reservierungen werden auch
nach Fehlern, Neustart oder unbekannter Billing-Antwort nicht zurückgegeben;
Job/State-Verzeichnis niemals zum Umgehen der Grenze ersetzen.

Die [Decisions-Dokumentation](https://developers.openai.com/api/docs/guides/decisions)
nennt für `gpt-6-luna` Input 0,10 USD/M und keine Output-/Cache-Gebühr.
Die [allgemeine Preistabelle](https://developers.openai.com/api/docs/pricing)
nennt Responses standardmäßig 0,10 USD/M Input und 0,50 USD/M Output. Schätzungen
berücksichtigen keine regionalen Aufschläge und behaupten keine Rechnung.

Das vorbereitete `programs/ui-decisions.nix` installiert eine Unit ohne
WantedBy und ohne Restart. Nur ein expliziter Start macht API-Verarbeitung
möglich. Ihre owned 0600 EnvironmentFile enthält ausschließlich den ausgewählten
Proton-Pass-Verweis auf `openai-t3`, niemals den Key. Maskiertes
`PROTON_PASS_LINUX_KEYRING=dbus pass-cli run` injiziert den Key ausschließlich in
die Kindprozessumgebung. Die MCP-Seite benötigt keinen Key. Keine OAuth-
Tokenextraktion oder nicht dokumentierte Codex-Auth-Wiederverwendung.

Nach belegter Aktivierung sind die vorgesehenen Bedienwege:

```sh
systemctl --user start weasel-ui-decisions.service
systemctl --user status weasel-ui-decisions.service
systemctl --user stop weasel-ui-decisions.service
```

Die additive verwaltete MCP-Konfiguration heißt `weasel_decisions`. Ihr Tool
akzeptiert `task_id`, `observation_id`, begrenzten Text, ein Predicate oder eine
Choice mit bestehenden Kandidaten-IDs, optional einen expliziten privaten
PNG/JPEG-Crop-Pfad und ein Timeout von 500–15.000 ms. Leere Bildroots deaktivieren
Bildversand. Bilder werden nicht selbst ausgewählt oder aufgenommen.

Gleiche Request-ID und identische Evidenz liefert einen als gecacht markierten
Receipt, keinen frischen Entscheid. Neue Beobachtungen brauchen neue IDs.
Wiederverwendung mit geändertem Inhalt wird abgelehnt. Es gibt keine
automatischen Retries; Crash-/Timeout-Dispatch kann Kosten erzeugt haben und
wird nicht automatisch wiederholt. Cancel unterdrückt die Ergebniszustellung,
behauptet jedoch keinen Abbruch bereits gestarteter Providerberechnung.

Die separate Rust-Aktorprüfung bestimmt Frische, Fensteridentität, erlaubte
Ziele, Aktionen, Resultat und Desktop-Übernahme. Eine Modellprobabilität oder
Choice ist keine Garantie und darf diese Prüfungen nicht umgehen. Die Voice-
Implementierung bleibt eine spätere Projektstufe.
