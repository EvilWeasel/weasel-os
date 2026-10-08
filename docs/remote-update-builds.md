# Zentrale Builds, VM-Tests und spätere Flotten-Updates

Stand: 2026-10-08. Das ist die Ausbauentscheidung und ein Handoff für einen
eigenen Infrastrukturauftrag. Der tägliche Updater in
[daily-updates.md](daily-updates.md) arbeitet zunächst für `nixy-laptop`.
Dieser Auftrag hat keinen VPS als Nix-Builder eingerichtet. Im Repository ist
bisher weder `nix.distributedBuilds` noch `nix.buildMachines` deklariert.
Der anschließend ausdrücklich beauftragte SSH-Zugang ist repariert und mit dem
dedizierten Proton-Key geprüft; dessen Protokoll steht in
[vps-ssh-credentials.md](vps-ssh-credentials.md).

## Empfehlung und vorhandener Zugang

Ein zentraler Rechner ist sinnvoll für die tägliche Auswertung exakter
Quellstände, Builds, gemeinsame Artefakte und Tests mit kurzlebigen NixOS-VMs.
Er kann die Laptop-Last reduzieren und Ergebnisse für mehrere Rechner sammeln.
Die tatsächliche Aktivierung bleibt eine eigene Transaktion auf dem jeweiligen
Zielhost mit dessen Snapshot, Zustand und Gesundheitsprüfung.

Hephaestus hat genug CPU und verfügbaren RAM für begrenzte Builds. Seine Platte
hat aber nur rund 45 GiB frei, er trägt bestehende Dienste, und eine bewusst
eingerichtete Policy setzt das lokale Nix-Store-Budget auf null. Er ist deshalb
gegenwärtig kein verfügbarer Nix-Builder. Ein Ausbau verlangt zuerst eine
eigene, hart begrenzte Speicherallokation mit geprüftem Lebenszyklus. Iris ist
mit zwei CPUs und vier GiB RAM für den Management- und Recovery-Weg vorgesehen
und sollte daraus nicht automatisch zum Build-Worker werden.

| Beobachtung | Beleg und Grenze |
| --- | --- |
| Hephaestus, Server `162472190`, Typ `cx43`, und Iris, Server `163123673`, Typ `cx23`, wurden heute als `running`, nicht gesperrt und mit nicht blockierten öffentlichen IPs gelesen. | Zunächst bereinigter API-Receipt `/tmp/hetzner-check-20261008.md`; nach ausdrücklicher Zugangsfreigabe begrenzte API-Leseprüfung über den bestehenden maskierten Proton-Pass-Zugang. |
| Beide VMs hatten in den API-Samples bis 19:13:57 UTC CPU- und Netzwerkaktivität. | Cloud-Liveness; kein Beweis für einen bestimmten Dienst, genug freien Speicher oder Nix. |
| Der persönliche Laptop-NetBird-Daemon war `Idle`, ohne Overlay-IP. `netbird-personal up --no-browser` verband ihn mit bestehenden Credentials. | Danach `Connected`, `100.96.62.207/16`, Management verbunden; Hephaestus `100.96.10.221` verbunden. Keine Neuregistrierung, kein Setup-Key und keine Änderung von ACLs oder Firewallregeln. |
| Hephaestus: tatsächlich `x86_64`, 8 CPUs, 15.6 GiB RAM, davon rund 10 GiB verfügbar; Root-Dateisystem 151 GiB, rund 45 GiB frei. | Authentifizierte SSH-Systeminventur am 2026-10-08. Cloud-API bestätigt CX43 mit 16 GB RAM und `primary_disk_size=160` GB; Dateisystemwerte stammen von `free`/`df`. |
| Iris: tatsächlich `x86_64`, 2 CPUs, 3.8 GiB RAM, davon rund 3.2 GiB verfügbar; Root-Dateisystem 38 GiB, rund 31 GiB frei. | Authentifizierte SSH-Systeminventur am 2026-10-08. Cloud-API bestätigt CX23 mit 4 GB RAM und 40 GB Primärdisk. |
| Hephaestus hat keinen verfügbaren Nix-Builder. | `/usr/local/bin/nix` verweist auf den Admission-Guard; selbst `nix --version` endet mit `local_store_budget_bytes=0`. Die Guard-Dokumentation verlangt eine separate harte Speichergrenze und einen geprüften Cache-Lebenszyklus. Kein Store und kein Portable-Nix wurden angelegt. |
| Iris hat kein Nix im normalen Benutzerpfad. Auf beiden Servern fehlt `/dev/kvm`; Hephaestus hat weder `vmx` noch `svm` in den CPU-Flags. | OS-seitig geprüft. Kein hardwarebeschleunigter NixOS-VM-Test belegt; keine Änderung von Kernel oder Virtualisierung. |
| Hephaestus betreibt laufende Hermes-, NetBird-, Factorio- und Burrow-Dienste. Iris' NetBird-Management-Seite antwortete per HTTPS. | Hephaestus: Namen und aktive Zustände über SSH gelesen; Iris: HTTPS-Antwort geprüft. Keine Appdaten oder Modelle. `aidan-realtime-engine.service` und `dnf-makecache.service` waren auf Hephaestus bereits fehlgeschlagen und wurden nicht verändert. Das ist keine vollständige Funktionsprüfung dieser Dienste. |
| Endgültiger SSH-Zugang: Hephaestus `hermes`/`root`; Iris `aidan` über Hephaestus-root als Jump, danach vorhandenes `sudo`. | Mit dediziertem Proton-Agent und gepinnten Hostkeys tatsächlich geprüft. Iris-Cloud-SSH erlaubt ausschließlich Hephaestus als Quelle; diese Regel blieb erhalten. Iris `PermitRootLogin=no` blieb erhalten. |
| `hosts/ew-cloud` enthält eine weitere x86_64-NixOS-Serverkonfiguration. | Sie ist kein belegter Alias für Hephaestus oder Iris. Die bestehenden Namen und IPs dürfen nicht zusammengeführt werden. |

