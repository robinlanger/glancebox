# Start the server

<p class="gb-meta">Step 2 of 5 · about 10 minutes</p>
<div class="gb-progress" aria-hidden="true"><span class="on"></span><span class="on"></span><span></span><span></span><span></span></div>

!!! tip "Home Assistant OS?"
    Run the server as a Home Assistant add-on instead of Docker. Follow the step-by-step guide [Home Assistant add-on](../home-assistant.md) and skip this step.

The server renders your pages and sends them to the display as pictures. It runs in Docker on your always-on computer.

## Get Glance Box

1. Open a terminal on the computer and run:

    ```sh
    git clone https://github.com/robinlanger/glancebox.git
    cd glancebox
    cp config-example.yaml config.yaml
    mkdir pages-custom
    ```

2. Open `config.yaml` in an editor and adjust the pages under `pages:`:

    - The `bahn` page shows departures for an example station. Change `station:` to yours, or delete the block.
    - The `url` page at the end points to an example address. Delete it or change `url:` to a page of your own.
    - For a first test, a clock is the simplest page. Add it under `pages:`:

        ```yaml
          - type: clock
        ```

    You can change all of this later. More pages: the [template catalog](../templates/README.md).

## Start it

1. Start the server:

    ```sh
    docker compose up -d --build
    ```

    The first start takes a few minutes, because Docker builds the image with its own browser inside.

2. Open `http://<server-ip>:8080/` in your browser, for example `http://192.168.1.50:8080/`. You should see a preview of every page.

    !!! tip "Port 8080 already taken?"
        If something else (for example Pi-hole) uses port 8080, create a file `.env` next to `docker-compose.yml` with `GLANCEBOX_PORT=8090` and run `docker compose up -d` again. Use `:8090` from then on.

3. **Write down the server address**, for example `http://192.168.1.50:8080`. The display asks for it in step 4. Give the computer a fixed IP address in your router, so the address does not change.

If the server does not start, `docker compose logs --tail 50` shows why. All options: [Configuration](../configuration.md).
