# QundisTester — iU891A-XL Wireless M-Bus Tester V1

Python 3.11+; Windows zuerst, gleiche Python-Anwendung für Linux/Synology.
Lokale Weboberfläche, kein Cloud-Dienst, keine Abrechnungssoftware.

## Windows starten

Python von python.org mit `pip` und `py`-Launcher installieren. Im Projektordner:

```bat
start.bat --simulate
```

Dann http://127.0.0.1:8080 öffnen. Für echten Empfang:

```bat
start.bat
start.bat --ports
start.bat --diagnose --port COM3
start.bat --port COM3 --mode ct
```

`start.bat` erstellt eine virtuelle Umgebung und installiert pyserial. Bei mehreren
Sticks muss `--port` angegeben werden. Die automatische Erkennung berücksichtigt
IMST-Namen und die am Testgerät beobachtete USB-Kennung 04b4:0003 / IMS-Seriennummer.
Andere COM-Geräte werden nicht wahllos angesprochen. Die HCI-Identifikation prüft
zusätzlich den Modultyp. Andere Firmware-/USB-Varianten ggf. explizit auswählen.

Modi: `ct` (Standard), `c`, `t`, `s`, `custom-ct`. Custom C/T wird nur auf explizite
Auswahl angefordert; abgelehnte Befehle erscheinen im Status. Nicht jeder Stick
mit alter Firmware unterstützt diesen Modus. Ein Modus empfängt nur die dazu
passenden Funktelegramme; „alle Geräte“ bedeutet ohne Adressfilter, nicht alle
Funkmodi gleichzeitig. Kein automatisches Flashen und keine Funkübertragung.

Beim Start: Identität/Firmware und aktive Konfiguration lesen, Scanmodus deaktivieren,
Adressfilter deaktivieren, RX-Benachrichtigungen aktivieren, RAM-Konfiguration setzen
und zurücklesen. NVM wird nicht verändert. Aktive Einstellungen bleiben bis zum
Neustart des Sticks bestehen. Fehler/Abziehen führen nach drei Sekunden zu erneutem
Verbindungsversuch. Der Diagnosebefehl liest nur. Andere Programme müssen COM3 freigeben.

## Daten und Oberfläche

Geräte werden nach Hersteller, ID, Version und Typ unterschieden. Unbekannte und
kurze Telegramme bleiben sichtbar. Die Anzeige des Modells ist ausdrücklich eine
Vermutung aus dem Header, keine gesicherte Produktidentifikation.
Ein Gerät gilt als zuletzt gesehen, sobald ein Telegramm eintrifft; längere Pausen
sind wegen der meterabhängigen Sendeintervalle kein sicherer Offline-Nachweis.
Die Seite aktualisiert jede Sekunde. Telegrammdetails enthalten vollständiges vom
Stick geliefertes WM-Bus-Hex, HCI-Hex inkl. FCS (ohne SLIP), Host-Zeit in UTC,
Dongle-Zeitstempel, RSSI, Modus/Format, Verschlüsselungsstatus und Decoderfelder.
Die Funk-CRCs werden durch die IMST-Firmware entfernt; das Hex ist daher kein
bitgenauer Mitschnitt der Funkstrecke. Dongle-Zeit wird nicht als synchron vorausgesetzt.

Letzte 100 Telegramme im RAM; bis zu 1000 zuletzt gesehene Geräte. Aliasnamen liegen
atomar gespeichert in `data/aliases.json`. App und Telegramme verwenden gemeinsam
`data/tester.log`, maximal ca. 10 MB (5 Dateien mit je ca. 2 MB). CSV exportiert die
letzten 100 Telegramme einschließlich Rohdaten und JSON-Decoderfeldern. Beim Neustart
bleiben Aliasnamen und Logs erhalten; die RAM-Historie beginnt neu. Beschädigte
Aliasdateien verursachen einen sichtbaren Startfehler statt stillen Datenverlusts.

### Herstellerfilter und letzter dekodierter Stand

Checkboxen erlauben einen oder mehrere Hersteller (z.B. QDS für Qundis).
Die Auswahl wird automatisch und atomar in `data/settings.json` gespeichert:

```json
{"manufacturers": ["QDS", "HAG"]}
```

Leere Liste / „Alle Hersteller“ zeigt alle Geräte. Der Filter betrifft Geräte,
Telegrammliste und „CSV mit Filter“. „CSV aller Telegramme“ enthält weiterhin alle
100 gespeicherten Telegramme. Empfang, Ringpuffer und Logs werden nicht gefiltert.
Neue Hersteller erscheinen automatisch als zusätzliche Auswahl.

