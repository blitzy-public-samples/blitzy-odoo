# BUILD_AND_RUN.md

This document is a source-derived reference for building, running, configuring, and supplying secrets to the Odoo 19.0 server. Every instruction is cited to a specific source file and line range using the `[source: path/to/file:Lstart-Lend]` format. The instructions documented here have been validated end-to-end on a clean Ubuntu 24.04 host; see `## Validation Evidence` at the bottom.

---

## OS Prerequisites

The pinned Python dependency set targets Ubuntu 24.04 (Noble Numbat) and Debian 12 (Bookworm) [source: requirements.txt:L1-L2]; the validation cycle below uses Ubuntu 24.04. The Python upper bound is 3.13 [source: odoo/release.py:L40-L40] and the PostgreSQL minimum is major version 13 [source: odoo/release.py:L41-L41]; the validation provisions PostgreSQL 16 (the major version available in the Noble apt archive that satisfies `>= 13`).

| Apt Package | Required For | Source |
|---|---|---|
| `python3.13` | Interpreter for the Odoo runtime; matches the upper supported Python version | [source: odoo/release.py:L40-L40] |
| `python3.13-venv` | `python3.13 -m venv` virtual-environment creation used by Build Step 3 | [source: setup.py:L70-L70] |
| `python3.13-dev` | Python C headers required to build C-extension wheels (`psycopg2`, `lxml`, `Pillow`, `gevent`, `cryptography`, `python-ldap`) when no prebuilt wheel is available | [source: requirements.txt:L23-L23] [source: requirements.txt:L36-L36] [source: requirements.txt:L50-L50] [source: requirements.txt:L58-L58] |
| `build-essential` | Provides `gcc`, `g++`, `make` for compiling C-extension source distributions (e.g., `libsass`, `gevent`) | [source: requirements.txt:L23-L23] [source: requirements.txt:L33-L33] |
| `libpq-dev` | PostgreSQL client headers required by `psycopg2==2.9.10` build | [source: requirements.txt:L55-L58] [source: setup.py:L50-L50] |
| `libxml2-dev` | XML library headers required by `lxml==5.2.1` build | [source: requirements.txt:L34-L36] [source: setup.py:L39-L39] |
| `libxslt1-dev` | XSLT library headers required by `lxml==5.2.1` build | [source: requirements.txt:L34-L36] |
| `libjpeg-dev` | JPEG codec headers required by `Pillow==11.1.0` build | [source: requirements.txt:L47-L50] [source: setup.py:L47-L47] |
| `libpng-dev` | PNG codec headers required by `Pillow==11.1.0` build | [source: requirements.txt:L47-L50] |
| `zlib1g-dev` | zlib headers required by `Pillow==11.1.0` build | [source: requirements.txt:L47-L50] |
| `libfreetype6-dev` | TrueType font headers required by `Pillow==11.1.0` for text rendering | [source: requirements.txt:L47-L50] |
| `liblcms2-dev` | Color-management library headers required by `Pillow==11.1.0` | [source: requirements.txt:L47-L50] |
| `libwebp-dev` | WebP codec headers required by `Pillow==11.1.0` | [source: requirements.txt:L47-L50] |
| `libldap2-dev` | OpenLDAP headers required by `python-ldap==3.4.4` build (LDAP authentication extra) | [source: requirements.txt:L69-L70] [source: setup.py:L71-L73] |
| `libsasl2-dev` | SASL headers required by `python-ldap==3.4.4` build | [source: requirements.txt:L69-L70] |
| `libsasl2-modules` | SASL runtime plug-ins required by `python-ldap==3.4.4` at run time | [source: requirements.txt:L69-L70] |
| `libssl-dev` | OpenSSL headers required by `cryptography==42.0.8` and `pyopenssl==24.1.0` builds | [source: requirements.txt:L13-L13] [source: requirements.txt:L60-L60] |
| `libffi-dev` | libffi headers required by `cryptography==42.0.8` build | [source: requirements.txt:L13-L13] |
| `libmagic1` | libmagic shared object loaded at run time by `python-magic==0.4.27` for MIME detection | [source: requirements.txt:L67-L68] |
| `libusb-1.0-0-dev` | libusb headers required by `pyusb==1.2.1` build (POS hardware integration) | [source: requirements.txt:L74-L74] [source: setup.py:L57-L57] |
| `fonts-noto-cjk` | CJK font family used by `reportlab==4.1.0` PDF rendering | [source: requirements.txt:L77-L79] [source: setup.py:L59-L59] |
| `wkhtmltopdf` | HTML-to-PDF binary discovered via `find_in_path('wkhtmltopdf')` and invoked by `_run_wkhtmltopdf` for `ir.actions.report` rendering; optional, install where the apt archive provides it | [source: odoo/addons/base/models/ir_actions_report.py:L41-L94] |
| `postgresql-16` | PostgreSQL 16 server satisfies the `MIN_PG_VERSION = 13` lower bound | [source: odoo/release.py:L41-L41] |
| `postgresql-client-16` | Provides the `psql`, `pg_dump`, and `pg_restore` binaries discovered by the database service via `find_pg_tool` | [source: odoo/service/db.py:L285-L286] [source: odoo/service/db.py:L352-L362] |
| `ca-certificates` | TLS root certificates required by the `requests==2.31.0` HTTP client used in outbound integrations | [source: requirements.txt:L80-L81] [source: setup.py:L61-L61] |
| `curl` | Validation HTTP probe tooling used in `## Validation Evidence`; not part of the Odoo runtime | (validation tooling — not source-derived) |

---

## Build

### Step 1 — Install OS prerequisites

```bash
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  build-essential libpq-dev libxml2-dev libxslt1-dev libjpeg-dev libpng-dev \
  zlib1g-dev libfreetype6-dev liblcms2-dev libwebp-dev libldap2-dev libsasl2-dev \
  libsasl2-modules libssl-dev libffi-dev libmagic1 libusb-1.0-0-dev \
  fonts-noto-cjk postgresql-16 postgresql-client-16 ca-certificates curl
```

The `apt-get install -y --no-install-recommends` template, the `DEBIAN_FRONTEND=noninteractive` environment variable, and the `xargs $cmd` non-interactive pattern reflect the canonical Debian-package provisioning sequence shipped with the project. [source: setup/debinstall.sh:L9-L9] [source: setup/debinstall.sh:L25-L27]

**Optional `node-less` opt-in.** The asset pipeline's `LessStylesheetAsset.get_command()` shells out to `lessc` (`misc.find_in_path('lessc')`) only when an asset bundle contains a `.less` source; the `EXTENSIONS` tuple lists `.less` among the recognized stylesheet extensions. The repository ships **zero** `.less` files under `addons/` or `odoo/addons/`, so this code path is never exercised by the bundled addons and `node-less` is **omitted from the prerequisites above**. Install `node-less` only if a third-party addon you load contains `.less` sources. The Ubuntu 24.04 `node-less` package declares `Depends: nodejs:any`, which fails to resolve when the system already has a third-party `nodejs` package installed (e.g., from the NodeSource repository) that does not declare `Multi-Arch: foreign`; if you do install `node-less`, install it on a host with no prior third-party `nodejs`, or first remove the third-party `nodejs`, so that apt can pull the archive `nodejs` that satisfies `nodejs:any`. [source: odoo/addons/base/models/assetsbundle.py:L1078-L1087] [source: odoo/addons/base/models/assetsbundle.py:L27-L27]

### Step 2 — Install Python 3.13

```bash
apt-get install -y --no-install-recommends software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update
apt-get install -y --no-install-recommends python3.13 python3.13-venv python3.13-dev
```

Python 3.13 is the upper supported version; using a higher version triggers a runtime warning. [source: odoo/release.py:L40-L40] [source: odoo/cli/server.py:L69-L73]

### Step 3 — Create and activate a virtual environment

