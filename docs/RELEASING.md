# Releasing Glance Box

Maintainer checklist. Firmware and server share one version, kept in the repo-root `VERSION`
file. A release is a `vX.Y.Z` tag; the `release` workflow does the rest.

## Checklist

1. **Bump the version.** Edit `VERSION`, set the same `version` in `ha-addon/config.yaml`
   (the Home Assistant add-on pulls the image tag of that version; the store offers the new
   version as soon as it is on `main`, so push the tag right after merging, and never merge an
   `ha-addon/` version whose image lacks what the add-on needs), and add a `## [X.Y.Z]` section to `CHANGELOG.md`
   (the workflow publishes exactly that section as the release notes). Check it locally:
   `python3 tools/changelog_section.py "$(cat VERSION)"`.
2. **Never change the flash layout in an OTA release.** `board_build.ldscript` and the
   filesystem layout (LittleFS offset, size, block size) must stay as they are: an OTA update
   keeps the data already on the flash, and a device whose settings no longer mount loses its
   settings (server address, update password). A layout change is only possible with serial flashing.
3. **CI is green** on the commit you are about to tag (`ci.yml`, jobs `server`, `server-image`, `audit`, `firmware`, `docs`:
   server tests, firmware build, native tests, size check, Docker build, known vulnerabilities in
   the runtime dependencies, docs check).
