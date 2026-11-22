#include "i18n.h"

#include "arduino_str.h"

#include "web_util.h"

namespace {
#define GB_STR(name, text) const char name[] PROGMEM = text;

// English
GB_STR(en0, "Status")
GB_STR(en1, "Uptime")
GB_STR(en2, "Signal")
GB_STR(en3, "Frames")
GB_STR(en4, "Last frame")
GB_STR(en5, "Safe mode")
GB_STR(en6, "Failed boots")
GB_STR(en7, "Settings")
GB_STR(en8, "Server URL")
GB_STR(en9, "Brightness (%)")
GB_STR(en10, "New update password (empty = keep)")
GB_STR(en11, "Save")
GB_STR(en12, "Saved.")
GB_STR(en13, "Changes need the update password (user admin).")
GB_STR(en14, "Firmware update")
GB_STR(en15, "MD5 of the .bin file")
GB_STR(en16, "Upload")
GB_STR(en17, "Device")
GB_STR(en18, "Restart")
GB_STR(en19, "Reset settings and Wi-Fi")
GB_STR(en20, "Really reset settings and Wi-Fi?")
GB_STR(en21, "Restarting...")
GB_STR(en22, "Reset done. The device restarts and opens the setup portal.")
GB_STR(en23, "Back")
GB_STR(en24, "Server URL: https is not supported, use http://")
GB_STR(en25, "Server URL: only http:// is supported")
GB_STR(en26, "Server URL: host is missing")
GB_STR(en27, "Server URL is too long")
GB_STR(en28, "Password must have at least 8 characters")
GB_STR(en29, "Password must have at most 32 characters")
GB_STR(en30, "Password: use printable ASCII characters only")
GB_STR(en31, "Brightness must be a number from 5 to 100")
GB_STR(en32, "Saving failed")
GB_STR(en33, "Current update password is wrong")
GB_STR(en34, "Reset failed: settings could not be erased")
GB_STR(en35, "Safe mode")
GB_STR(en36, "The device failed to boot several times and is running the minimal safe firmware. Upload a working firmware (.bin) below, or try the normal firmware again.")
GB_STR(en37, "Boot normal firmware")
GB_STR(en38, "Night from")
GB_STR(en39, "Night until")
GB_STR(en40, "Night brightness (%)")
GB_STR(en41, "Same times = night mode off. 0 % = completely dark.")
GB_STR(en42, "Local time")
GB_STR(en43, "Night")
GB_STR(en44, "Night times must be HH:MM")
GB_STR(en45, "Night brightness must be a number from 0 to 100")
GB_STR(en46, "Display")
GB_STR(en47, "Server")
GB_STR(en48, "Details")
GB_STR(en49, "Night mode")
GB_STR(en50, "From")
GB_STR(en51, "Until")
GB_STR(en52, "Change password")
GB_STR(en53, "Change")
GB_STR(en54, "Off")
GB_STR(en55, "Online")
GB_STR(en56, "Offline")
GB_STR(en57, "Excellent")
GB_STR(en58, "Good")
GB_STR(en59, "Fair")
GB_STR(en60, "Weak")
GB_STR(en61, "Up for")
GB_STR(en62, "Connection")
GB_STR(en63, "Wi-Fi")
GB_STR(en64, "Undo")
GB_STR(en65, "Not saved: the update password is needed (user admin).")
GB_STR(en66, "Password changed. Your browser will ask for the new one.")
GB_STR(en67, "Update installed. The device restarts.")
GB_STR(en68, "Uploading...")
GB_STR(en69, "Address")
GB_STR(en70, "{} ago")
GB_STR(en71, "d")
GB_STR(en72, "Firmware file (.bin)")
GB_STR(en73, "Brightness")
GB_STR(en74, "Brightness at night")
GB_STR(en75, "Last image")
GB_STR(en76, "Images shown")
GB_STR(en77, "Server URL: no spaces, quotes or special chars")
GB_STR(en78, "Too many wrong passwords. Try again in {} s.")

// German
GB_STR(de0, "Status")
GB_STR(de1, "Laufzeit")
GB_STR(de2, "Signal")
GB_STR(de3, "Frames")
GB_STR(de4, "Letzter Frame")
GB_STR(de5, "Safe Mode")
GB_STR(de6, "Fehlstarts")
GB_STR(de7, "Einstellungen")
GB_STR(de8, "Server-URL")
GB_STR(de9, "Helligkeit (%)")
GB_STR(de10, "Neues Update-Passwort (leer = unverändert)")
GB_STR(de11, "Speichern")
GB_STR(de12, "Gespeichert.")
GB_STR(de13, "Änderungen brauchen das Update-Passwort (Benutzer admin).")
GB_STR(de14, "Firmware-Update")
GB_STR(de15, "MD5 der .bin-Datei")
GB_STR(de16, "Hochladen")
GB_STR(de17, "Gerät")
GB_STR(de18, "Neustart")
GB_STR(de19, "Einstellungen und WLAN zurücksetzen")
GB_STR(de20, "Einstellungen und WLAN wirklich zurücksetzen?")
GB_STR(de21, "Neustart ...")
GB_STR(de22, "Zurückgesetzt. Das Gerät startet neu und öffnet das Einrichtungsportal.")
GB_STR(de23, "Zurück")
GB_STR(de24, "Server-URL: https wird nicht unterstützt, bitte http://")
GB_STR(de25, "Server-URL: nur http:// wird unterstützt")
GB_STR(de26, "Server-URL: Host fehlt")
GB_STR(de27, "Server-URL ist zu lang")
GB_STR(de28, "Passwort braucht mindestens 8 Zeichen")
GB_STR(de29, "Passwort darf höchstens 32 Zeichen haben")
GB_STR(de30, "Passwort: nur druckbare ASCII-Zeichen")
GB_STR(de31, "Helligkeit muss eine Zahl von 5 bis 100 sein")
GB_STR(de32, "Speichern fehlgeschlagen")
GB_STR(de33, "Aktuelles Update-Passwort ist falsch")
GB_STR(de34, "Zurücksetzen fehlgeschlagen: Einstellungen nicht gelöscht")
GB_STR(de35, "Abgesicherter Modus")
GB_STR(de36, "Das Gerät ist mehrfach nicht hochgefahren und läuft mit der minimalen Notfall-Firmware. Lade unten eine funktionierende Firmware (.bin) hoch oder versuche es noch einmal mit der normalen Firmware.")
GB_STR(de37, "Normale Firmware starten")
GB_STR(de38, "Nacht von")
GB_STR(de39, "Nacht bis")
GB_STR(de40, "Helligkeit nachts (%)")
GB_STR(de41, "Gleiche Zeiten = Nachtmodus aus. 0 % = ganz dunkel.")
GB_STR(de42, "Uhrzeit")
GB_STR(de43, "Nacht")
GB_STR(de44, "Nachtzeiten müssen im Format HH:MM sein")
GB_STR(de45, "Helligkeit nachts muss eine Zahl von 0 bis 100 sein")
GB_STR(de46, "Anzeige")
GB_STR(de47, "Server")
GB_STR(de48, "Details")
GB_STR(de49, "Nachtmodus")
GB_STR(de50, "Von")
GB_STR(de51, "Bis")
GB_STR(de52, "Passwort ändern")
GB_STR(de53, "Ändern")
GB_STR(de54, "Aus")
GB_STR(de55, "Online")
GB_STR(de56, "Offline")
GB_STR(de57, "Sehr gut")
GB_STR(de58, "Gut")
GB_STR(de59, "Mäßig")
GB_STR(de60, "Schwach")
GB_STR(de61, "Läuft seit")
GB_STR(de62, "Verbindung")
GB_STR(de63, "WLAN")
GB_STR(de64, "Rückgängig")
GB_STR(de65, "Nicht gespeichert: Das Update-Passwort wird gebraucht (Benutzer admin).")
GB_STR(de66, "Passwort geändert. Der Browser fragt gleich nach dem neuen.")
GB_STR(de67, "Update installiert. Das Gerät startet neu.")
GB_STR(de68, "Wird hochgeladen ...")
GB_STR(de69, "Adresse")
GB_STR(de70, "vor {}")
GB_STR(de71, "T")
GB_STR(de72, "Firmware-Datei (.bin)")
GB_STR(de73, "Helligkeit")
GB_STR(de74, "Helligkeit nachts")
GB_STR(de75, "Letztes Bild")
GB_STR(de76, "Bilder gezeigt")
GB_STR(de77, "Server-URL: keine Leerzeichen, Anführungszeichen oder Sonderzeichen")
GB_STR(de78, "Zu viele falsche Passwörter. In {} s erneut versuchen.")

#undef GB_STR

const char* const kEn[] PROGMEM = {en0, en1, en2, en3, en4, en5, en6, en7, en8, en9, en10, en11, en12, en13, en14, en15, en16, en17, en18, en19, en20, en21, en22, en23, en24, en25, en26, en27, en28, en29, en30, en31, en32, en33, en34, en35, en36, en37, en38, en39, en40, en41, en42, en43, en44, en45, en46, en47, en48, en49, en50, en51, en52, en53, en54, en55, en56, en57, en58, en59, en60, en61, en62, en63, en64, en65, en66, en67, en68, en69, en70, en71, en72, en73, en74, en75, en76, en77, en78};
const char* const kDe[] PROGMEM = {de0, de1, de2, de3, de4, de5, de6, de7, de8, de9, de10, de11, de12, de13, de14, de15, de16, de17, de18, de19, de20, de21, de22, de23, de24, de25, de26, de27, de28, de29, de30, de31, de32, de33, de34, de35, de36, de37, de38, de39, de40, de41, de42, de43, de44, de45, de46, de47, de48, de49, de50, de51, de52, de53, de54, de55, de56, de57, de58, de59, de60, de61, de62, de63, de64, de65, de66, de67, de68, de69, de70, de71, de72, de73, de74, de75, de76, de77, de78};
static_assert(sizeof(kEn) / sizeof(kEn[0]) == static_cast<size_t>(Msg::Count), "kEn size");
static_assert(sizeof(kDe) / sizeof(kDe[0]) == static_cast<size_t>(Msg::Count), "kDe size");
}  // namespace

Lang langFromHeader(const String& acceptLanguage) {
  return gb::prefersGerman(strOrEmpty(acceptLanguage)) ? Lang::De : Lang::En;
}

const __FlashStringHelper* tr(Lang lang, Msg msg) {
  const char* const* table = lang == Lang::De ? kDe : kEn;
  return reinterpret_cast<const __FlashStringHelper*>(
      pgm_read_ptr(&table[static_cast<size_t>(msg)]));
}

Msg msgForError(const std::string& code, bool isPassword) {
  if (code == "https_unsupported") return Msg::ErrHttps;
  if (code == "unsupported_scheme") return Msg::ErrScheme;
  if (code == "empty_host") return Msg::ErrEmptyHost;
  if (code == "too_short") return Msg::ErrPwShort;
  if (code == "invalid_chars") return isPassword ? Msg::ErrPwChars : Msg::ErrUrlChars;
  if (code == "too_long") return isPassword ? Msg::ErrPwLong : Msg::ErrTooLong;
  return Msg::ErrSaveFailed;
}
