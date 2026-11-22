# Set up Wi-Fi

<p class="gb-meta">Step 4 of 5 · about 3 minutes</p>
<div class="gb-progress" aria-hidden="true"><span class="on"></span><span class="on"></span><span class="on"></span><span class="on"></span><span></span></div>

The display opens its own Wi-Fi so you can tell it your network and your server.

## Connect to the display

1. On your phone or computer, join the Wi-Fi **`GlanceBox-XXXX`** shown on the display. It has no password. If the display was set up before (for example because its saved network is gone), it asks for a password: enter your update password.
2. Most phones open the setup page by themselves. If not, open `http://192.168.4.1`.

<figure class="gb-figure" markdown>
![Sketch of the setup portal on a phone: Wi-Fi, server URL, update password and brightness](../../img/site/setup-portal.svg){ width="300" }
</figure>

## Fill in the form

1. Tap **Configure WiFi** and choose your 2.4 GHz network, then enter its password.
2. **Server URL:** the address from step 2, for example `http://192.168.1.50:8080`. Only `http://` works. The empty field shows `http://192.168.x.x:8090` as an example; use your server's IP address and port (8080 for the Docker server unless you changed it, 8090 for the Home Assistant add-on). If a field is invalid, the form comes back at once with the error, before the display tries your Wi-Fi: choose your network again and enter the passwords again.
3. **Update password:** a new password you choose, 8 to 32 characters, no umlauts. Enter it again in **Repeat update password**; the portal stores it only when both match. You need it for updates and for changing settings. The user name is always `admin`.
4. **Brightness:** 5 to 100 %. You can change it later with a slider.
5. Tap **Save**.

The display restarts, joins your Wi-Fi and shows its IP address, then the first page from your server.

!!! info "Do it right away"
    Until you save, the setup Wi-Fi is open to anyone nearby. More on this: [What to know about security](../setup.md#what-to-know-about-security).