Die Übersicht bewahrt den letzten erfolgreich dekodierten Stand mit Empfangszeit.
Ein neueres Telegramm ohne Verbrauchsdaten löscht ihn nicht. „Zuletzt gesehen“
bezeichnet dagegen das jüngste Telegramm. Einzeltelegramme und CSV enthalten nur
den dort tatsächlich dekodierten Wert, keinen hineinkopierten älteren Stand.
Dieser Stand-Cache liegt wie die Gerätehistorie nur im RAM.

## Decoder / Qundis

`receiver.py` liefert Rohtelegramme; `decoder.py` ist unabhängig von der Hardware.
Der interne Decoder liest Header sowie konservativ unterstützte DIF/VIF-Records
mit CI 78/7A/72. Aktueller Volumenwert nur aus eindeutig aktuellem Standard-Record
(keine historischen Speicher-/Tarifwerte). Proprietäre Walk-by-Datensätze und
kompakte/erweiterte Transportformate bleiben mit Rohdaten sichtbar.
Zusätzlich wird das hier empfangene unverschlüsselte Qundis-Wasser-WalkByDataSet
erkannt. Der Decoder validiert Header, eingebettete Adresse, Blocklänge,
Wasserkennung, feste Layoutbytes, BCD-Verbrauchsbytes und den nachfolgenden
Datumzeitrecord. Unpassende/verkürzte Varianten liefern keinen Verbrauchswert.
Die Gateway-Meldung „unsupported“, Modus 255, verhindert bei diesem strukturell
validierten Klartextformat nicht die Dekodierung. Bekannte Encryption Modes
werden dadurch nicht übergangen. Beide Datensätze der drei empfangenen Qundis-IDs
sind in Regressionstests gesichert. Ein Displayabgleich bleibt sinnvoll.
Die Simulation enthält **synthetische QDS-Standardrecords**; anonymisierte Aufnahmen liegen
zusätzlich unter `tests/fixtures/qundis-water-live.json`.
Q caloric 5.5 P3 AMR und WB HC5xxx8 sind spätere Ziele; Header-/Rohanzeige funktioniert
bereits, proprietäre Verbrauchsdekodierung ist nicht implementiert.

Optional einen separat installierten aktuellen wmbusmeters-Build einsetzen:

```bat
start.bat --wmbusmeters C:\Tools\wmbusmeters.exe
```

Der Aufruf folgt dem dokumentierten Hex-/auto-/NOKEY-CLI. Unter Linux analog mit
`--wmbusmeters /usr/bin/wmbusmeters`. JSON erscheint zusätzlich im Telegramm;
`total_m3` wird als ungeprüfter externer Wert angezeigt. Das Programm wird mit
Argumentliste ohne Shell gestartet, Timeout 5 Sekunden; Fehler lassen Rohdaten
sichtbar. wmbusmeters wird nicht mitgeliefert und dessen Integration wurde hier
mangels installiertem Binary nicht gegen einen echten Build geprüft. Die synchrone
externe Dekodierung kann bei hoher Verkehrsdichte den Empfang verzögern; für maximale
Capture-Leistung den internen Decoder verwenden. Decoder-Auswahl `auto` dient Tests.

## Tests

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Prüft offizielle Ping-/CRC-Vektoren, SLIP-Fragmente/Escaping/Fehlererholung,
RAM-Konfiguration, Paketmetadaten, konservative Volumendekodierung, unbekannte
Geräte, 100er-Ringpuffer, Alias-Persistenz, Simulation, HTTP und CSV.

## Synology / Docker (DSM 7 / Container Manager)

Das Projekt baut ein lokales Docker-Image fuer Linux amd64 und arm64. Ein
passendes NAS mit Container Manager/Docker ist Voraussetzung. Der angeschlossene
USB-Stick muss vom DSM-Host als serielles Geraet erkannt werden: Ein Container
kann einen fehlenden DSM-USB-Treiber nicht ersetzen. Ein am Windows-Laptop
angeschlossener Stick steht dem NAS nicht automatisch zur Verfuegung.

### 1. Projekt auf der Synology ablegen

Repository als ZIP herunterladen und nach `/volume1/docker/QundisTester`
entpacken, oder per SSH (falls Git vorhanden):

```sh
git clone https://github.com/CBerauer/QundisTester.git /volume1/docker/QundisTester
cd /volume1/docker/QundisTester
cp .env.example .env
mkdir -p data
```

In `.env` `BIND_ADDRESS` auf die LAN-IP deiner Synology setzen, z.B.
`192.168.178.20`. Danach ist die Seite unter `http://192.168.178.20:8766/`
erreichbar. Der Standard `127.0.0.1` erlaubt nur lokalen Zugriff auf dem NAS.
Die App hat keine Anmeldung; nur im vertrauenswuerdigen Heimnetz betreiben und
keine Router-Portfreigabe einrichten.

### 2. Zuerst ohne Funk testen

