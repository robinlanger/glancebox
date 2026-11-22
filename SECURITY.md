# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report them privately through GitHub: on the [Security tab](https://github.com/robinlanger/glancebox/security) choose **Report a vulnerability**. Only the maintainer sees the report. Please describe what is affected (firmware, server or a page), the version, and how to reproduce it.

Glance Box is a hobby project maintained by one person. You will usually get a first answer within a week. Once a fix is released, the advisory is published and you are credited if you want.

## Supported versions

Only the **latest release** gets security fixes. Firmware and server are released together with the same version number; please update both.

## Checking a release

Every release image and firmware file carries a signed build provenance attestation from the
release workflow. With the [GitHub CLI](https://cli.github.com/) you can check that a file was
built by this repository:

```sh
gh attestation verify oci://ghcr.io/robinlanger/glancebox:X.Y.Z --repo robinlanger/glancebox
gh attestation verify glancebox-ultra-X.Y.Z.bin --repo robinlanger/glancebox
```

Releases before the one that introduced this check have no attestation.

## Scope and known limits

Glance Box is built for a home network. These are design decisions, not vulnerabilities:

- The **server has no login**. Its preview page and frame API are open to everyone who can reach the port. Keep it inside your home network and do not forward the port to the internet.
- The **display talks plain HTTP**. Firmware updates and settings changes are protected by the update password (HTTP Basic auth, user `admin`), but the password is not encrypted on the network. `/status` is readable without a password.
- The setup portal (`GlanceBox-XXXX`) is an open Wi-Fi network while it runs. It only opens when no Wi-Fi is configured or the saved network is unreachable, and changing an existing setup there needs the current update password.
- Tokens for pages (Home Assistant, AI providers) belong in `.env`, not in `config.yaml`.
- **Chromium** renders the pages with only an allowlist of environment variables, so it does not inherit tokens or keys. Its sandbox is tried at start, but Docker's default seccomp profile and the Home Assistant add-on usually do not allow it; Chromium then runs without a sandbox and the server logs one warning. A process running as the same user can still read the server's own start environment (`/proc/<pid>/environ`), which only the sandbox prevents.

Reports that show a way around these protections, for example installing firmware without the update password, reading tokens from the server, or code execution through a page or a pushed value, are very welcome.
