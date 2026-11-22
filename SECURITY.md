# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report them privately through GitHub: on the [Security tab](https://github.com/robinlanger/glancebox/security) choose **Report a vulnerability**. Only the maintainer sees the report. Please describe what is affected (firmware, server or a page), the version, and how to reproduce it.

Glance Box is a hobby project maintained by one person. You will usually get a first answer within a week. Once a fix is released, the advisory is published and you are credited if you want.

## Supported versions

Only the **latest release** gets security fixes. Firmware and server are released together with the same version number; please update both.

## Scope and known limits

Glance Box is built for a home network. These are design decisions, not vulnerabilities:

- The **server has no login**. Its preview page and frame API are open to everyone who can reach the port. Keep it inside your home network and do not forward the port to the internet.
- The **display talks plain HTTP**. Firmware updates and settings changes are protected by the update password (HTTP Basic auth, user `admin`), but the password is not encrypted on the network. `/status` is readable without a password.
- The device page answers only when it is opened by the device's IP address or its own device name (protection against DNS rebinding), and after five wrong passwords in a row it refuses every password for 30 seconds; the lock is shared by all clients, so someone on your network can keep you locked out, but cannot try passwords quickly.
- The setup portal (`GlanceBox-XXXX`) is an open Wi-Fi network only as long as no update password is set (first setup). After that its Wi-Fi uses WPA2 with the update password as the Wi-Fi password. It only opens when no Wi-Fi is configured or the saved network is unreachable, and changing an existing setup there also needs the current update password.
- Tokens for pages (Home Assistant, AI providers) belong in `.env`, not in `config.yaml`.

Reports that show a way around these protections, for example installing firmware without the update password, reading tokens from the server, or code execution through a page or a pushed value, are very welcome.
