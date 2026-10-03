# PrÃ¼fung am 03.10.2026

## Echtes GerÃ¤t

- Windows COM3, USB VID 04b4 / PID 0003, Seriennummer IMS<anonymisiert>.
- HCI-Modultyp 6e bestÃ¤tigt iU891A-XL; Modul-ID <anonymisiert>.
- Firmware 1.0, Build 84, Datum 14.11.2024, Name WMBusGateway.
- UrsprÃ¼ngliche RAM-Konfiguration `000e0000003200a0bb0d00`: Empfang aus.
- C/T aktiviert und zurÃ¼ckgelesen: `030e0000003200a0bb0d00`.
- Automatische Portauswahl findet COM3.
- Ein Telegramm in 30 Sekunden; QDS, ID 12345678, Version 35, Typ 37
  (Radio converter), C / Format A, RSSI âˆ’82 dBm.
- HCI-CRC validiert. Fixture: `tests/fixtures/com3-qds.json`.
- Host hat Dongle-Uhr nicht synchronisiert; Dongle-Zeit ist hier veraltet.
- Firmware meldet Decryption Status 3 / Encryption Mode 255. Das allein beweist
  nicht, dass der ZÃ¤hler verschlÃ¼sselt sendet: proprietÃ¤re Formate kÃ¶nnen vom
  Gateway ebenfalls nicht unterstÃ¼tzt werden. Keine Verbrauchsinterpretation
  aus diesem Telegramm. Zuordnung zum konkreten Q water 5.5 noch unbestÃ¤tigt.
- Keine NVM-Konfiguration, kein Flashen, kein Funk-Senden. C/T bleibt im RAM aktiv.

## Software

Neun automatisierte Tests: CRC/Ping, SLIP-Recovery, RX-Metadaten, Standard-Records,
Puffer/Aliase, Simulation/HTTP/CSV, aktive Konfiguration, externer Decoderfehler,
echter Capture. Browser zeigt Simulation mit QDS und unbekanntem GerÃ¤t sowie
synthetischem Volumenwert und Telegrammliste.

Port 8080 war auf diesem Laptop nicht bindbar (Windows 10013); Vorschau auf 8765.
Bei Bedarf `start.bat --http-port 8765` verwenden.

## Erweiterung: Herstellerfilter und Qundis-Wasser

Der nachfolgende Live-Betrieb lieferte fÃ¼r dieselben Qundis-Adressen AMR- und
Walk-by-Telegramme. Das bisherige Verhalten ersetzte den GerÃ¤tewert durch das
neueste Telegramm und lÃ¶schte dabei einen zuvor erfolgreichen Stand. Jetzt bleiben
Stand und Empfangszeit erhalten, unabhÃ¤ngig von der Zeit des jÃ¼ngsten Telegramms.

Die aufgezeichneten Standard-Telegramme enthalten 0,529 mÂ³ (12345678),
0,229 mÂ³ (12345679) und 0,361 mÂ³ (12345680). Die entsprechenden Walk-by-Werte stimmen
bei zeitnahen Aufnahmen Ã¼berein; spÃ¤terer Walk-by-Empfang meldet 0,230 mÂ³ fÃ¼r
12345679. Ein neues Live-Telegramm nach dem Update zeigte 0,364 mÂ³ fÃ¼r 12345680.
Der Wasser-WalkByDataSet ist jetzt nach strikter Struktur- und BCD-PrÃ¼fung dekodierbar,
obwohl die Gateway-Firmware ihn als Modus 255 / Status 3 meldet. FrÃ¼here Aussage
â€žkeine Verbrauchsinterpretationâ€œ bezieht sich auf den ursprÃ¼nglichen Decoder.

Herstellerfilter: Mehrfachauswahl, atomare Persistenz in `data/settings.json`,
gefilterte GerÃ¤te-/Telegrammansicht und eigener gefilterter CSV-Export.
Rohdatenempfang und Gesamtexport enthalten weiterhin alle Hersteller.
14 Tests bestanden, einschlieÃŸlich echter AMR-/Walk-by-Telegramme, fehlerhafter
Layouts/BCD, verkÃ¼rzter Pakete, Stand-Erhalt und Filter-Persistenz/CSV.
Live-App auf Port 8766 mit vorher gesicherter und neu dekodierter Historie gestartet.

Offen: Displayabgleich, optionaler wmbusmeters-Build, Custom-C/T auf kompatibler
Firmware, Synology/Docker und Q caloric-Dekodierung.

## Repository / Docker

Zähler-IDs in Testaufnahmen und diesem Bericht sind vor Veröffentlichung anonymisiert;
HCI-Prüfsummen wurden für die geänderten Testdaten neu berechnet.
Compose für Radio und Simulation sowie HTTP-Healthcheck vorhanden.
Docker und Synology wurden auf diesem Windows-Host mangels Docker nicht ausgeführt.
