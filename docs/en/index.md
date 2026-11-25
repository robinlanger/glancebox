---
template: home.html
title: Glance Box
description: Turn the GeekMagic SmallTV Ultra into a Wi-Fi display for anything you can write as HTML. Open source, no soldering, no cloud.
hide:
  - navigation
  - toc
kicker: Open source · no soldering
title_line1: Your display.
title_line2: Your pages.
lead: Glance Box turns the ~15 € SmallTV Ultra into a Wi-Fi display for anything you can write as HTML. Departures, weather, your energy flow, your home server, your AI limits.
cta_primary: Get started
cta_secondary: View on GitHub
hero_alt: Glance Box on the GeekMagic SmallTV Ultra showing the energy flow page, next to an earbuds case for size
steps_title: From the box to your first picture.
steps_sub: No soldering, no serial adapter, no cloud. About half an hour.
steps:
  - title: Get the device
    text: A GeekMagic SmallTV Ultra, about 15 €.
    link_text: What to look for
    href: guide/1-get-the-device/
  - title: Start the server
    text: One Docker command, then list your pages in config.yaml.
    link_text: Set up the server
    href: guide/2-start-the-server/
  - title: Flash it in your browser
    text: Through the "Firmware update" menu of the stock firmware.
    link_text: Flashing guide
    href: guide/3-flash-the-firmware/
gallery_title: Ready-made templates.
gallery_sub: Add a few lines to config.yaml. Or write your own pages in HTML.
gallery:
  - img: img/templates/bahn.png
    caption: Departures
    href: templates/bahn/
  - img: img/templates/weather.png
    caption: Weather
    href: templates/weather/
  - img: img/templates/kuma-ok.png
    caption: Uptime Kuma
    href: templates/kuma/
  - img: img/templates/ai-claude.png
    caption: Claude limits
    href: templates/ai/
  - img: img/templates/homeassistant-tiles.png
    caption: Home Assistant
    href: templates/homeassistant/
  - img: img/templates/energy.png
    caption: Energy flow
    href: templates/energy/
  - img: img/templates/printer-printing.png
    caption: 3D printer
    href: templates/printer/
photo_alt: Four photos of the display showing departures, Uptime Kuma, weather and Claude limits
photo_caption: On the real display.
features:
  - title: Safe updates
    text: Every update is checked against its MD5. A broken one ends in safe mode, not a boot loop.
  - title: A lovely device page
    text: Live brightness, night mode, settings saved as you go, in light and dark.
  - title: Yours, not ours
    text: MIT licensed, no account. The display only talks to your own server.
---

# Glance Box