4. **Smoketest on real hardware** with the release candidate and the previous release bin:

   ```sh
   cd firmware && pio run -e ultra && cd ..
   gh release download vPREV --pattern 'glancebox-ultra-*.bin' --dir /tmp/prev   # or any saved copy
   GB_PASSWORD=<device password> tools/ota-smoketest.sh <device-ip> \
       firmware/.pio/build/ultra/firmware.bin /tmp/prev/glancebox-ultra-PREV.bin
   ```

   It must end with `PASS` (see [The smoketest](#the-smoketest)). Use `--skip-frames` only if the
   device has no server configured.
5. **24 h soak.** Leave the candidate on a device for 24 hours. Afterwards `/status` must show
   `boot_failed` 0, `safe_mode` false, and `frames_ok` still growing; note the uptime and
   `heap_free`.
6. **Tag only from a green `main`.** Merge first, wait for CI on `main`, then tag that commit:
   `git switch main && git pull && git tag vX.Y.Z && git push origin vX.Y.Z`. The tag must equal `v$(cat VERSION)`,
   otherwise the workflow fails before building anything.
7. **Note the smoketest result in the release notes.** When the workflow has created the release,
   edit it and append a line such as
   `Smoketest: PASS on GeekMagic SmallTV Ultra, previous = vPREV, 24 h soak OK (YYYY-MM-DD)`.
8. Optionally, run the smoketest once more with the **published** `.bin` (check it against the
   `.md5`/`.sha256` files first).
9. **Check the build attestations** of the published image and firmware:

   ```sh
   gh attestation verify oci://ghcr.io/robinlanger/glancebox:X.Y.Z --repo robinlanger/glancebox
   gh attestation verify glancebox-ultra-X.Y.Z.bin --repo robinlanger/glancebox
   ```

### First release (no previous release exists)

For `0.1.0` there is no earlier release bin. Use the same commit built with a different version
as the "previous" image:

```sh
echo 0.1.0-prev > VERSION          # temporary, do not commit
(cd firmware && pio run -e ultra)
cp firmware/.pio/build/ultra/firmware.bin /tmp/glancebox-0.1.0-prev.bin
git checkout VERSION
(cd firmware && pio run -e ultra)  # the real 0.1.0 image
```

The smoketest needs the two images to carry different `GBVER:` tags, otherwise it cannot tell a
reboot into the new image from no reboot, and it refuses to run.

## What the release workflow does

`.github/workflows/release.yml`, on a pushed tag `v*`:

1. Fails if the tag is not `v$(cat VERSION)`.
2. Builds the firmware (`pio run -e ultra`, PlatformIO pinned in the workflow), runs the size
   check, verifies that `GBVER:<version>` is in the image exactly once, and writes
   `glancebox-ultra-<ver>.bin`, `.bin.md5` and `.bin.sha256`.
3. Builds the Docker image for `linux/amd64` and `linux/arm64` and pushes
   `ghcr.io/robinlanger/glancebox:<ver>` and `:latest`.
4. Creates signed build provenance attestations (`actions/attest-build-provenance`) for the
   pushed image (stored in GHCR next to it) and for `glancebox-ultra-<ver>.bin`.
5. Runs `gh release create` with the three firmware files and the `CHANGELOG.md` section.

Before building, the workflow also fails if a GitHub release for the tag already exists, so a
duplicate tag pushes nothing.

**Dry run.** Actions, "release", "Run workflow" (any branch) builds everything but never logs in
to GHCR, pushes, attests, or creates a release. The firmware files are kept as the workflow artifact
`firmware-<ver>`. Publishing is only possible by pushing a `v*` tag.

## Dependency updates

Dependabot opens weekly pull requests for the Python dependencies, the Docker base image and the
GitHub Actions. A Dependabot PR that changes `server/requirements.in` or
`server/requirements-dev.in` needs the lock files regenerated with the commands in their headers
(run in `server/`, first `requirements.lock`, then `requirements-dev.lock`), and the CI job
`server` fails until then. The lock check can also turn red without any change in the repo, when a
pinned version gains a new wheel on PyPI; regenerating the lock files fixes it.

## The smoketest

`tools/ota-smoketest.sh [--skip-frames] <device-ip> <new.bin> <previous.bin>`, with the OTA
password in `GB_PASSWORD` (user is always `admin`). Needs `bash`, `curl`, `jq` and `strings`.
It is non-interactive and prints `PASS` (exit 0) or `FAIL <step>` (exit 1); progress goes to
stderr. Every request has a timeout.

| Step | Action | Pass condition |
| --- | --- | --- |
| 1 | read the version from `/status` | device answers; both bins carry one `GBVER:` tag each, and they differ |
| 2 | upload the new bin with a wrong MD5 | HTTP 400, same version, uptime did not drop (no reboot) |
| 3 | upload the new bin | reboot seen, `/status` reports the bin's version within 90 s, `boot_failed` back to 0 and `safe_mode` false within 90 s, `frames_ok` grows within 60 s |
| 4 | upload the previous bin | same checks |
| 5 | upload the new bin again | same checks |

The device refuses further uploads after a committed update until it reboots, so the script
always waits for the reboot before the next step. `boot_failed` is 1 during the first minute after
a boot and drops to 0 once the firmware counts as healthy (60 s uptime, Wi-Fi, web server), which
is why step 3 takes about a minute per image. A full run takes roughly five to six minutes.

## Running the smoketest in a self-hosted runner

The smoketest has to reach the device on the LAN, so it cannot run on GitHub-hosted runners. To
automate it, register a self-hosted runner on a machine in the same network as the test device
(a Raspberry Pi is enough; it needs `bash`, `curl`, `jq`, `binutils`).

1. Settings, Actions, Runners, "New self-hosted runner"; give it a label such as `glancebox-lab`.
   Run the runner as an unprivileged user.
2. Store the device password as the repository secret `GB_PASSWORD` and the device address as
   the variable `GB_DEVICE_IP`. Use a dedicated test device with its own password.
3. Add a manual workflow (not part of this repo's default pipeline), for example:

   ```yaml
   name: ota-smoketest
   on:
     workflow_dispatch:
       inputs:
         previous_tag: { description: "Previous release tag", required: true }
   jobs:
     smoketest:
       runs-on: [self-hosted, glancebox-lab]
       steps:
         - uses: actions/checkout@v4.2.2
         - uses: actions/download-artifact@v4.3.0   # firmware-<ver> from a dry run
           with: { name: firmware-X.Y.Z, path: dist }   # replace X.Y.Z
         - run: gh release download "${{ inputs.previous_tag }}" --pattern '*.bin' --dir prev
           env: { GH_TOKEN: "${{ github.token }}" }
         - run: tools/ota-smoketest.sh "$GB_DEVICE_IP" dist/*.bin prev/*.bin
           env:
             GB_PASSWORD: ${{ secrets.GB_PASSWORD }}
             GB_DEVICE_IP: ${{ vars.GB_DEVICE_IP }}
   ```

4. Only run it from branches and tags you trust: a workflow on a self-hosted runner executes
   code on your network. Do not enable it for pull requests from forks.

The device is flashed three times per run; keep the test device powered and on good Wi-Fi.
If a run fails midway, check `/status` of the device: a failed step 3 to 5 can leave it on
either image, which is expected and safe. Re-run the smoketest once the cause is understood.