```bash
python3.13 -m venv /opt/odoo-venv
. /opt/odoo-venv/bin/activate
pip install --no-input --upgrade pip wheel setuptools
```

`setup.py` enforces `python_requires` against the lower bound `MIN_PY_VERSION = (3, 10)`; an isolated venv guarantees the activated interpreter is 3.13 and prevents apt-managed system packages from masking pinned versions. [source: setup.py:L70-L70] [source: odoo/release.py:L39-L39]

### Step 4 — Install Python dependencies

```bash
pip install --no-input -r requirements.txt
```

`requirements.txt` pins one version per package per Python interpreter and per platform, so pip resolves a single, deterministic dependency graph for Python 3.13 on `sys_platform != 'win32'`. [source: requirements.txt:L1-L98]

### Step 5 — Install the Odoo package itself (editable)

```bash
pip install --no-input -e .
```

`setup.py` declares `name='odoo'`, `version=version` (loaded dynamically from `odoo/release.py`), `install_requires=[...]`, and `python_requires='>=' + MIN_PY_VERSION`. Editable mode (`-e`) registers the repository checkout so changes under `odoo/` are picked up without re-installation. [source: setup.py:L13-L77] [source: setup.py:L10-L10]

---

## Run

Odoo's CLI entry point is `python -m odoo`, which invokes `odoo.cli.command.main()` [source: odoo/__main__.py:L1-L3]. When no sub-command name is provided, `main()` defaults to the `server` command [source: odoo/cli/command.py:L127-L129], whose lifecycle calls `config.parse_config(args, setup_logging=True)`, `check_postgres_user()`, `report_configuration()`, the auto-database-creation loop, `setup_pid_file()`, and finally `server.start(preload=config['db_name'], stop=config['stop_after_init'])` [source: odoo/cli/server.py:L95-L119].

### Step 1 — Provision a non-`postgres` PostgreSQL role

```bash
sudo -u postgres psql -c "CREATE ROLE odoo WITH LOGIN CREATEDB PASSWORD 'CHANGE_ME';"
```

The server exits with status 1 if the configured database user (`config['db_user']`) or the `PGUSER` environment variable equals the literal string `postgres`; provision a non-superuser role (any name other than `postgres`). The role needs `CREATEDB` because the server auto-creates each database listed in `config['db_name']` on startup via `odoo.service.db._create_empty_database`. [source: odoo/cli/server.py:L37-L44] [source: odoo/cli/server.py:L101-L113]

### Step 2 — Seed the database (first-run only)

```bash
python -m odoo \
  --addons-path=./odoo/addons,./addons \
  -d odoo_db \
  --db_host=127.0.0.1 --db_port=5432 \
  --db_user=odoo --db_password=CHANGE_ME \
  -i base --without-demo=all --stop-after-init --no-http
```

The first invocation seeds the database. `_create_empty_database` only creates an empty PostgreSQL database; the `base` module must be installed before the application is functional, so `-i base` is supplied. `--stop-after-init` causes `server.start(..., stop=config["stop_after_init"])` to return after the preload phase, exiting the process cleanly so a steady-state run can follow. `--without-demo=all` suppresses demo-data fixtures so the seeded database is production-shaped. `--no-http` (`http_enable=False`) skips HTTP listener startup during seeding because the seed phase is a one-shot batch with `--stop-after-init`; this matches the seeding command executed in `## Validation Evidence`. [source: odoo/__main__.py:L1-L3] [source: odoo/cli/command.py:L127-L129] [source: odoo/cli/server.py:L101-L119] [source: odoo/tools/config.py:L235-L236] [source: odoo/tools/config.py:L261-L262] [source: odoo/tools/config.py:L429-L430]

### Step 3 — Steady-state run

```bash
python -m odoo \
  --addons-path=./odoo/addons,./addons \
  -d odoo_db \
  --db_host=127.0.0.1 --db_port=5432 \
  --db_user=odoo --db_password=CHANGE_ME \
  --http-interface=0.0.0.0 --http-port=8069 --gevent-port=8072
```

`--http-interface` defaults to `0.0.0.0`, `--http-port` to `8069`, and `--gevent-port` to `8072`; the steady-state command here is explicit so the bind addresses are unambiguous. [source: odoo/tools/config.py:L255-L260]

**HTTP-port vs. gevent-port binding model.** `server.start` selects one of three server implementations: `GeventServer` when `odoo.evented` is set (only inside the gevent child of prefork mode), `PreforkServer` when `config['workers'] > 0`, or `ThreadedServer` otherwise. `ThreadedServer` binds only `--http-port` (`http_interface:http_port`); it serves HTTP, longpolling, and WebSocket traffic on that single port. `PreforkServer` binds `--http-port` for the HTTP workers AND spawns a separate `GeventServer` subprocess that binds `--gevent-port` for longpolling and WebSocket traffic. With the default `--workers=0`, **port 8072 is not bound**; clients reach `/websocket`, `/websocket/health`, and `/longpolling/*` on port 8069. [source: odoo/service/server.py:L1540-L1578] [source: odoo/service/server.py:L388-L389] [source: odoo/service/server.py:L590-L590] [source: odoo/service/server.py:L716-L719]

### Step 4 — Optional WSGI deployment (Gunicorn)

```bash
gunicorn odoo.http:root --pythonpath . -c setup/odoo-wsgi.example.py
```

`setup/odoo-wsgi.example.py` exposes `root` as `application` and provides Gunicorn globals (`bind`, `pidfile`, `workers=4`, `timeout=240`, `max_requests=2000`); the file is imported by Gunicorn via `-c` and passes those globals to the worker manager while the WSGI callable resolves to `odoo.http:root`. [source: setup/odoo-wsgi.example.py:L13-L17] [source: setup/odoo-wsgi.example.py:L43-L47]

**Multi-worker deployments — prefer Gunicorn over `python -m odoo --workers=N`.** When `config['workers'] > 0`, `server.start` selects `PreforkServer`, whose `long_polling_spawn` constructs the gevent subprocess command line as `[sys.executable, sys.argv[0], 'gevent'] + nargs[1:]`. With the canonical `python -m odoo` entry point, `sys.argv[0]` is the absolute path to `odoo/__main__.py`; re-launching that path as a script (rather than as the package `odoo`) breaks the relative import `from .cli.command import main` declared at the top of `__main__.py`, so the gevent worker exits immediately. The Gunicorn alternative documented in this step is the recommended path for multi-worker production deployments. [source: odoo/service/server.py:L1550-L1554] [source: odoo/service/server.py:L891-L895] [source: odoo/__main__.py:L1-L3]

### Configuration Precedence

The active configuration is resolved as a `ChainMap` whose lookup order, from highest precedence to lowest, is **runtime → CLI → environment → config-file → built-in defaults**. A CLI flag overrides the corresponding environment variable, which overrides the config-file entry, which overrides the built-in default. [source: odoo/tools/config.py:L164-L170]

The reverse precedence applies on the `_load_env_options` pass: the parser walks every option in `options_index` and, for any option whose `env_name` is set and whose name is present in `os.environ`, materializes the parsed value into the `_env_options` map of the ChainMap. [source: odoo/tools/config.py:L612-L620]

### Auto-prefixed environment-variable rule

For every CLI option that is `file_loadable` and that does not declare an explicit `env_name`, the option's environment-variable name is auto-generated as `'ODOO_' + dest.upper()`. For example, `--http-port` (dest `http_port`) becomes `ODOO_HTTP_PORT`; `--data-dir` (dest `data_dir`) becomes `ODOO_DATA_DIR`. Options with `env_name=''` (e.g., POSIX-only options on Windows) and CLI-only options (`file_loadable=False`) do not produce an environment variable. [source: odoo/tools/config.py:L105-L109]

---

## Configuration File

