# WLAN einrichten

<p class="gb-meta">Schritt 4 von 5 · etwa 3 Minuten</p>
<div class="gb-progress" aria-hidden="true"><span class="on"></span><span class="on"></span><span class="on"></span><span class="on"></span><span></span></div>

Das Display öffnet ein eigenes WLAN, damit du ihm dein Netz und deinen Server nennen kannst.

## Mit dem Display verbinden

1. Verbinde Handy oder Rechner mit dem WLAN **`GlanceBox-XXXX`**, das auf dem Display steht. Es hat kein Passwort. War das Display schon einmal eingerichtet (etwa weil sein gespeichertes Netz weg ist), fragt es nach einem Passwort: Gib dein Update-Passwort ein.
2. Die meisten Handys öffnen die Einrichtungsseite von selbst. Sonst öffne `http://192.168.4.1`.

<figure class="gb-figure" markdown>
![Skizze des Einrichtungsportals am Handy: WLAN, Server-URL, Update-Passwort und Helligkeit](../../img/site/setup-portal.svg){ width="300" }
</figure>

## Das Formular ausfüllen

1. Tipp auf **Configure WiFi**, wähl dein 2,4-GHz-Netz und gib sein Passwort ein.
2. **Server URL:** die Adresse aus Schritt 2, zum Beispiel `http://192.168.1.50:8080`. Nur `http://` funktioniert. Das leere Feld zeigt `http://192.168.x.x:8090` als Beispiel; nimm die IP-Adresse und den Port deines Servers (8080 beim Docker-Server, solange du nichts geändert hast, 8090 beim Home-Assistant-Add-on). Ist ein Feld ungültig, kommt das Formular sofort mit dem Fehler zurück, bevor das Display dein WLAN versucht: Wähl dein Netz noch einmal aus und gib die Passwörter neu ein.
3. **Update password:** ein neues Passwort deiner Wahl, 8 bis 32 Zeichen, ohne Umlaute. Gib es unter **Repeat update password** noch einmal ein; das Portal speichert es nur, wenn beide gleich sind. Du brauchst es für Updates und zum Ändern der Einstellungen. Der Benutzername ist immer `admin`.
4. **Brightness:** 5 bis 100 %. Später stellst du sie bequem mit einem Regler ein.
5. Tipp auf **Save**.

Das Display startet neu, verbindet sich mit deinem WLAN, zeigt seine IP-Adresse und dann die erste Seite von deinem Server.

!!! info "Gleich erledigen"
    Bis du speicherst, ist das Einrichtungs-WLAN für jeden in der Nähe offen. Mehr dazu: [Was du zur Sicherheit wissen solltest](../setup.md#was-du-zur-sicherheit-wissen-solltest).
