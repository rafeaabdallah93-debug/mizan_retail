# Running Mizan on your computer or server

Mizan comes in two editions. Pick one:

| Edition | What you get | Web address (default) |
| --- | --- | --- |
| `shop` | Mizan for your shop and branches (ERPNext 16 + Mizan) | http://localhost:8081 |
| `shop-web` | Everything in `shop`, plus the link to a WooCommerce online store | http://localhost:8082 |

If you do not sell on a WooCommerce website, choose `shop`.
Before using `shop-web` with real customers, read `docs/woocommerce.md` (it has a security warning).

In the commands below, replace `shop` with `shop-web` if that is your edition.
Type every command in a terminal (on Windows: the Ubuntu window, see step 1) opened in the
`mizan_retail` folder.

## 1. Install the tools (once)

Mizan runs on **Linux**, on **macOS**, or on **Windows through WSL2** (a Linux inside Windows).
You need three things: a terminal, **git** (downloads Mizan) and **Docker** (runs it).
The computer needs at least 4 GB of memory (8 GB is better) and 20 GB of free disk.

**Windows 10 or 11**
1. Open "Windows PowerShell" as administrator and type `wsl --install`. Restart when asked.
   After the restart an "Ubuntu" window opens: choose a user name and password.
2. Install **Docker Desktop** from https://www.docker.com/products/docker-desktop/ . During
   setup keep "Use WSL 2" ticked. Start Docker Desktop, then in its Settings, Resources,
   WSL integration, switch on "Ubuntu".
3. In the Ubuntu window type: `sudo apt update && sudo apt install -y git`
4. Use the Ubuntu window for every command below (not PowerShell).

**macOS**
1. Install **Docker Desktop** from https://www.docker.com/products/docker-desktop/ and start it.
2. Open the "Terminal" app and type `git --version`. If git is missing, macOS offers to install
   the "command line developer tools": accept.

**Linux server (Ubuntu or Debian)**
1. Install **Docker Engine** with the Compose plugin: https://docs.docker.com/engine/install/
2. `sudo apt install -y git`

Check: `docker compose version` and `git --version` should each print a version number.

## 2. Get Mizan (once)

    git clone https://github.com/rafeaabdallah93-debug/mizan_retail.git
    cd mizan_retail

This downloads the `mizan_retail` folder. All commands below are typed inside it.

## 3. Fill in your shop's settings (once)

    cp deploy/.env.example deploy/.env

Open `deploy/.env` in a text editor and fill in:

- `COMPANY`: your company name, as it should appear on invoices.
- `ABBR`: a short abbreviation of it, letters only (for example `MS`).
- `LANGUAGE`: `ar` for Arabic screens, `en` for English.
- `ADMIN_PASSWORD` and `DB_ROOT_PASSWORD`: two different passwords of **at least 12
  characters**. Mizan refuses to start with shorter ones. Write them down somewhere safe.
- `SITE_NAME`: keep `mizan.localhost` if you use Mizan on this computer only. On a server with a
  domain name, put the domain (for example `erp.myshop.com`).

Company, abbreviation, language and passwords are used once, when the shop is first created.
Keep `deploy/.env` private and never send it to anyone.

## 4. Build Mizan (once, and again for each update)

    deploy/build.sh shop deploy/.env

This prepares Mizan for your computer (a few minutes) and writes the version it built into
`deploy/.env` (the `MIZAN_IMAGE=` line).

## 5. Start

    docker compose -f deploy/editions/shop.yaml --env-file deploy/.env up -d

The very first start takes about 3 to 5 minutes: it creates your company with Egyptian
settings (currency EGP, VAT, chart of accounts). The command waits until this is done.
Later starts take about a minute.
Mizan starts again by itself when the computer restarts (as long as Docker is running).

If the command ends with an error such as `service "create-site" didn't complete
successfully`, read the section "If the first start failed" below.

## 6. Open in the browser

Go to http://localhost:8081 (or http://localhost:8082 for `shop-web`). If you see
"502 Bad Gateway", Mizan is still waking up: wait a few seconds and refresh.

- Username: `Administrator`
- Password: the `ADMIN_PASSWORD` you chose.

**First thing to do:** open **Users** (search "User" in the search bar), and add one user for
each person who works in the shop, with their own password and role. Use Administrator only
for setup, not for daily work.

