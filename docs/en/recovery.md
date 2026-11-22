# Recovery

What to do when something goes wrong: a device page that refuses access, safe mode after a bad update, the boot counter, and the serial route as the last resort.

## The device page refuses access

- **Open the device page by its IP address**, for example `http://192.168.1.50/`, or in safe mode's own network `http://192.168.4.1/`. The device answers only to its IP address (and, as an aside, to its built-in device name of the form `ESP-XXXXXX`); for any other name, for example one your router added, it answers `open this page by the device's IP address`. This protects it against websites that try to reach it through a fake name (DNS rebinding).
- **After five wrong passwords in a row the device locks the password check for 30 seconds**, for everyone. During that time it refuses even the correct password and says how many seconds are left (HTTP status 429). Wait, then enter the correct password. The first wrong password after a lock locks it again.

## Safe mode

### When it starts

The firmware counts every boot. It counts as healthy after **60 seconds of uptime with Wi-Fi connected and the web server running**, and the counter returns to 0. If **3 boots in a row** do not get there (crash, hang, endless restarts), the next boot starts safe mode. A server that cannot be reached does **not** trigger safe mode.

Safe mode has almost no code: Wi-Fi, a minimal web server with one update page, the update function and `/status`. It does not decode pictures and does not ask the server for frames.

### What you see

The display shows **"Safe mode"** with the firmware version, the number of failed boots and the address `http://<ip>/update` once Wi-Fi is connected. If the saved Wi-Fi cannot be reached within 20 seconds, safe mode opens its own network `GlanceBox-XXXX` as well (no password); join it and use the address `192.168.4.1`. If the device has no valid update password in its settings, safe mode first shows the setup portal, see [Setup](setup.md).

`http://<ip>/status` shows `"safe_mode": true`.

### Leaving safe mode

Safe mode serves a small page at `http://<ip>/` and `http://<ip>/update` (in German or English, depending on your browser). It has the update form and two buttons. The page is public, but every action asks for the user `admin` and your update password.

1. **Upload a working firmware** (the previous release is a good choice, or the newest one). In the browser, open the page, paste the MD5 (the first word of the release's `.md5` file, see [Updating](updating.md#before-you-update)), choose the `.bin` file and press **Upload**. The browser asks for `admin` and your update password. Alternatively use curl:

   ```sh
   curl -u admin:<password> -F md5=<md5> -F firmware=@glancebox-ultra-<version>.bin http://<ip>/update
   ```

   After the upload the device restarts into the new firmware with a clean counter. Details of the command are in [Updating](updating.md#update-with-curl).
2. **Or boot the normal firmware again**, for example if safe mode was triggered by something temporary. Press **Boot normal firmware** on the page, or use curl:

   ```sh
   curl -u admin:<password> -X POST http://<ip>/boot-normal
   ```

   The next boot runs the normal firmware. If it fails again three times, you are back in safe mode.

A plain restart (the **Restart** button, `POST /restart`) does **not** leave safe mode.

## The boot counter and power cycles

The counter lives in a memory area that survives restarts. At every start the firmware also checks **why** the chip started: after power-on it always starts counting from scratch, even if the memory survived a short power loss. So:

- Unplugging the power and plugging it in again **resets the counter**. After a power cycle the device starts the normal firmware again and gets three new tries. A signal on the chip's reset pin (for example from a serial adapter) counts the same way.
- Crashes, watchdog resets and restarts by software (the **Restart** button, an update) keep the counter. Three of them within a minute each count as failed boots.
- If the firmware keeps failing and you power-cycle each time, you will never reach safe mode on your own. In that case upload a good firmware (for example right after a power cycle, within the first minute, as soon as `/update` answers) or use the serial route below.

## Serial flashing

The last resort. It works even if the firmware is completely broken, because it talks to the chip's built-in bootloader. You need the same adapter as for the backup, see [Flashing](flashing.md#step-1-back-up-the-stock-firmware-optional).

### What you need

- A 3.3 V USB-to-serial adapter: a Raspberry Pi Pico with `debugprobe` (GP4 = TX, GP5 = RX) or a CH340 module set to 3.3 V.
- `esptool` (`pip install esptool`).
- The wiring from [Flashing](flashing.md#wiring): GND to GND, adapter TX to ESP RX, adapter RX to ESP TX. **Cross TX and RX.**

### Pad labels and photo (pending verification on real hardware)

> [!NOTE]
> **Pending verification on real hardware.** A photo of the Ultra board with the pad labels will be added here after the maintainer has opened a device. Until then, no board-specific positions are given. The signals you need are always on the ESP-12F module itself: GND, TX (TXD0), RX (RXD0) and GPIO0. Use the module's datasheet pinout, look at them with a multimeter's continuity mode against the module's pins, and only solder or clip to a pad when you are sure which signal it carries. If you are not sure, do not guess: ask in an issue.

### Putting the device into flash mode

1. Disconnect the USB cable from the display.
2. Connect the wires: GND, TX, RX and **GPIO0 to GND**.
3. Plug the display's own USB-C cable in. Do not power the display from the adapter.
4. Check the connection: `esptool.py --port <port> chip_id` shows `Chip is ESP8266`. If it cannot connect, power-cycle with GPIO0 held at GND again and check TX and RX.

### Flashing the firmware

```sh
esptool.py --port <port> -b 115200 write_flash 0x0 glancebox-ultra-<version>.bin
```

Afterwards remove the GPIO0 wire and power-cycle the display (unplug, plug in). It starts the new firmware and opens the setup portal if no settings are stored. If settings are still stored and the saved Wi-Fi cannot be reached, the setup portal opens too, and its Wi-Fi `GlanceBox-XXXX` asks for a password: enter your update password. The exact flash command, including flash parameters, is pending the maintainer's own serial test.

## Restoring the backup

If you made a backup as described in [Flashing](flashing.md#making-and-checking-the-backup), this returns the display to the stock firmware, including its activation:

1. Put the device into flash mode as above (GPIO0 to GND at power-up).
2. Optionally erase first: `esptool.py --port <port> erase_flash`.
3. Write the backup:

   ```sh
   esptool.py --port <port> -b 115200 write_flash 0 backup1.bin
   ```

4. Remove the GPIO0 wire, power-cycle the display. It starts the stock firmware as before, with your old Wi-Fi settings.

If you check `shasum -a 256 backup1.bin` first and it matches the hash you noted down, you know the file is intact.

Without a backup there is no way back to stock firmware. You can always flash Glance Box again.