Im Container Manager ein Projekt aus diesem Ordner mit
`compose.simulation.yaml` erstellen und bauen/starten. Alternativ per SSH:

```sh
docker compose -f compose.simulation.yaml up -d --build
docker compose -f compose.simulation.yaml logs --tail=50
docker compose -f compose.simulation.yaml down
```

Simulation verwendet `data-simulation`, damit synthetische Daten getrennt bleiben.
Bei aelteren DSM-Installationen lautet der Befehl ggf. `docker-compose`.

### 3. iU891A-XL auf dem NAS anschliessen

Per SSH den vorhandenen Geraetepfad pruefen:

```sh
ls -l /dev/ttyACM* /dev/ttyUSB* /dev/serial/by-id/*
```

Nicht jeder der Pfade muss existieren. Den tatsaechlich zum IMST-Stick gehoerenden
Pfad in `.env` als `SERIAL_DEVICE` eintragen. Typisch ist `/dev/ttyACM0` oder
`/dev/ttyUSB0`; wenn vorhanden ist ein stabiler `/dev/serial/by-id/...`-Pfad vorzuziehen.
Falls kein Geraet erscheint, zuerst DSM-Treiberunterstuetzung fuer dein NAS-Modell
klaeren. Die App installiert keine Kernelmodule.

Im Container Manager das Projekt mit `compose.yaml` bauen/starten, oder:

```sh
docker compose up -d --build
docker compose logs --tail=50
```

Compose reicht nur das ausgewaehlte USB-Geraet durch (kein privileged-Modus),
mappt es intern auf `/dev/ttyMeter` und startet standardmaessig C/T-Empfang.
Modus in `.env`: `RADIO_MODE=ct`, alternativ `c`, `t`, `s` oder explizit `custom-ct`.
Der Container laeuft fuer unkomplizierten USB-/Ordnerzugriff als root; nur das
Projekt-Datenverzeichnis ist eingebunden. Bei Abziehen versucht die App erneut
zu verbinden. Falls sich der Host-Geraetepfad aendert, `.env` aktualisieren und
Container mit `docker compose up -d --force-recreate` neu erstellen.

### Betrieb und Aktualisierung

`data/` enthaelt Aliase, Herstellerfilter und rotierende Logs. Diesen Ordner sichern.
Die letzten 100 Telegramme und der Stand-Cache bleiben RAM-Daten und beginnen nach
einem Neustart neu. `restart: unless-stopped` startet den Container nach einem
NAS-Neustart wieder, sofern das USB-Geraet verfuegbar ist.

Der Docker-Healthcheck prueft die HTTP-API, nicht den Funkempfang; ein ruhiger Zaehler
oder nicht verbundener Stick macht den Webserver nicht automatisch unhealthy.
Empfangsstatus/Firmware werden in der Oberflaeche angezeigt. Ein unhealthy-Status
allein loest bei Docker Compose keinen automatischen Neustart aus.

```sh
git pull --ff-only
docker compose up -d --build
docker compose down
```

GitHub Actions prueft Python-Tests und Docker-Builds fuer amd64/arm64 bei jedem Push.
Docker und echter Synology-USB-Empfang wurden auf dem Entwicklungsrechner mangels
Docker/NAS-Zugriff nicht ausgefuehrt. Die Hardwarekompatibilitaet ist erst auf deinem
NAS nachweisbar. Das Image enthaelt pyserial, aber kein wmbusmeters-Binary.

## Quellen / Stand 03.10.2026

- [IMST HCI-Spezifikation 2.4, 03.06.2026](https://wireless-solutions.de/data/Wireless%20Solutions/Downloads/iU891A-XL-wM-Bus/WM_Bus_Gateway_HCI_Protocol_Specification.pdf)
- [IMST Produkt und Downloads inkl. API-Beispiele](https://wireless-solutions.de/products/wm-bus-iu891a-xl.html)
- [wmbusmeters CLI / aktueller Quellcode](https://github.com/wmbusmeters/wmbusmeters)
- [2026 iU891A-Treiberprobleme #1945](https://github.com/wmbusmeters/wmbusmeters/issues/1945)
- [Q water 5.5 Parsing #2012](https://github.com/wmbusmeters/wmbusmeters/issues/2012)
- [qwaterv2: WalkByDataSet-Layout und Wasserkennung](https://github.com/wmbusmeters/wmbusmeters/blob/master/drivers/src/qwaterv2.xmq)

Der aktuelle wmbusmeters-Quellcode enthält Custom-C/T sowie Korrekturen an der
Frame-Verarbeitung. Ein beliebiger veröffentlichter Build muss diese nicht enthalten.
Daher direkte HCI-Anbindung als Windows-V1, wmbusmeters optional als Decoder.
Implementierung aus der Protokollspezifikation; kein wmbusmeters-Treibercode kopiert.
