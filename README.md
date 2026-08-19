[![LoxBerry Plugin](https://img.shields.io/badge/LoxBerry-Plugin-blue)](https://www.loxberry.de/)
[![GitHub release](https://img.shields.io/github/v/release/Woersty/LoxBerry-Plugin-Text2SIP?include_prereleases)](https://github.com/Woersty/LoxBerry-Plugin-Text2SIP/releases)
[![GitHub issues](https://img.shields.io/github/issues/Woersty/LoxBerry-Plugin-Text2SIP)](https://github.com/Woersty/LoxBerry-Plugin-Text2SIP/issues)
[![License](https://img.shields.io/github/license/Woersty/LoxBerry-Plugin-Text2SIP)](https://github.com/Woersty/LoxBerry-Plugin-Text2SIP/blob/master/LICENSE)

# LoxBerry Text2SIP

**Text2SIP** ist ein Plugin für den [LoxBerry](https://www.loxberry.de/), mit dem automatisch Telefonanrufe über **SIP** ausgelöst und dabei frei definierbare Sprachansagen wiedergegeben werden können.

Damit lassen sich Ereignisse aus **Loxone** oder anderen Systemen direkt als Telefonanruf signalisieren – beispielsweise Alarme, Störungen, Klingelereignisse oder Statusmeldungen.

---

## Funktionen

* 📞 Automatische Telefonanrufe über SIP
* 🔊 Sprachausgabe direkt während des Telefonanrufs
* 📝 Frei definierbare Ansagetexte
* 🔢 Mehrere unabhängig konfigurierbare Ansagen
* 🔄 Dynamische Übergabe von Text über `tts`
* 🏠 Übernahme von Werten aus dem Loxone Miniserver
* 🔢 DTMF/MFV-Auswertung während des Anrufs
* ✅ Bestätigung eines Anrufs über frei definierbare Telefontaste
* 🌐 Aufruf einer URL nach bzw. während eines Anrufs
* ⏱️ Einstellbare Wartezeiten vor und nach der Ansage
* ⌛ Einstellbares Anruf-Timeout
* 📴 Lokale Offline-Sprachausgabe mit **Kyutai Pocket-TTS**
* 🟢 Residenter Pocket-TTS-Server mit Watchdog und Statusanzeige
* 🎙️ Integration des LoxBerry **Text2Speech** Plugins
* 📡 Kommunikation mit Text2Speech über MQTT
* 🌍 Nutzung eines Text2Speech Plugins auf einem anderen LoxBerry über einen externen MQTT-Broker möglich
* 🔁 Fallback auf **Pocket-TTS**, falls Text2Speech nicht verfügbar ist
* 📋 Umfangreiches Logging zur Fehlersuche
* 🔄 Automatische Plugin-Updates über die LoxBerry Update-Funktion

---

## Typische Einsatzmöglichkeiten

Text2SIP eignet sich beispielsweise für:

* Alarmmeldungen
* Einbruch- oder Rauchmeldeanlagen
* technische Störungen
* Heizungs- oder Anlagenfehler
* Wassermeldungen
* Klingelsignalisierung
* Statusmeldungen
* Erinnerungen
* Fernbestätigung eines Ereignisses per Telefontaste

Beispiel:

> „Achtung. Im Keller wurde Wasser erkannt. Bitte bestätigen Sie den Alarm mit der Taste 2.“

---

## Funktionsweise

Der Ablauf eines Anrufs ist grundsätzlich:

```text
Loxone / HTTP-Aufruf
        │
        ▼
     Text2SIP
        │
        ├── Text erzeugen
        │
        ├── optional Text2Speech über MQTT
        │       └── bei Fehler: Pocket-TTS
        │
        ├── lokale Spracherzeugung: Pocket-TTS
        ├── Audio-Datei im RAM erzeugen
        │
        ▼
      pjsua
        │
        ▼
   SIP-Server / PBX
        │
        ▼
      Telefon
```

Seit Release **2026.08.10** verwendet Text2SIP für die SIP-Telefonie **pjsua**.

Die früher verwendete `sipcmd`-Implementierung wurde ersetzt.

### Offline-Sprachausgabe mit Pocket-TTS

Wenn das Text2Speech-Plugin deaktiviert ist, erzeugt Text2SIP die Ansage lokal mit **Pocket-TTS 2.1.0**. Das aktuell gewählte Sprachmodell läuft als residenter lokaler Server und bleibt zwischen den Anrufen im Speicher. Dadurch muss das Modell nicht für jede Ansage neu geladen werden.

Ein Watchdog prüft den lokalen Pocket-TTS-Server sofort nach dem Start und anschließend alle **120 Sekunden**. Laufzeitstatus und Fehlerprotokoll liegen ausschließlich unter `/run/shm/text2sip-pockettts/`. Das Watchdog-Fehlerlog wird bei mehr als **50 KiB** automatisch zurückgesetzt.

Pocket-TTS-Sprachmodelle werden bei Bedarf über die vorhandene Sprachauswahl geladen. Text2SIP verwendet die kompakten Modelle für Deutsch, Englisch, Spanisch, Italienisch und Portugiesisch. Für Französisch steht in Pocket-TTS 2.1.0 nur `french_24l` zur Verfügung; dieses Modell wird als einzige 24L-Ausnahme ebenfalls nur bei Auswahl von Frankreich heruntergeladen. Es bleibt immer nur ein Sprachmodell gleichzeitig resident im RAM.

In der Plugin-Oberfläche wird der Pocket-TTS-Status immer angezeigt, sobald **Text2SIP aktiviert** ist. Bei einem Fehler erscheint ein roter Statuspunkt und ein Button zum manuellen Neustart des residenten Servers.

---

## Voraussetzungen

Benötigt werden:

* ein laufender **LoxBerry**
* ein erreichbarer **SIP-Server / SIP-Proxy**
* ein dort eingerichteter SIP-Benutzer
* Netzwerkzugriff vom LoxBerry zum SIP-System

Geeignete SIP-Systeme sind beispielsweise:

* FRITZ!Box
* VoIP-Telefonanlagen
* SIP-PBX-Systeme
* andere SIP-kompatible Telefonserver

### Beispiel FRITZ!Box

In der FRITZ!Box kann unter:

```text
Telefonie
└── Telefoniegeräte
    └── Neues Gerät einrichten
        └── Telefon
            └── LAN/WLAN (IP-Telefon)
```

ein eigener SIP-Benutzer für Text2SIP eingerichtet werden.

Anschließend werden im Plugin unter anderem eingetragen:

* SIP-Benutzername
* SIP-Passwort
* SIP-Proxy / Registrar
* anzurufende Rufnummer

---

## Installation

1. Aktuelles Release herunterladen:

   [GitHub Releases](https://github.com/Woersty/LoxBerry-Plugin-Text2SIP/releases)

2. Im LoxBerry öffnen:

   ```text
   Plugin-Verwaltung
   ```

3. Das heruntergeladene ZIP als neues Plugin installieren.

4. Anschließend **Text2SIP** über die Plugin-Verwaltung öffnen.

5. SIP-Zugangsdaten und mindestens eine Ansage konfigurieren.

---

## Konfiguration einer Ansage

Für jede Ansage können separat Einstellungen vorgenommen werden.

Typische Parameter sind:

| Einstellung       | Beschreibung                               |
| ----------------- | ------------------------------------------ |
| Sprache           | Sprache der Sprachansage                   |
| Text              | Vorzulesender Text                         |
| SIP-Benutzer      | SIP-Benutzername                           |
| SIP-Passwort      | Passwort des SIP-Benutzers                 |
| SIP-Proxy         | Adresse des SIP-Servers                    |
| Zielrufnummer     | Nummer, die angerufen werden soll          |
| Pause vor Ansage  | Wartezeit nach Rufannahme                  |
| Pause nach Ansage | Wartezeit nach Wiedergabe                  |
| Timeout           | Maximale Anrufdauer                        |
| Result-URL        | URL für DTMF/MFV-Rückmeldungen             |
| Bestätigungstaste | Taste zum Bestätigen bzw. Beenden          |
| Miniserver-Wert   | Optionaler dynamischer Wert für die Ansage |

---

## Aufruf über HTTP

Eine konfigurierte Ansage kann beispielsweise über folgenden Aufruf gestartet werden:

```text
http://LOXBERRY/plugins/text2sip/index.php?mode=make_call&vg=1
```

Dabei bezeichnet:

```text
vg=1
```

die ID der gewünschten Ansage.

---

## Verwendung mit Loxone

In der **Loxone Config** kann ein virtueller Ausgang angelegt werden.

### Virtueller Ausgang

Adresse:

```text
http://LOXBERRY
```

### Befehl bei EIN

```text
/plugins/text2sip/index.php?mode=make_call&vg=1
```

`1` entspricht dabei der ID der gewünschten Text2SIP-Ansage.

Weitere Ansagen können entsprechend über andere IDs angesprochen werden.

---

## Dynamischer Text mit `tts`

Zusätzlicher Text kann direkt beim HTTP-Aufruf übergeben werden:

```text
http://LOXBERRY/plugins/text2sip/index.php?mode=make_call&vg=1&tts=Fenster%20im%20Wohnzimmer%20offen
```

Im Ansagetext kann dafür der Platzhalter

```text
##
```

verwendet werden.

Beispiel für einen im Plugin gespeicherten Text:

```text
Achtung. Folgende Meldung wurde erkannt: ##
```

HTTP-Aufruf:

```text
http://LOXBERRY/plugins/text2sip/index.php?mode=make_call&vg=1&tts=Fenster%20im%20Wohnzimmer%20offen
```

Ausgegeben wird:

```text
Achtung. Folgende Meldung wurde erkannt: Fenster im Wohnzimmer offen
```

Enthält der konfigurierte Text keinen `##`-Platzhalter, kann der über `tts` übergebene Text zusätzlich an die Ansage angehängt werden.

---

## Werte aus dem Loxone Miniserver

Text2SIP kann außerdem Werte direkt aus dem Miniserver abrufen.

Der Platzhalter

```text
##
```

wird dabei durch den ausgelesenen Wert ersetzt.

Beispiel:

```text
Die aktuelle Außentemperatur beträgt ## Grad.
```

Damit können dynamische Zustände und Messwerte telefonisch ausgegeben werden.

---

## DTMF / MFV

Während eines Telefonanrufs kann Text2SIP Tasteneingaben des Angerufenen auswerten.

Unterstützt werden:

```text
0 1 2 3 4 5 6 7 8 9 * #
```

Eine Taste kann beispielsweise als Bestätigung für einen Alarm definiert werden.

Beispiel:

```text
Alarm im Keller. Bitte bestätigen Sie mit Taste 2.
```

Nach der Eingabe kann Text2SIP den Anruf beenden und optional eine konfigurierte URL aufrufen.

Dadurch kann die Bestätigung wieder an **Loxone** oder ein anderes System übertragen werden.

---

## Text2Speech Integration

Text2SIP kann optional mit dem LoxBerry Plugin **Text2Speech** zusammenarbeiten.

Dadurch stehen – abhängig von der Text2Speech-Konfiguration – zusätzliche TTS-Dienste, Stimmen und Sprachen zur Verfügung.

Die Kommunikation zwischen Text2SIP und Text2Speech erfolgt über **MQTT**.

Text2Speech kann dabei:

* auf demselben LoxBerry laufen
* oder über einen externen MQTT-Broker auf einem anderen LoxBerry bereitgestellt werden

Ist die Text2Speech-Erzeugung nicht verfügbar, verfügt Text2SIP über eine Fallback-Logik für die lokale Spracherzeugung.

---

## SIP mit pjsua

Seit Version **2026.08.10** verwendet Text2SIP `pjsua` für den eigentlichen SIP-Anruf.

Das bietet insbesondere eine zuverlässigere SIP-Kommunikation und ein definiertes Binding an die LAN-Adresse des LoxBerry.

Dadurch werden unter anderem Probleme vermieden, bei denen bei vorhandenen Docker-Netzwerken eine falsche Netzwerkadresse für SIP verwendet wird.

Die passenden `pjsua`-Binaries werden vom Plugin abhängig von der verwendeten Architektur ausgewählt.

---

## Logging

Text2SIP schreibt seine Laufzeitinformationen in das LoxBerry Plugin-Log.

Das Log enthält unter anderem Informationen zu:

* TTS-Erzeugung
* MQTT-Kommunikation
* SIP-Verbindungsaufbau
* Zielrufnummer
* pjsua
* DTMF-Eingaben
* Fehlern und Fallbacks

Sensible Daten wie das SIP-Passwort werden im normalen Text2SIP-Log maskiert.

Bei Problemen sollte zunächst das Plugin-Log geprüft werden.

---

## Fehler melden

Fehler und Verbesserungsvorschläge bitte über GitHub Issues melden:

[GitHub Issues](https://github.com/Woersty/LoxBerry-Plugin-Text2SIP/issues)

Für eine Fehleranalyse sind hilfreich:

* verwendete LoxBerry-Version
* Text2SIP-Version
* verwendete Hardware / Architektur
* verwendeter SIP-Server
* relevante Auszüge aus dem Text2SIP-Log
* genaue Beschreibung des erwarteten und tatsächlichen Verhaltens

**Bitte keine Passwörter oder andere Zugangsdaten veröffentlichen.**

---

## Weitere Dokumentation

Weitere Informationen befinden sich im LoxBerry Wiki:

[LoxBerry Wiki – Text2SIP](https://www.loxwiki.eu/display/LOXBERRY/Text2SIP)

> Hinweis: Teile der Wiki-Dokumentation beziehen sich noch auf ältere Text2SIP-Versionen. Für aktuelle technische Änderungen sind die GitHub Releases und dieses Repository maßgeblich.

---

## Aktuelle Änderungen

### 2026.08.10

* `sipcmd` durch `pjsua` ersetzt
* MQTT-Anbindung optimiert
* Unterstützung interner und externer MQTT-Broker
* MQTT-Details für die Text2Speech-Anbindung ergänzt
* bisherige MQTT-Bridge-Funktion entfernt

---

## Projekt

**Text2SIP** wurde ursprünglich von **Christian Wörstenfeld** für den LoxBerry entwickelt.

Repository:

[Woersty/LoxBerry-Plugin-Text2SIP](https://github.com/Woersty/LoxBerry-Plugin-Text2SIP)

Das Projekt lebt von Beiträgen, Tests, Fehlermeldungen und Verbesserungen aus der LoxBerry-Community.

---

## Lizenz

Dieses Projekt steht unter der **Apache License 2.0**.

Weitere Informationen befinden sich in der Datei:

[LICENSE](https://github.com/Woersty/LoxBerry-Plugin-Text2SIP/blob/master/LICENSE)

---

## Links

* [LoxBerry](https://www.loxberry.de/)
* [Text2SIP Repository](https://github.com/Woersty/LoxBerry-Plugin-Text2SIP)
* [Releases](https://github.com/Woersty/LoxBerry-Plugin-Text2SIP/releases)
* [Issues](https://github.com/Woersty/LoxBerry-Plugin-Text2SIP/issues)
* [LoxBerry Wiki – Text2SIP](https://www.loxwiki.eu/display/LOXBERRY/Text2SIP)