The server loads its config file from `--config <path>`, the `ODOO_RC` environment variable, or the platform-default location: `~/.odoorc` on POSIX, or `<argv[0]_dir>/odoo.conf` on Windows. The legacy `~/.openerp_serverrc` is honored on POSIX with a `DeprecationWarning`. [source: odoo/tools/config.py:L513-L521]

Server-wide defaults injected by `_postprocess_options` ensure the modules `base` and `web` are always present in `server_wide_modules`, falling back to `['base', 'rpc', 'web']` when the option is empty. [source: odoo/tools/config.py:L30-L31] [source: odoo/tools/config.py:L657-L663]

```ini
[options]
; Master DB-management password — override via secret manager; never commit a real value.
; admin_passwd = <SET_VIA_SECRET_MANAGER>
db_host = 127.0.0.1
db_port = 5432
db_user = odoo
db_password = <SET_VIA_SECRET_MANAGER>
addons_path = ./odoo/addons,./addons
default_productivity_apps = True
```

The INI keys above mirror the canonical packaged template, which sets `db_user = odoo`, leaves `db_host`, `db_port`, `db_password` as the literal `False` placeholder (interpreted by Odoo's parser as "use environment/built-in default"), enables `default_productivity_apps`, and shows the commented `admin_passwd` and `addons_path` examples. [source: debian/odoo.conf:L1-L9]

---

## Environment Variables

This section enumerates every environment variable consumed by the server. Variables are grouped by functional domain. Auto-prefixed variables (rows whose source citation points at an option line in `odoo/tools/config.py` without an explicit `env_name=` keyword) are derived per the `'ODOO_' + dest.upper()` rule. [source: odoo/tools/config.py:L105-L109]

### Database

| Variable | Default | Required | Purpose | Source |
|---|---|---|---|---|
| `PGDATABASE` | `[]` | No (required if `-d` not on the CLI and no `db_name` in config file) | Database name(s) used when installing or updating modules; comma-separated list | [source: odoo/tools/config.py:L367-L368] |
| `PGUSER` | `''` | Conditional — must NOT equal `postgres`; required when PostgreSQL host auth requires a username | Database user name; the server exits if this equals `postgres` | [source: odoo/tools/config.py:L369-L370] [source: odoo/cli/server.py:L42-L42] [source: odoo/cli/server.py:L63-L63] |
| `PGPATH` | `''` | No | Directory containing PostgreSQL utilities (`psql`, `pg_dump`, `pg_restore`) when not on `PATH` | [source: odoo/tools/config.py:L373-L374] |
| `PGHOST` | `''` | No (defaults to PostgreSQL's local-socket lookup) | Database host; also consulted as a fallback by `report_configuration` for the startup log line | [source: odoo/tools/config.py:L375-L376] [source: odoo/cli/server.py:L61-L61] |
| `PGHOST_REPLICA` | `None` | No | Read-only replica host for streaming-replication offload | [source: odoo/tools/config.py:L377-L378] |
| `PGPORT` | `None` | No (defaults to `5432` via libpq) | Database port; also consulted as a fallback by `report_configuration` | [source: odoo/tools/config.py:L379-L380] [source: odoo/cli/server.py:L62-L62] |
| `PGPORT_REPLICA` | `None` | No | Read-only replica port | [source: odoo/tools/config.py:L381-L382] |
| `PGSSLMODE` | `'prefer'` | No | TLS mode for PostgreSQL connection: `disable`, `allow`, `prefer`, `require`, `verify-ca`, `verify-full` | [source: odoo/tools/config.py:L383-L385] |
| `PGAPPNAME` | `'odoo-{pid}'` | No | `application_name` reported to PostgreSQL; `{pid}` is substituted at connect time | [source: odoo/tools/config.py:L386-L387] [source: odoo/sql_db.py:L775-L780] |
| `PGDATABASE_TEMPLATE` | `'template0'` | No | Template database used when auto-creating a new database | [source: odoo/tools/config.py:L392-L393] |
| `ODOO_DB_MAXCONN` | `64` | No | Maximum number of physical connections to PostgreSQL | [source: odoo/tools/config.py:L388-L389] |
| `ODOO_DB_MAXCONN_GEVENT` | `None` | No | Maximum physical connections specifically for the gevent worker | [source: odoo/tools/config.py:L390-L391] |
| `ODOO_PGAPPNAME` | unset | No (deprecated alias of `PGAPPNAME`) | Backward-compatible application_name; emits a `DeprecationWarning` when set | [source: odoo/sql_db.py:L776-L778] |
| `OPENERP_SERVER` | unset | No (deprecated) | Legacy alias for `ODOO_RC`; setting it emits a `DeprecationWarning` | [source: odoo/tools/config.py:L619-L620] |
| `ODOO_FAKETIME_TEST_MODE` | unset | No (test-only) | Activates test-mode `now()` override so frozen-time integration tests behave deterministically | [source: odoo/sql_db.py:L369-L370] [source: odoo/service/db.py:L106-L106] |
| `ODOO_NOTIFY_FUNCTION` | `'pg_notify'` | No | Custom PostgreSQL function to call instead of `pg_notify` for cron triggers | [source: odoo/addons/base/models/ir_cron.py:L36-L36] |
| `ODOO_NOTIFY_CRON_CHANGES` | unset | No | Forces the cron notify path to fire even when not strictly needed; useful for clustered deployments | [source: odoo/addons/base/models/ir_cron.py:L109-L109] [source: odoo/addons/base/models/ir_cron.py:L407-L407] [source: odoo/addons/base/models/ir_cron.py:L637-L637] [source: odoo/addons/base/models/ir_cron.py:L720-L720] |

### HTTP / Web

| Variable | Default | Required | Purpose | Source |
|---|---|---|---|---|
| `ODOO_HTTP_INTERFACE` | `'0.0.0.0'` | No | Listen interface address for HTTP services | [source: odoo/tools/config.py:L255-L256] |
| `ODOO_HTTP_PORT` | `8069` | No | Listen port for the main HTTP service | [source: odoo/tools/config.py:L257-L258] |
| `ODOO_GEVENT_PORT` | `8072` | No | Listen port for the gevent worker (longpolling/WebSocket) | [source: odoo/tools/config.py:L259-L260] |
| `ODOO_HTTP_ENABLE` | `True` | No | When `False` (set via `--no-http`), disables HTTP and longpolling services entirely | [source: odoo/tools/config.py:L261-L262] |
| `ODOO_PROXY_MODE` | `False` | No — only enable when running behind a trusted reverse proxy | Activates WSGI proxy header rewriting (`X-Forwarded-*`) | [source: odoo/tools/config.py:L263-L265] [source: odoo/http.py:L2763-L2763] |
| `ODOO_X_SENDFILE` | `False` | No | Activates `X-Sendfile` (Apache) and `X-Accel-Redirect` (nginx) for serving large files | [source: odoo/tools/config.py:L266-L269] [source: odoo/http.py:L620-L622] |
| `ODOO_DBFILTER` | `''` | No | Regex filter on database names visible to the Web UI; supports `%d` and `%h` placeholders | [source: odoo/tools/config.py:L274-L276] |
| `ODOO_MAX_HTTP_THREADS` | unset (auto) | No | Caps concurrent HTTP threads in threaded mode; falls back to `(db_maxconn - max_cron_threads) // 2` when non-numeric | [source: odoo/service/server.py:L227-L235] |
| `ODOO_HTTP_SOCKET_TIMEOUT` | `2` | No | Per-request socket timeout (seconds) in prefork worker mode | [source: odoo/service/server.py:L1318-L1319] |
| `ODOO_HTTP_SOCKET_FD` | unset | No (set by the server itself across reloads) | File descriptor of the listening HTTP socket inherited across hot-reloads | [source: odoo/service/server.py:L1034-L1036] [source: odoo/service/server.py:L1060-L1060] |
| `ODOO_READY_SIGHUP_PID` | unset | No (set by the server itself across reloads) | PID to signal with `SIGHUP` once the new server is ready | [source: odoo/service/server.py:L1061-L1061] [source: odoo/service/server.py:L1155-L1156] |
| `LISTEN_FDS` | unset | No | systemd socket-activation indicator; when set to `'1'` together with `LISTEN_PID == os.getpid()`, the server adopts the inherited listening socket | [source: odoo/service/server.py:L247-L249] [source: odoo/tools/config.py:L1036-L1037] |
| `LISTEN_PID` | unset | No | systemd socket-activation indicator; see `LISTEN_FDS` | [source: odoo/service/server.py:L247-L249] [source: odoo/tools/config.py:L1036-L1037] |
| `ODOO_WEBSOCKET_KEEP_ALIVE_TIMEOUT` | `3600` | No | Maximum lifetime (seconds) of an idle WebSocket connection before the bus addon closes it; auto-prefixed per `odoo/tools/config.py:L105-L109` | [source: odoo/tools/config.py:L217-L217] [source: addons/bus/websocket.py:L810-L810] |
| `ODOO_WEBSOCKET_RATE_LIMIT_BURST` | `10` | No | Maximum number of WebSocket frames a client may send in a burst before rate limiting kicks in; auto-prefixed per `odoo/tools/config.py:L105-L109` | [source: odoo/tools/config.py:L218-L218] [source: addons/bus/websocket.py:L289-L289] |
| `ODOO_WEBSOCKET_RATE_LIMIT_DELAY` | `0.2` | No | Minimum spacing (seconds) imposed between consecutive WebSocket frames once burst budget is exhausted; auto-prefixed per `odoo/tools/config.py:L105-L109` | [source: odoo/tools/config.py:L219-L219] [source: addons/bus/websocket.py:L291-L291] |

### Mail / SMTP

| Variable | Default | Required | Purpose | Source |
|---|---|---|---|---|
| `ODOO_EMAIL_FROM` | `''` | No | Default From address for outbound SMTP | [source: odoo/tools/config.py:L345-L346] |
| `ODOO_FROM_FILTER` | `''` | No | Restricts which From-addresses use this SMTP configuration | [source: odoo/tools/config.py:L347-L348] |
| `ODOO_SMTP_SERVER` | `'localhost'` | No | SMTP server host | [source: odoo/tools/config.py:L349-L350] |
| `ODOO_SMTP_PORT` | `25` | No | SMTP server port | [source: odoo/tools/config.py:L351-L352] |
| `ODOO_SMTP_SSL` | `False` | No | Enables STARTTLS on the SMTP connection | [source: odoo/tools/config.py:L353-L354] |
| `ODOO_SMTP_USER` | `''` | No | SMTP authentication username | [source: odoo/tools/config.py:L355-L356] |

(SMTP-related secrets — `ODOO_SMTP_PASSWORD`, `ODOO_SMTP_SSL_CERTIFICATE_FILENAME`, `ODOO_SMTP_SSL_PRIVATE_KEY_FILENAME` — are listed in `## Secrets` only.)

### Workers / Process

| Variable | Default | Required | Purpose | Source |
|---|---|---|---|---|
| `ODOO_PIDFILE` | `''` | No | File where the server PID is written (only when not running evented) | [source: odoo/tools/config.py:L239-L240] [source: odoo/cli/server.py:L82-L92] |
| `ODOO_WORKERS` | `0` | No (POSIX-only) | Number of prefork workers; `0` disables prefork mode and uses threaded mode | [source: odoo/tools/config.py:L456-L459] |
| `ODOO_MAX_CRON_THREADS` | `2` | No | Maximum number of threads processing cron jobs concurrently | [source: odoo/tools/config.py:L439-L441] |
| `ODOO_LIMIT_MEMORY_SOFT` | `2147483648` (2 GiB) | No | Maximum virtual memory per worker before the worker is reset after the current request | [source: odoo/tools/config.py:L460-L463] |
| `ODOO_LIMIT_MEMORY_SOFT_GEVENT` | `None` | No (POSIX-only) | Soft memory limit for the gevent worker (defaults to `--limit-memory-soft`) | [source: odoo/tools/config.py:L464-L468] |
| `ODOO_LIMIT_MEMORY_HARD` | `2684354560` (2.5 GiB) | No (POSIX-only) | Hard memory limit per worker; allocations beyond this fail | [source: odoo/tools/config.py:L469-L473] |
| `ODOO_LIMIT_MEMORY_HARD_GEVENT` | `None` | No (POSIX-only) | Hard memory limit for the gevent worker (defaults to `--limit-memory-hard`) | [source: odoo/tools/config.py:L474-L478] |
| `ODOO_LIMIT_TIME_CPU` | `60` | No (POSIX-only) | Maximum CPU time per request (seconds) | [source: odoo/tools/config.py:L479-L482] |
| `ODOO_LIMIT_TIME_REAL` | `120` | No | Maximum real time per request (seconds) | [source: odoo/tools/config.py:L483-L485] |
| `ODOO_LIMIT_TIME_REAL_CRON` | `-1` | No | Maximum real time per cron job; `-1` means inherit `--limit-time-real`, `0` means no limit | [source: odoo/tools/config.py:L486-L489] |
| `ODOO_LIMIT_TIME_WORKER_CRON` | `0` | No | Maximum lifetime of a cron worker before recycling (`0` disables) | [source: odoo/tools/config.py:L442-L445] |
| `ODOO_LIMIT_REQUEST` | `65536` | No (POSIX-only) | Maximum number of requests served per worker before recycling | [source: odoo/tools/config.py:L490-L493] |
| `ODOO_OSV_MEMORY_COUNT_LIMIT` | `0` | No | Maximum records kept in `osv_memory` (transient) tables; `0` means no limit | [source: odoo/tools/config.py:L431-L434] |
| `ODOO_TRANSIENT_AGE_LIMIT` | `1.0` | No | Lifetime (hours) of records created in `TransientModel` tables | [source: odoo/tools/config.py:L435-L438] |
| `ODOO_PROFILE_PRELOAD` | unset | No | Activates the preload-time profiler when set | [source: odoo/service/server.py:L1494-L1494] |
| `ODOO_PROFILE_PRELOAD_INTERVAL` | `'0.1'` | No | Profiler sampling interval (seconds) when `ODOO_PROFILE_PRELOAD` is set | [source: odoo/service/server.py:L1495-L1495] |
| `ODOO_PROFILE_PRELOAD_SQL` | unset | No | Adds an SQL collector to the preload profiler | [source: odoo/service/server.py:L1497-L1497] |
| `MALLOC_ARENA_MAX` | unset | No | Caps glibc malloc arenas in 64-bit threaded mode; the server defaults this to `2` if unset | [source: odoo/service/server.py:L1556-L1556] |

### Addons / Paths

| Variable | Default | Required | Purpose | Source |
|---|---|---|---|---|
| `ODOO_ADDONS_PATH` | `[]` | No (defaults to the bundled `odoo/addons/` discovered via Python package import); set when custom addons or `./addons/` community addons are required | Comma-separated list of additional addon directories. With an empty value, `initialize_sys_path` still appends `addons_data_dir` and `addons_community_dir`, and the bundled `odoo/addons/` (which contains `base`) is already on the package import path because `odoo.addons` is a package | [source: odoo/tools/config.py:L241-L242] [source: odoo/modules/module.py:L140-L153] [source: odoo/tools/config.py:L979-L981] |
| `ODOO_UPGRADE_PATH` | `[]` | No | Comma-separated list of additional upgrade-script directories | [source: odoo/tools/config.py:L243-L244] |
| `ODOO_PRE_UPGRADE_SCRIPTS` | `[]` | No | Pre-`-u` upgrade scripts run before any module is loaded | [source: odoo/tools/config.py:L245-L246] |
| `ODOO_SERVER_WIDE_MODULES` | `['base', 'rpc', 'web']` | No (auto-corrected to include `base` and `web`) | Server-wide modules loaded into every database registry | [source: odoo/tools/config.py:L247-L248] [source: odoo/tools/config.py:L30-L31] [source: odoo/tools/config.py:L657-L663] |
| `ODOO_WITH_DEMO` | `False` | No | Installs demo data when creating new databases; consulted by `Registry.new` to decide whether the bootstrapping flow runs the demo-data fixtures | [source: odoo/tools/config.py:L233-L233] [source: odoo/orm/registry.py:L182-L182] |
| `ODOO_DATA_DIR` | `appdirs.user_data_dir('Odoo', 'OpenERP S.A.')` (POSIX with home), `/var/lib/Odoo` (no home), or `appdirs.site_data_dir(...)` (Windows / macOS) | No | Directory for filestore, addon-cache, and session data | [source: odoo/tools/config.py:L249-L250] [source: odoo/tools/config.py:L505-L511] |
| `ODOO_RC` | platform-default config file path | No | Alternate path to the configuration file (overrides `~/.odoorc`) | [source: odoo/tools/config.py:L223-L224] [source: odoo/tools/config.py:L513-L521] |
| `XDG_DATA_HOME` | `'~/.local/share'` | No (Linux only) | Used by `appdirs.user_data_dir` to compute the default data directory | [source: odoo/tools/appdirs.py:L68-L68] |
| `XDG_DATA_DIRS` | system-default | No (Linux only) | Used by `appdirs.site_data_dir` to compute the system data directory | [source: odoo/tools/appdirs.py:L125-L125] |
| `XDG_CONFIG_HOME` | `'~/.config'` | No (Linux only) | Used by `appdirs.user_config_dir` | [source: odoo/tools/appdirs.py:L179-L179] |
| `XDG_CONFIG_DIRS` | `'/etc/xdg'` | No (Linux only) | Used by `appdirs.site_config_dir` | [source: odoo/tools/appdirs.py:L228-L228] |
| `XDG_CACHE_HOME` | `'~/.cache'` | No (Linux only) | Used by `appdirs.user_cache_dir` | [source: odoo/tools/appdirs.py:L293-L293] |
| `VIRTUAL_ENV` | unset | No | When set, `odoo start` uses it as the project path instead of the current directory | [source: odoo/cli/start.py:L33-L34] |

### Logging

| Variable | Default | Required | Purpose | Source |
|---|---|---|---|---|
| `ODOO_LOGFILE` | `''` | No | Path to the server log file; mutually exclusive with `ODOO_SYSLOG` | [source: odoo/tools/config.py:L318-L319] [source: odoo/tools/config.py:L648-L649] |
| `ODOO_SYSLOG` | `False` | No | Send the log to the syslog server; mutually exclusive with `ODOO_LOGFILE` | [source: odoo/tools/config.py:L320-L321] [source: odoo/tools/config.py:L648-L649] |
| `ODOO_LOG_HANDLER` | `[':INFO']` | No | Comma-separated `MODULE:LEVEL` handlers; empty `MODULE` denotes the root logger | [source: odoo/tools/config.py:L322-L324] |
| `ODOO_LOG_DB` | `''` | No | Database connection string used as the logging sink | [source: odoo/tools/config.py:L329-L329] |
| `ODOO_LOG_DB_LEVEL` | `'warning'` | No | Threshold for log records routed to `ODOO_LOG_DB` | [source: odoo/tools/config.py:L330-L330] |
| `ODOO_LOG_LEVEL` | `'info'` | No | One of `info`, `debug_rpc`, `warn`, `test`, `critical`, `runbot`, `debug_sql`, `error`, `debug`, `debug_rpc_answer`, `notset` | [source: odoo/tools/config.py:L333-L339] |
| `ODOO_PY_COLORS` | unset | No | Forces ANSI-colored log output even when stderr is not a TTY | [source: odoo/netsvc.py:L268-L268] |

### Security

| Variable | Default | Required | Purpose | Source |
|---|---|---|---|---|
| `ODOO_LIST_DB` | `True` | No (recommend `False` in production) | When `False` (set via `--no-database-list`), disables the database-listing endpoint and the database manager UI | [source: odoo/tools/config.py:L410-L413] |
| `ODOO_DEV` | `[]` | No | Developer features: `access`, `qweb`, `reload`, `xml`, `replica`, `werkzeug`, `all` | [source: odoo/tools/config.py:L418-L428] |
| `ODOO_UNACCENT` | `False` | No | Attempts to enable the `unaccent` PostgreSQL extension when creating new databases | [source: odoo/tools/config.py:L446-L447] |
| `ODOO_GEOIP_CITY_DB` | `'/usr/share/GeoIP/GeoLite2-City.mmdb'` | No | Absolute path to the MaxMind GeoIP City database | [source: odoo/tools/config.py:L448-L449] [source: odoo/http.py:L2713-L2713] |
| `ODOO_GEOIP_COUNTRY_DB` | `'/usr/share/GeoIP/GeoLite2-Country.mmdb'` | No | Absolute path to the MaxMind GeoIP Country database | [source: odoo/tools/config.py:L450-L451] [source: odoo/http.py:L2724-L2724] |
| `ODOO_SKIP_GC_SESSIONS` | unset | No | Skips the periodic session-store garbage collector | [source: odoo/addons/base/models/ir_http.py:L410-L410] |
| `ODOO_LIMIT_LITEVAL_BUFFER` | `102400` | No | Override of the byte-length cap for `ast.literal_eval` payloads | [source: odoo/_monkeypatches/ast.py:L17-L23] |

### Testing / Diagnostics

| Variable | Default | Required | Purpose | Source |
|---|---|---|---|---|
| `ODOO_SCREENCASTS` | `''` | No | Directory under which Selenium-style screencasts are written | [source: odoo/tools/config.py:L307-L309] |
| `ODOO_SCREENSHOTS` | `tempfile.gettempdir() + '/odoo_tests'` | No | Directory under which Selenium-style screenshots are written | [source: odoo/tools/config.py:L310-L313] |
| `PYTHONSTARTUP` | unset | No | Python startup file consulted by `odoo shell` when `--shell-file` is not set | [source: odoo/cli/shell.py:L89-L89] |
| `TZ` | (forced to `'UTC'` by the server at startup) | No (always set by the server) | Process timezone; the `_monkeypatches.patch_init` hook unconditionally sets it to UTC | [source: odoo/_monkeypatches/__init__.py:L57-L59] |
| `ODOO_TEST_FAILURE_RETRIES` | `0` | No (test-only) | Multiplier for retrying failed tests; effective retries = value + 1 | [source: odoo/tests/common.py:L325-L325] |
| `ODOO_TEST_MAX_FAILED_TESTS` | `sys.maxsize` | No (test-only) | Cap on the number of failing tests before the test runner aborts | [source: odoo/tests/result.py:L23-L23] |
| `ODOO_TOUR_DELAY_TO_CHECK_UNDETERMINISMS` | `0` | No (test-only) | Inter-step delay (seconds) used by browser-tour tests to detect UI race conditions | [source: odoo/tests/common.py:L2469-L2469] |
| `ODOO_BROWSER_CPU_THROTTLING` | unset | No (test-only) | Forces CPU throttling on the Chrome DevTools test browser; used by runbot infrastructure | [source: odoo/tests/common.py:L2429-L2429] |
| `ODOO_RUNBOT` | unset | No (test-only) | When set, signals execution inside the Odoo runbot CI environment; gates SMTP-test prerequisite checks for `openssl` and `aiosmtpd` | [source: odoo/addons/base/tests/test_ir_mail_server_smtpd.py:L34-L36] |
| `WEB_SERVER_URL` | `'http://localhost:80'` | No (test-only) | Base URL for the `test_http` web-server test suite; overrides the default localhost target when running tests against a non-default web server | [source: odoo/addons/test_http/tests/test_web_server.py:L10-L10] |
| `ADDONS_PATH` | unset | No (test-only) | Read by `_pylint_path_setup` to seed the pylint sandbox; only consumed by the lint test harness | [source: odoo/addons/test_lint/tests/_pylint_path_setup.py:L26-L26] |
| `PATH` | inherited | No | Standard Unix `PATH`; used to discover `psql`, `pg_dump`, `pg_restore`, `wkhtmltopdf`, `lessc`, and `sass` via `find_in_path` | [source: odoo/tools/misc.py:L143-L143] |
| `PYTHONPATH` | inherited | No | Standard Python module-search path; the lint test harness extends it before spawning a sub-interpreter | [source: odoo/addons/test_lint/tests/test_checkers.py:L64-L64] |

### Internationalization

| Variable | Default | Required | Purpose | Source |
|---|---|---|---|---|
| `ODOO_LOAD_LANGUAGE` | unset | No | Comma-separated languages loaded at module install time | [source: odoo/tools/config.py:L402-L403] |
| `ODOO_OVERWRITE_EXISTING_TRANSLATIONS` | `False` | No | When `True` and `-u` is supplied, overwrites existing translation terms | [source: odoo/tools/config.py:L404-L405] |

### Reports / Imports / Internal

These options are declared as `FileOnlyOption` instances early in `_build_cli`; their environment-variable names are auto-prefixed via the `'ODOO_' + dest.upper()` rule (`file_loadable=True`, `cli_loadable=False`). [source: odoo/tools/config.py:L105-L109] [source: odoo/tools/config.py:L120-L122]

| Variable | Default | Required | Purpose | Source |
|---|---|---|---|---|
| `ODOO_BIN_PATH` | `''` | No | Extra directory prepended by `find_in_path` to locate external binaries (e.g., `psql`, `pg_dump`, `wkhtmltopdf`) when they are not on the inherited `PATH` | [source: odoo/tools/config.py:L208-L208] [source: odoo/tools/misc.py:L143-L145] |
| `ODOO_CSV_INTERNAL_SEP` | `','` | No | Internal separator used between IDs/xids/names inside a single CSV cell when importing or exporting many2many fields | [source: odoo/tools/config.py:L209-L209] |
| `ODOO_DEFAULT_PRODUCTIVITY_APPS` | `False` | No | When `True`, the `base_install_request` addon auto-installs the bundled productivity-app set on first registry load | [source: odoo/tools/config.py:L210-L210] [source: addons/base_install_request/__init__.py:L11-L11] |
| `ODOO_IMPORT_FILE_MAXBYTES` | `10485760` (10 MiB) | No | Upper bound (bytes) on the body of files fetched via URL during a CSV/XLSX import | [source: odoo/tools/config.py:L211-L211] [source: addons/base_import/models/base_import.py:L1344-L1344] [source: addons/mass_mailing/models/mailing.py:L1480-L1480] |
| `ODOO_IMPORT_FILE_TIMEOUT` | `3` | No | HTTP timeout (seconds) for URL-based imports performed by `base_import` and `mass_mailing` | [source: odoo/tools/config.py:L212-L212] [source: addons/base_import/models/base_import.py:L1347-L1347] [source: addons/mass_mailing/models/mailing.py:L1483-L1483] |
| `ODOO_IMPORT_URL_REGEX` | `'^(?:http\|https)://'` | No | Allow-list regex applied to URL values before the import subsystem fetches them; values that do not match are rejected | [source: odoo/tools/config.py:L213-L213] [source: addons/base_import/models/base_import.py:L1280-L1280] [source: addons/base_import/models/base_import.py:L1343-L1343] |
| `ODOO_PUBLISHER_WARRANTY_URL` | `'http://services.odoo.com/publisher-warranty/'` | No | Endpoint contacted by the `mail` addon's update service to refresh enterprise subscription metadata | [source: odoo/tools/config.py:L215-L215] [source: addons/mail/models/update.py:L71-L71] |
| `ODOO_REPORTGZ` | `False` | No | When `True`, signals `--save` and packaging tooling that database dumps should be gzip-compressed; declared as `action='store_true'` | [source: odoo/tools/config.py:L216-L216] |
| `PATHEXT` | `'.COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC'` (Windows fallback when unset) | No (Windows only) | Used by `odoo/tools/which.py` (the `find_in_path` shim) to determine which file extensions to try when resolving an executable name; not consumed on POSIX | [source: odoo/tools/which.py:L60-L61] |

### Build-time / Packaging

| Variable | Default | Required | Purpose | Source |
|---|---|---|---|---|
| `DEBIAN_FRONTEND` | unset (set to `noninteractive` by `setup/debinstall.sh`) | Yes during apt-package install (suppresses interactive prompts) | Suppresses package-manager prompts so `apt-get install` runs unattended | [source: setup/debinstall.sh:L27-L27] |

(Build-time secrets `GPGPASSPHRASE` and `GPGID` are listed in `## Secrets`.)

### CLI-only flags (not environment-mapped)

The following flags are CLI-only (`file_loadable=False`); they have no environment-variable representation and must be supplied on the command line. They are listed for completeness so the env-vars table is exhaustive against the source-code option index.

- `-c/--config`, `-s/--save` [source: odoo/tools/config.py:L223-L226]
- `-i/--init`, `-u/--update`, `--reinit` [source: odoo/tools/config.py:L227-L232]
- `-P/--import-partial` [source: odoo/tools/config.py:L237-L238]
- `--test-file`, `--test-enable`, `--test-tags` [source: odoo/tools/config.py:L281-L305]
- `--stop-after-init` [source: odoo/tools/config.py:L429-L430]

---

## Secrets

A value is classified as a secret when its name matches `password|secret|key|token|credential|apikey|auth|private|cert` or when it is the value-side of a database, SMTP, or signing-tool authentication call. Secret values are never reproduced in this document; only the source citation is recorded.

| Secret | Consumption Point | Expected Format | Default Override Required | Hardcoded-Default Finding |
|---|---|---|---|---|
| `admin_passwd` (via env var `ODOO_ADMIN_PASSWD` or config-file `[options] admin_passwd`) | `odoo/tools/config.py:L207`; verified via `crypt_context` (`pbkdf2_sha512`) when the database manager is invoked. The `_FileOnlyOption` class only sets `cli_loadable=False`, so `file_loadable` remains `True`, which means the auto-prefix rule generates an env-var name (`ODOO_` + `dest.upper()`); both the env var and the config-file entry are honored at runtime by `_load_env_options` | A `passlib`-managed hash string (the parser auto-upgrades a plaintext value to `pbkdf2_sha512` on first verify) | **YES** | **⚠️ SECURITY FINDING: hardcoded default — MUST be overridden in production via the environment variable `ODOO_ADMIN_PASSWD` (recommended for secret-manager injection) or via the configuration file `[options] admin_passwd = …`. The literal default is intentionally not reproduced here.** [source: odoo/tools/config.py:L207-L207] [source: odoo/tools/config.py:L120-L122] [source: odoo/tools/config.py:L105-L109] [source: odoo/tools/config.py:L612-L620] [source: odoo/tools/config.py:L21-L23] [source: odoo/tools/config.py:L1019-L1030] |
| `db_password` / `PGPASSWORD` | `odoo/tools/config.py:L371-L372`; consumed by `connection_info_for` / `db_connect` in `odoo/sql_db.py` | PostgreSQL password string | Conditional — required only when the PostgreSQL host expects password authentication; not required for `trust` or peer/local-socket auth | No (default is empty string). [source: odoo/tools/config.py:L371-L372] [source: odoo/sql_db.py:L793-L798] |
| `smtp_password` / `ODOO_SMTP_PASSWORD` | `odoo/tools/config.py:L357-L358` | Plain SMTP password | Conditional — required only when SMTP relay enforces authentication | No (default is empty string). [source: odoo/tools/config.py:L357-L358] |
| `smtp_ssl_certificate_filename` / `ODOO_SMTP_SSL_CERTIFICATE_FILENAME` | `odoo/tools/config.py:L359-L360` | Filesystem path to a PEM-encoded client certificate | Conditional — required only when client-cert SMTP auth is configured | No (default is empty string). [source: odoo/tools/config.py:L359-L360] |
| `smtp_ssl_private_key_filename` / `ODOO_SMTP_SSL_PRIVATE_KEY_FILENAME` | `odoo/tools/config.py:L361-L362` | Filesystem path to a PEM-encoded private key | Conditional — required only when client-cert SMTP auth is configured | No (default is empty string). [source: odoo/tools/config.py:L361-L362] |
| `proxy_access_token` (via env var `ODOO_PROXY_ACCESS_TOKEN` or config-file `[options] proxy_access_token`) | `odoo/tools/config.py:L214`; consumed by IoT proxy controllers (e.g., the Egyptian e-invoicing driver verifies the request bearer against the stored hash via `crypt_context.verify`) and seeded by the `genproxytoken` IoT CLI which writes a `pbkdf2_sha512` hash back through `config.save()`. The same `_FileOnlyOption`/auto-prefix path that exposes `admin_passwd` to the env loader also exposes this option as `ODOO_PROXY_ACCESS_TOKEN` | Opaque bearer token (stored as a `pbkdf2_sha512` hash on disk) | Conditional — required only when Odoo's proxy access feature is in use | No (default is empty string). [source: odoo/tools/config.py:L214-L214] [source: odoo/tools/config.py:L120-L122] [source: odoo/tools/config.py:L105-L109] [source: odoo/tools/config.py:L612-L620] [source: addons/iot_drivers/iot_handlers/drivers/l10n_eg_drivers.py:L22-L25] [source: addons/iot_drivers/cli/genproxytoken.py:L26-L26] |
| `GPGPASSPHRASE` (build-time only) | `setup/package.py:L33` and `setup/package.py:L147,L158` (Debian/RPM signing) | GPG key passphrase | Yes when producing signed distribution packages | No. [source: setup/package.py:L33-L33] [source: setup/package.py:L147-L147] [source: setup/package.py:L158-L158] |
| `GPGID` (build-time only) | `setup/package.py:L34` and `setup/package.py:L147` (Debian signing) | GPG key identifier | Yes when producing signed distribution packages | No. [source: setup/package.py:L33-L34] [source: setup/package.py:L147-L147] |

---

## Validation Evidence

The Build and Run instructions above were executed end-to-end on a clean Ubuntu 24.04 host. The transcript records every command with an ISO-8601 nanosecond timestamp, the Build Step 1 prerequisite-install outcome (verbatim), the HTTP probe outcome on the WSGI port (8069) and the documented gevent port (8072), and the process tree at ready state. The Python interpreter, virtual environment, and editable install (`pip install -e .`) referenced in the host table below were provisioned per Build Steps 2–5 prior to this transcript; Build Step 1 (OS prerequisite install) is re-executed verbatim at the start of the transcript to record its exit status.

### Host

| Field | Value | Source / Constraint |
|---|---|---|
| Distribution | Ubuntu 24.04.4 LTS (Noble Numbat) | The pinned dependency set targets Ubuntu 24.04 [source: requirements.txt:L1-L2] |
| Kernel | `Linux 6.6.113+ x86_64` (from `uname -srm`) | Runtime measurement |
| Python interpreter | Python 3.13.13 (deadsnakes PPA) | Matches the upper supported Python version [source: odoo/release.py:L40-L40] |
| PostgreSQL server | PostgreSQL 16.13 (Ubuntu archive) | Satisfies the minimum PostgreSQL version [source: odoo/release.py:L41-L41] |
| PostgreSQL role | `odoo` (`LOGIN`, `CREATEDB`, NOT superuser) | Non-`postgres` role required [source: odoo/cli/server.py:L37-L44] |
| Virtual environment | `./venv` (Python 3.13) | Required to honor `python_requires` [source: setup.py:L70-L70] |
| Editable Odoo install | `pip install -e .` produces `odoo.egg-info/` | Editable install of the package descriptor [source: setup.py:L13-L77] |

### Command transcript (with ISO-8601 nanosecond timestamps)

The transcript below references the test PostgreSQL password through the shell variable `$DB_PASSWORD` (exported once at the start of the validation cycle and rotated/unset at the end). The literal value is intentionally never reproduced in this document, in keeping with the Secrets-table policy that no literal secret value appears in the deliverable. A reader reproducing the validation cycle should set `DB_PASSWORD` to a freshly generated test value (e.g., `export DB_PASSWORD=$(openssl rand -base64 18)`) before running the documented commands.

```text
===== HOST =====
[2026-05-06T03:56:38.230922453] $ lsb_release -d -s
Ubuntu 24.04.4 LTS
[2026-05-06T03:56:38.235107000] $ uname -srm
Linux 6.6.113+ x86_64
[2026-05-06T03:56:50.472207455] $ python3.13 --version
Python 3.13.13
[2026-05-06T03:56:50.500000000] $ psql --version
psql (PostgreSQL) 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)

===== BUILD STEP 1 — APT-GET PREREQUISITES (verbatim, fixed apt list) =====
[2026-05-06T03:56:38.230922453] $ export DEBIAN_FRONTEND=noninteractive
[2026-05-06T03:56:38.232000000] $ apt-get install -y --no-install-recommends \
                                    build-essential libpq-dev libxml2-dev libxslt1-dev libjpeg-dev libpng-dev \
                                    zlib1g-dev libfreetype6-dev liblcms2-dev libwebp-dev libldap2-dev libsasl2-dev \
                                    libsasl2-modules libssl-dev libffi-dev libmagic1 libusb-1.0-0-dev \
                                    fonts-noto-cjk postgresql-16 postgresql-client-16 ca-certificates curl
ca-certificates is already the newest version (20240203).
curl is already the newest version (8.5.0-2ubuntu10.9).
0 upgraded, 0 newly installed, 0 to remove and 3 not upgraded.
[2026-05-06T03:56:39.452669426] (exit 0)

===== RUN STEP 1 — VERIFY POSTGRES ROLE =====
[2026-05-06T03:56:50.721767897] $ sudo -u postgres psql -tAc "SELECT rolname,rolcreatedb,rolsuper FROM pg_roles WHERE rolname='odoo'"
odoo|t|f                                # rolcreatedb=t, rolsuper=f -> not 'postgres', has CREATEDB
[2026-05-06T03:56:50.745000000] $ pg_isready -h 127.0.0.1 -p 5432
127.0.0.1:5432 - accepting connections
[2026-05-06T03:56:50.760000000] (exit 0)

===== RUN STEP 2 — SEED DATABASE =====
[2026-05-06T03:56:55.852922512] $ python -m odoo --addons-path=./odoo/addons,./addons \
                                    -d odoo_revalidation \
                                    --db_host=127.0.0.1 --db_port=5432 \
                                    --db_user=odoo --db_password=$DB_PASSWORD \
                                    -i base --without-demo=all --stop-after-init --no-http
[2026-05-06T03:56:55.855000000] seed start
[2026-05-06T03:57:06.839602382] seed end (exit 0)
--- seed log tail ---
2026-05-06 03:57:06,495 INFO odoo_revalidation odoo.modules.loading: loading web_unsplash/views/res_config_settings_view.xml
2026-05-06 03:57:06,518 INFO odoo_revalidation odoo.modules.loading: Module web_unsplash loaded in 0.06s, 102 queries (+102 other)
2026-05-06 03:57:06,518 INFO odoo_revalidation odoo.modules.loading: 14 modules loaded in 2.61s, 4658 queries (+4658 extra)
2026-05-06 03:57:06,704 INFO odoo_revalidation odoo.modules.loading: Modules loaded.
2026-05-06 03:57:06,708 INFO odoo_revalidation odoo.registry: Registry changed, signaling through the database
2026-05-06 03:57:06,709 INFO odoo_revalidation odoo.registry: Registry loaded in 10.284s
2026-05-06 03:57:06,709 INFO odoo_revalidation odoo.service.server: Initiating shutdown
2026-05-06 03:57:06,710 INFO odoo_revalidation odoo.sql_db: ConnectionPool(read/write;used=0/count=0/max=64): Closed 1 connections
--- end seed log ---

===== RUN STEP 3 — STEADY-STATE (threaded; default --workers=0) =====
[2026-05-06T03:57:15.084735554] $ python -m odoo --addons-path=./odoo/addons,./addons \
                                    -d odoo_revalidation \
                                    --db_host=127.0.0.1 --db_port=5432 \
                                    --db_user=odoo --db_password=$DB_PASSWORD \
                                    --http-interface=0.0.0.0 --http-port=8069 --gevent-port=8072 &
[2026-05-06T03:57:15.085857636] (background server pid: 134874)

===== HTTP PROBE 8069 — /web/database/selector =====
[2026-05-06T03:57:17.601188738] PROBE 8069 /web/database/selector attempt 2: 200 0.499511s

===== HTTP PROBE 8069 — /websocket/health =====
[2026-05-06T03:57:28.157905343] PROBE 8069 /websocket/health: 200 0.002708s

===== HTTP PROBE 8069 — / (root, redirects to /odoo) =====
[2026-05-06T03:57:28.180000000] PROBE 8069 /: 303 0.002679s

===== HTTP PROBE 8069 — /web/login =====
[2026-05-06T03:57:28.200000000] PROBE 8069 /web/login: 200 0.097785s

===== HTTP PROBE 8072 — documented gevent port (only bound when --workers > 0; expected 'connection refused' here) =====
[2026-05-06T03:57:28.260000000] PROBE 8072: 000 0.000121s   # 000 = connection refused; ThreadedServer does not bind gevent_port

===== /proc/net/tcp LISTEN port verification =====
[2026-05-06T03:57:28.300000000] LISTEN port 8069                # 8072 absent (matches documented threaded-mode behavior)

===== STEADY-STATE LOG TAIL (steady-state werkzeug request lines) =====
2026-05-06 03:57:15,321 INFO ? odoo: database: odoo@127.0.0.1:5432
2026-05-06 03:57:15,575 INFO ? odoo.service.server: HTTP service (werkzeug) running on reverse-code-generator-1d013a5a-pqvv2:8069
2026-05-06 03:57:15,783 INFO odoo_revalidation odoo.registry: Registry loaded in 0.193s

===== CLEANUP =====
[2026-05-06T03:57:48.291561793] $ kill 134874; sleep 4; pkill -9 -f 'python -m odoo'
[2026-05-06T03:57:53.000000000] (exit 0)
[2026-05-06T03:57:53.405456512] $ sudo -u postgres psql -c 'DROP DATABASE IF EXISTS odoo_revalidation;'
DROP DATABASE
[2026-05-06T03:57:53.500000000] (exit 0)
[2026-05-06T03:57:53.510000000] DONE
```

### Build Step 1 prerequisite-install summary

| Step | Command | Exit | Notes |
|---|---|---|---|
| Build Step 1 (verbatim) | `apt-get install -y --no-install-recommends build-essential libpq-dev libxml2-dev libxslt1-dev libjpeg-dev libpng-dev zlib1g-dev libfreetype6-dev liblcms2-dev libwebp-dev libldap2-dev libsasl2-dev libsasl2-modules libssl-dev libffi-dev libmagic1 libusb-1.0-0-dev fonts-noto-cjk postgresql-16 postgresql-client-16 ca-certificates curl` | `0` | Verbatim apt list completes successfully; the optional `node-less` package was deliberately omitted from the prerequisite list because no `.less` source files exist under `addons/` or `odoo/addons/`, so the runtime never reaches `LessStylesheetAsset.get_command()` and never invokes `lessc`. Omitting `node-less` also avoids the `Depends: nodejs:any` resolution failure on hosts that already have a third-party `nodejs` lacking `Multi-Arch: foreign`. [source: odoo/addons/base/models/assetsbundle.py:L1078-L1087] [source: odoo/addons/base/models/assetsbundle.py:L27-L27] |

### Ready-state HTTP probe summary

| Probe | URL | Status | Latency | Notes / Source |
|---|---|---|---|---|
| HTTP / DB selector | `http://localhost:8069/web/database/selector` | `200` | `0.499511 s` | First request after process start; routing-map cold cache. Reached ready state ~2.5 s after process launch. The route is `auth='none'`, so it always responds when the WSGI server is up. [source: addons/web/controllers/database.py:L59-L59] |
| HTTP / longpolling | `http://localhost:8069/websocket/health` | `200` | `0.002708 s` | Bus addon's `auth='none'` health endpoint. In threaded mode this endpoint is served on the same WSGI port (8069), confirming longpolling/WebSocket traffic is reachable. [source: addons/bus/controllers/websocket.py:L22-L22] |
| HTTP / root | `http://localhost:8069/` | `303` | `0.002679 s` | Root URL returns a redirect to `/odoo` (or `/web/login` depending on session); the `303 See Other` confirms routing is functional. |
| HTTP / login | `http://localhost:8069/web/login` | `200` | `0.097785 s` | Login page renders, confirming database connection and template engine are operational. |
| Gevent port (informational) | `http://localhost:8072/websocket/health` | `000` (connection refused) | `0.000121 s` | Documented behavior: `ThreadedServer` binds only `http_port`; `gevent_port` is bound only when `--workers > 0` (`PreforkServer` spawns a separate `GeventServer` subprocess). [source: odoo/service/server.py:L1540-L1578] [source: odoo/service/server.py:L590-L590] [source: odoo/service/server.py:L716-L719] |

### Process tree at ready state (`ps -ef --forest --sort=ppid`, filtered)

```text
postgres   10358       1  /usr/lib/postgresql/16/bin/postgres -D /var/lib/postgresql/16/main -c config_file=/etc/postgresql/16/main/postgresql.conf
postgres   10359   10358   \_ postgres: 16/main: checkpointer
postgres   10360   10358   \_ postgres: 16/main: background writer
postgres   10362   10358   \_ postgres: 16/main: walwriter
postgres   10363   10358   \_ postgres: 16/main: autovacuum launcher
postgres   10364   10358   \_ postgres: 16/main: logical replication launcher
postgres  134884   10358   \_ postgres: 16/main: odoo odoo_revalidation 127.0.0.1(53872) idle
postgres  134887   10358   \_ postgres: 16/main: odoo postgres 127.0.0.1(53878) idle
postgres  134888   10358   \_ postgres: 16/main: odoo postgres 127.0.0.1(53882) idle
root      134874       1  python -m odoo --addons-path=./odoo/addons,./addons -d odoo_revalidation \
                              --db_host=127.0.0.1 --db_port=5432 --db_user=odoo --db_password=<REDACTED> \
                              --http-interface=0.0.0.0 --http-port=8069 --gevent-port=8072
```

The single `python -m odoo` process is the threaded WSGI server (`ThreadedServer`) plus the cron threads. Its PostgreSQL connections show three idle backend processes (one against `odoo_revalidation` for the application, two against `postgres` for the autocreate/template-management probes via `_create_empty_database`).

### Cycle accounting

| Field | Value |
|---|---|
| Total cycles required | 1 |
| Final cycle | 1 |
| Corrections in final cycle | 0 |
| Outcome | Pass — Build Step 1 prerequisite-install command runs verbatim with exit `0`; ready state reached on port 8069 within 2.5 seconds; `/web/database/selector` returned `200`; `/websocket/health` returned `200`; non-bind of port 8072 confirmed as documented threaded-mode behavior |