Der anfängliche SSH-Timeout lag vor der später reparierten Overlay-Verbindung
und belegte keinen globalen Serverausfall. Die heutigen API- und OS-Lesungen
bestätigen Hephaestus als `cx43`; ältere Recovery-Texte über eine erst geplante
Vergrößerung von `cpx22` sind dafür kein aktueller Zustandsbeleg.

## Was ein Remote-Builder übernimmt

Nix kann einzelne Derivationen per SSH auf einer passenden Maschine bauen.
Der Builder braucht Nix, einen SSH-Server, einen funktionierenden privaten
Zugangsweg und den passenden Build-Benutzer. Für Multiuser-Nix muss der lokale
Nix-Daemon den SSH-Zugang selbst verwenden können; ein funktionierender
interaktiver Benutzerzugang allein reicht nicht. Architektur und Fähigkeiten
werden bei `nix.buildMachines` beziehungsweise `builders` deklariert.
[Nix: Remote Builds](https://nix.dev/manual/nix/2.28/advanced-topics/distributed-builds.html),
[nix.dev: Distributed Builds](https://nix.dev/tutorials/nixos/distributed-builds-setup.html).

Die Evaluation und die Update-Auswahl werden durch diese Builder-Einstellung
nicht zu einem zentralen Dienst. Dafür muss ein eigener Worker den exakten
Checkout auswerten. Er muss für jedes Ziel dieselben Quellen und Lock-Dateien
verwenden, die später aktiviert werden. Ein Remote-Builder übernimmt auch
keinen Flotten-Rollout, keine Drift-Reparatur und keine Datensicherung.

NixOS ist für die eigentlichen Testgäste maßgeblich. Der Host kann auch ein
anderes Linux mit einer geeigneten Nix-Installation sein; NixOS-Tests können
außerhalb von NixOS gestartet werden. Damit erfordert die Idee zunächst keinen
OS-Wechsel des bestehenden Hephaestus.
[nix.dev: NixOS-Integrationstests](https://nix.dev/tutorials/nixos/integration-testing-using-virtual-machines.html).

Die Einrichtung müsste den bisherigen Ansible-Verwaltungsweg und den
vorhandenen Disk-Prevention-Guard respektieren. Dessen lokale Dokumentation
`/usr/local/share/hermes-disk-prevention.md` erklärt den Anlass: Ein früherer
Portable-Nix-Build materialisierte unbeschränkt Daten. Heute verweigern die
Nix-Admission-Entrypoints jede lokale Store-Allokation, einschließlich Evaluation.
Die Policy nennt als Mindestbedingungen ein hartes Byte-Limit, mindestens
20 GiB verbleibenden freien Speicher, Producer-Supervision und einen nachweislich
begrenzten Lebenszyklus. Der Guard ist ein operativer PATH-Guard, keine harte
OS-Quota; ein anderer Binärpfad wäre ein Bypass und keine zulässige Einrichtung.

Ein dedizierter Build-Zugang erhält keine Berechtigung, Live-Dienste zu
aktivieren. Ein zentraler Planungsagent braucht keine breit verteilten
Root-SSH-Schlüssel. Host-Aktivierung sollte über einen getrennten, eng
begrenzten lokalen Helfer erfolgen. Build-Jobs brauchen feste Grenzen für
Parallelität, Laufzeit, RAM und Speicher sowie eine Reserve für die bisherigen
Serverdienste. `builders-use-substitutes` kann Abhängigkeiten direkt aus den
erlaubten Binärcaches beziehen.
[nix.dev: Builder-Konfiguration](https://nix.dev/tutorials/nixos/distributed-builds-setup.html).

## VM-Tests und GUI ohne physische GPU

`pkgs.testers.runNixOSTest` kann eine oder mehrere deklarative NixOS-VMs starten
und über Python die wirklichen Dienste und deren Zusammenarbeit prüfen. Diese
Tests sind als Build-Derivationen ausführbar und liefern Logs und testabhängige
Artefakte. So lassen sich beispielsweise Boot, Dienststart, Berechtigungen,
Migrationen und Kommunikation zwischen Testknoten prüfen.
[nix.dev: NixOS-Integrationstests](https://nix.dev/tutorials/nixos/integration-testing-using-virtual-machines.html),
[NixOS-Handbuch: Tests](https://nixos.org/manual/nixos/stable/index.html).

Für normale Linux-VM-Tests wird KVM verlangt. Das aktuelle Testmodul erlaubt
explizit `requiredFeatures.kvm = false` für emulierte Ausführung; zusätzlich
muss `qemu.forceAccel` zur gewählten Ausführung passen. Software-Emulation ist
ein möglicher, langsamerer Testweg und muss mit Zeit- und Ressourcenlimits
gemessen werden. `kvm` darf erst als Remote-Builder-Fähigkeit deklariert werden,
wenn `/dev/kvm` für den tatsächlichen Build-Benutzer verfügbar ist und ein
kleiner VM-Test funktioniert.
[NixOS-Handbuch: System Requirements, requiredFeatures.kvm und qemu.forceAccel](https://nixos.org/manual/nixos/stable/index.html).

Hetzners offizielle Cloud-FAQ bestätigt KVM als Hypervisor des Providers. Sie
belegt damit keinen verfügbaren KVM-Zugang innerhalb dieser Gast-VMs. Die
gezielte Recherche hat keine Cloud-Zusage für Nested Virtualization gefunden;
die separat gefundene Robot-vKVM-Dokumentation beschreibt ein anderes Produkt.
Die anschließende OS-Prüfung fand auf beiden VMs kein `/dev/kvm` und auf
Hephaestus keine CPU-Virtualisierungsflags. Ein schneller KVM-Test-Worker steht
damit aktuell nicht bereit.
[Hetzner: Cloud Technical FAQ](https://docs.hetzner.com/cloud/technical-details/faq).

Für GUI-Start- und Bedienprüfungen braucht man keine physische GPU: Xvfb stellt
einen X-Server mit einem Framebuffer im Arbeitsspeicher bereit. Mesa LLVMpipe
kann passende Grafikoperationen auf der CPU rendern. Screenshots, lesbarer
Renderer-Inhalt und konkrete Bedienaktionen können damit im Test überprüft
werden.
[X.Org: Xvfb](https://www.x.org/archive/X11R7.6/doc/man/man1/Xvfb.1.xhtml),
[Mesa: LLVMpipe](https://docs.mesa3d.org/drivers/llvmpipe.html).

Der aktuelle [GUI-Gate-Helfer](../scripts/weasel-update-gates.py) verwendet schon
ein eigenes Xvfb-Display, `--disable-gpu`, ein privates Profil und eine überprüfte
Zuordnung des Debug-Listeners zum gestarteten Prozess. Das prüft für T3 und
ChatGPT den Start bis zu einer brauchbaren frischen Oberfläche. Es ist kein
allgemeiner End-to-End-Test ihrer Modell-, Authentifizierungs- und Nutzerflüsse.
Solche Abläufe brauchen zusätzliche definierte Szenarien und Testkonten oder
Fixtures. Ein erfolgreicher Screenshot allein ist keine Funktionsprüfung.

Xvfb deckt außerdem keinen nativen Wayland-Compositor ab. Ein Desktop-Test mit
Hyprland oder Niri braucht eine eigene VM-/Headless-Konfiguration und passende
Bedienprüfungen. Keine dieser Testvarianten ersetzt auf der echten Maschine
NVIDIA-/DisplayLink-Tests, Monitor-Hotplug, Suspend, Audio, USB oder die
tatsächlichen VPN-/Netzpfade. Testgäste importieren die relevanten gemeinsamen
Module; ihre virtuelle Hardwarekonfiguration muss als Abweichung vom echten
Host sichtbar bleiben.

## Handoff für den eigenen Infrastrukturauftrag

1. Den reparierten, gepinnten Zugang und den dedizierten Proton-Agent erneut
   prüfen. Die authentifizierte Ressourceninventur ist vorhanden; Werte und
   Dienstlast können sich bis zum Infrastrukturauftrag ändern.
2. Zuerst eine eigene harte Speichergrenze, Free-Space-Admission und einen
   getesteten Lebenszyklus über den bestehenden deklarativen Verwaltungsweg
   planen und provisionieren. Erst danach die bestehende Null-Budget-Policy
   gezielt ändern und einen einzelnen begrenzten Nix-Worker einrichten. Mit
   einem kleinen Build beginnen. Einen
   minimalen VM-Test anschließend gesondert messen und die Builder-Fähigkeiten
   ausschließlich aus diesen Ergebnissen ableiten.
3. Je Job einen isolierten Checkout und einen exakten, überprüften Commit
   verwenden. Zielhost, Flake-Lock, Quellen, Evaluations-`drvPath`, gebauter
   System-Store-Pfad und Test-Receipts gemeinsam festhalten. Verschiedene
   Hosts erhalten getrennte Ergebnisse. Lokale Änderungen anderer Aufgaben
   bleiben erhalten.
4. Drift zunächst lesend erfassen: deklarativer Commit/Lock, aktiver
   System-Store-Pfad und relevante Dienstzustände. Erwartete dynamische Daten,
   Quelländerungen und imperative Konfigurationsänderungen unterscheiden.
   Ungeklärte Drift stoppt den Rollout dieses Hosts; sie wird nicht durch
   Überschreiben verborgen.
5. Vor Aktivierung pro Host eine passende Datensicherung erstellen und prüfen.
   Auf dem Laptop gehört der Home-Snapshot dazu; bei Serverdiensten können
   zusätzlich konsistente Datenbank- und Volume-Backups nötig sein. Eine
   vorherige NixOS-Generation ersetzt keine Sicherung veränderlicher Daten.
6. Zunächst einen Canary aktivieren. Der lokale Aktivierungshelfer prüft erneut
   den vereinbarten Ausgangszustand, aktiviert genau das getestete Artefakt,
   prüft Dienste und relevante Nutzerabläufe und führt ein Journal. Ein
   Fehler stoppt weitere Hosts; Systemrollback und Datenwiederherstellung
   sind getrennte, dokumentierte Vorgänge.
7. Builds dürfen parallel laufen. Deployments brauchen eine gemeinsame
   Koordination und pro Host einen exklusiven Aktivierungslock; eine aktive
   oder ungeklärte Transaktion blockiert die nächste. Offline-Hosts behalten
   Kandidaten zur erneuten Prüfung, ohne einen inzwischen veralteten Stand
   ungeprüft zu aktivieren.

Ein frischer Thread kann diesen Auftrag aus dieser Datei und
[daily-updates.md](daily-updates.md) übernehmen. Er muss den dann aktuellen
Quellstand, laufende Transaktionen und Zugänge erneut lesen. Dieses Handoff
ist kein Beleg, dass Worker, Flotteninventar, VM-Suite oder Server-Rollout schon
eingerichtet sind. Die automatisierte Aktivierung der bestehenden Routine
bleibt vorerst auf den ausdrücklich konfigurierten Laptop beschränkt.

## Quellen und lokale Belege

- [Nix: Remote Builds](https://nix.dev/manual/nix/2.28/advanced-topics/distributed-builds.html)
- [nix.dev: Distributed Builds](https://nix.dev/tutorials/nixos/distributed-builds-setup.html)
- [nix.dev: NixOS-Integrationstests](https://nix.dev/tutorials/nixos/integration-testing-using-virtual-machines.html)
- [NixOS-Handbuch](https://nixos.org/manual/nixos/stable/index.html)
- [X.Org: Xvfb](https://www.x.org/archive/X11R7.6/doc/man/man1/Xvfb.1.xhtml)
- [Mesa: LLVMpipe](https://docs.mesa3d.org/drivers/llvmpipe.html)
- [Hetzner: Cloud Technical FAQ](https://docs.hetzner.com/cloud/technical-details/faq)

Begrenzte Parallel-Receipts: `/tmp/weasel-vps-nix-docs-20261008.json`,
`/tmp/weasel-vps-nix-extract-20261008.json`,
`/tmp/weasel-vps-gui-kvm-docs-20261008.json`,
`/tmp/weasel-vps-hetzner-nested-20261008.json`. Die bestehenden API-Beobachtungen
stehen in `/tmp/hetzner-check-20261008.md`. Temporäre Receipts sind ergänzende
Session-Belege und müssen für einen späteren Auftrag gegebenenfalls erneut
erhoben werden.