To see whether setup has finished, or what went wrong:

    docker compose -f deploy/editions/shop.yaml --env-file deploy/.env logs create-site

The last line says `Site ... is ready` when it is done.

## 7. Other computers in the shop (optional)

By default Mizan opens **only on the computer it runs on**. To let other computers and tills
on the shop's own network use it:

1. In `deploy/.env` add the line `HTTP_BIND=0.0.0.0`
2. Start again (step 5).
3. On the other computers, open `http://<this computer's address>:8081`, for example
   `http://192.168.1.20:8081`. (Find the address in this computer's network settings.)

**Warning:** this connection is **not encrypted** (plain `http`). Anyone on the same network
could read the passwords and data that pass over it. Use it only on a private shop network
that you control, with a Wi-Fi password, never on a public or guest Wi-Fi.

To use Mizan **over the internet** (from home, from another branch), do not just open the port:
it needs HTTPS through a "reverse proxy" set up by a technician (see the technical section).
For `shop-web`, the WooCommerce connector's security gap must also be fixed or its order
address blocked first (see `docs/woocommerce.md`).

## 8. Stop

    docker compose -f deploy/editions/shop.yaml --env-file deploy/.env stop

Your data is kept. Start again with the command in step 5.

Never add `-v` to a `down` command on a shop that has data: `down -v` **erases all your data**.

## 9. Back up (do this every day)

    deploy/backup.sh shop

This saves the database, uploaded files and the site's keys into a new folder
`deploy/backups/<date-time>/`. **Copy that folder to somewhere else** (a USB disk, another
computer, a cloud drive): a backup that stays on the same computer is lost with it.
The backup contains all your business data: keep it private.

## 10. Restore a backup

Mizan must be running (step 5), with the same edition as the backup. Then:

    deploy/restore.sh shop deploy/backups/<date-time>

It asks you to type `YES`, because it **replaces everything** currently in Mizan with the backup.

To move to a new computer: copy the `mizan_retail` folder (including `deploy/.env`) and your
backup folder, do steps 1, 4 and 5 there, then restore.

To move from `shop` to `shop-web`: back up the `shop` edition (step 9), stop it (step 8), build
and start `shop-web` (steps 4 and 5, with `shop-web`), then restore the backup into `shop-web`
with `deploy/restore.sh shop-web deploy/backups/<date-time>`.

## 11. Update to a new version

1. Back up (step 9) and copy the backup somewhere safe.
2. Download the new version of Mizan: in the `mizan_retail` folder type

        git pull

   This fetches the latest Mizan files from the internet and updates the folder in place.
   Your settings (`deploy/.env`) and backups are not touched.
3. Build and start again:

        deploy/build.sh shop deploy/.env
        docker compose -f deploy/editions/shop.yaml --env-file deploy/.env up -d

   Starting applies the database changes of the new version by itself. During that time the
   site shows a maintenance page; the command waits until it is finished.
4. Check it worked:

        docker compose -f deploy/editions/shop.yaml --env-file deploy/.env logs create-site

   The last line must be `Site ... is ready`.

If something goes wrong, set `MIZAN_IMAGE=` in `deploy/.env` back to the old value, start
again, and restore your backup.

## If the first start failed

1. Read what went wrong:

        docker compose -f deploy/editions/shop.yaml --env-file deploy/.env logs create-site

   Lines starting with `REFUSED:` tell you which setting to fix in `deploy/.env` (for example a
   password that is too short).
2. If this is a **brand-new installation with no data in it yet**, fix `deploy/.env`, erase the
   half-made shop and start again:

        docker compose -f deploy/editions/shop.yaml --env-file deploy/.env down -v
        docker compose -f deploy/editions/shop.yaml --env-file deploy/.env up -d

   Only do this before anyone has entered real data: `down -v` erases everything.
3. If it still fails, send the output of the `logs` command (it contains no passwords) to your
   technician.

## Check that it is healthy

    curl -s http://localhost:8081/api/method/ping

should print `{"message":"pong"}`.

---

# Technical section

## What is in each edition

| App | Source | `shop` | `shop-web` |
| --- | --- | --- | --- |
| frappe 16.55.1, erpnext 16.53.0 | base image `frappe/erpnext:v16.53.0` (pinned by digest) | yes | yes |
| mizan_core | `MIZAN_CORE_SRC` @ `MIZAN_CORE_REF` | yes | yes |
| mizan_retail | `MIZAN_RETAIL_SRC` @ `MIZAN_RETAIL_REF` (its `deploy/` folder is left out) | yes | yes |
| woocommerce_fusion (branch `version-16`, unchanged) + `woocommerce==3.0.0`, `jsonpath-ng==1.7.0`, `ply==3.11` | `WOOCOMMERCE_FUSION_SRC` @ `WOOCOMMERCE_FUSION_REF` | no | yes |

Other images: `mariadb:11.8` and `redis:6.2-alpine`, both pinned by digest in the compose files.
Nothing uses a floating tag; the Mizan image tag is made of the app commits:
`mizan-shop:<retail7>-<core7>` and `mizan-shop-web:<retail7>-<core7>-<woo7>`. Each image also
carries the full SHAs as labels: `docker image inspect <image> --format '{{json .Config.Labels}}'`.

## Pinned versions

`deploy/versions.env` holds one source and one ref per app (build args of `deploy/build.sh`).
A source is a git URL or a local git checkout; relative paths are relative to this repo.
Override any of them for one build with an environment variable of the same name.

Last verified together (Task 9b, 2026-11-05):

| App | Commit |
| --- | --- |
| mizan_core | `eedfcf02c25d1f71fc1f883d8ab4fb20c2578dd6` |
| mizan_retail (app code) | `53efc683ca65e753136147ad78c9258a2f0f39fa` |
| woocommerce_fusion (`version-16`) | `ab71a15d322232fff58d93fa0aa469812bfa9a30` |

`deploy/build.sh shop-web` with no overrides builds exactly these (sources cloned from
GitHub). To build local checkouts instead (developers):

    C=/home/user/mizan-dev/custom-apps
    MIZAN_CORE_SRC=$C/mizan_core MIZAN_CORE_REF=HEAD \
    MIZAN_RETAIL_SRC=$C/mizan_retail MIZAN_RETAIL_REF=HEAD \
    WOOCOMMERCE_FUSION_SRC=$C/woocommerce_fusion WOOCOMMERCE_FUSION_REF=HEAD \
      deploy/build.sh shop-web

build.sh warns when a ref is neither a full SHA nor a tag (record the printed SHA in
`versions.env` to rebuild the same image) and when a local checkout has uncommitted changes
(they are never included).

## How the image is built

- Host requirements: bash 3.2 or later (macOS's own bash is fine: no bash-4 features, no
  GNU-only `sed -i`), git, Docker. No Python or pip on the host.
- `deploy/fetch-wheels.sh` downloads the Python wheels into `deploy/wheels/` (git-ignored) by
  running `pip download --require-hashes` in a pinned `python:3.14.10-slim@sha256:...`
  container (override with `PYTHON_IMAGE`), with exact versions and sha256 hashes from
  `deploy/requirements/*.txt`. If `PIP_CERT`, `SSL_CERT_FILE` or `REQUESTS_CA_BUNDLE` points at
  a CA file on the host (TLS-intercepting proxies), it is mounted into that container.
  The image build never reaches PyPI (`pip install --no-index --require-hashes`).
  `flit_core` is needed only to install the apps in editable mode without build isolation.
- `deploy/build.sh <edition>` exports each app with `git archive <sha>` (uncommitted changes
  are never included; it warns if a local checkout is dirty) into `deploy/.build/<edition>/`,
  then runs `docker build -f deploy/Dockerfile` on that context.
- `deploy/Dockerfile` (`FROM frappe/erpnext:v16.53.0@sha256:...`): copies the apps into
  `apps/`, `pip install --no-deps --no-index --no-build-isolation -e apps/<app>`, links each
  app's `public/` into the baked `assets/` folder, and writes `sites/apps.txt`. The base image's
  entrypoint links `sites/assets` to that baked folder on every container start, so nginx
  serves `/assets/<app>/...` with no runtime hacks and it survives `down`/`up` and updates.
  These apps ship plain JS/CSS (no bundles), so no `bench build` is needed. The connector's
  Python dependencies are part of the image, so they survive container recreation.

## What the compose files do

Services as in frappe_docker's `pwd.yml`: `db`, `redis-cache` (in memory), `redis-queue`,
`configurator`, `create-site`, `backend`, `websocket`, `queue-short`, `queue-long` (also serves
the connector's `*_long` jobs), `scheduler`, `frontend` (nginx). Long-running services use
`restart: unless-stopped`. Volumes: `db-data`, `sites`, `logs`, `redis-queue-data`.

`create-site` runs on every `up`:
- no site yet: refuses (exit 1, nothing created) if `ADMIN_PASSWORD` or `DB_ROOT_PASSWORD`
  starts with `change-me` or is shorter than 12 characters (empty values are already stopped
  by compose's `${VAR:?}` guard); then `bench new-site <SITE_NAME> --install-app erpnext
  --install-app mizan_core --install-app mizan_retail [--install-app woocommerce_fusion]`;
- site exists: `set-maintenance-mode on`, `scheduler pause`, `migrate`, then `scheduler
  resume` and `set-maintenance-mode off` (also run by an EXIT trap if migrate fails, so the
  site is never left in maintenance mode or paused). This is what applies an update;
- if `frappe.is_setup_complete()` is false: `bench --site <SITE_NAME> mizan-provision
  --company "<COMPANY>" --abbr <ABBR> --language <LANGUAGE>`. Provisioning refuses if another
  company exists, and re-running it with the same company and abbreviation completes a
  partial first run (tested by clearing the setup-complete flags and restarting create-site);
- `enable-scheduler` (the connector needs it), `set-config -p allow_tests False`.

`backend`, `queue-short`, `queue-long` and `scheduler` start only after `create-site` has
completed successfully (`service_completed_successfully`). Workers and the scheduler must not
run jobs against a database that is being created or migrated; the backend waits too, so the
new code never serves an unmigrated database and nothing serves a site that has no company
yet (no setup-wizard window). The cost is that `up -d` returns only when the site is ready
(about 2 minutes on first start), and a failing `create-site` makes `up -d` report the error.
`websocket` and `frontend` do not write data and keep their usual order.

The frontend publishes `${HTTP_BIND:-127.0.0.1}:${HTTP_PORT}` -> 8080: loopback only unless
the owner sets `HTTP_BIND=0.0.0.0` (plain HTTP on the LAN, see step 7).

Compose project names: `mizan-shop` and `mizan-shop-web` (set in the files; `-p` overrides).
Both editions can run side by side on one machine (ports 8081 and 8082; `HTTP_PORT` changes it).

Bench commands:

    docker compose -f deploy/editions/shop.yaml --env-file deploy/.env exec backend bench --site <SITE_NAME> <command>

Backups: `deploy/backup.sh` runs `bench backup --with-files` (database, public and private
files, site config with the encryption key) and copies the result out of the container.
`deploy/restore.sh` runs `bench restore` with the files, restores the encryption key from the
backup's site config (so stored passwords such as the WooCommerce API secret still decrypt),
then migrates and restarts. Both scripts honour `COMPOSE_PROJECT_NAME` when you use `-p`.

## Production notes

- Put a TLS reverse proxy (Caddy, Traefik, nginx) in front of the `frontend` port for
  internet access, and use your domain as `SITE_NAME`.
- `shop-web`: block `/api/method/woocommerce_fusion.woocommerce_endpoint.order_created` at
  that reverse proxy until the connector's webhook signature check is fixed (see
  `docs/woocommerce.md`). This edition must not go live before that.
- If the site shows "502 Bad Gateway" after you restarted only the backend by hand, run
  `docker compose ... restart frontend` (nginx caches the backend address).
- `DB_ROOT_PASSWORD` only takes effect when the database volume is first created.
- Secrets: `ADMIN_PASSWORD` and `DB_ROOT_PASSWORD` stay in `deploy/.env` and in the
  environment of the `create-site` and `db` containers (visible to anyone who can run
  `docker inspect` on this machine). The site's own database password and encryption key are
  in `sites/<SITE_NAME>/site_config.json` in the `sites` volume, and in every backup. Restrict
  who can use Docker on the machine, keep `deploy/.env` at mode 600, and change the
  Administrator password inside Mizan after the first login if others have seen `.env`.
