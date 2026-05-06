# Technical Specification

# 0. Agent Action Plan

## 0.1 Intent Clarification

### 0.1.1 Core Objective

Based on the provided requirements, the Blitzy platform understands that the objective is to produce a single, source-derived markdown reference at the repository root, named `BUILD_AND_RUN.md`, that documents how to build, run, configure, and supply secrets to the Odoo 19.0 server using **only** code-and-configuration evidence drawn from the repository, and to **prove** that reference correct by executing it on a clean container/VM until the application reaches a verified ready state.

The deliverable consolidates five tightly coupled artifacts into one file:

- An OS-prerequisites and runtime-version manifest derived from `setup.py`, `setup.cfg`, `requirements.txt`, `odoo/release.py`, `setup/debinstall.sh`, `debian/odoo.conf`, `setup/package.py`, and the platform comments inside `requirements.txt`.
- An exact build-command sequence derived from `setup.py` (`scripts=['setup/odoo']`, `install_requires`, `python_requires`), `setup/debinstall.sh` (apt extraction logic), and `setup/package.py` (Docker-based packaging templates).
- An exact run-command sequence derived from `odoo/__main__.py` (delegates to `odoo.cli.command.main`), `odoo/cli/command.py` (default command resolution to `server`), `odoo/cli/server.py` (`main()` lifecycle), and `setup/odoo-wsgi.example.py` (WSGI deployment template).
- An exhaustive environment-variable table built by scanning `odoo/tools/config.py` `_OdooOption` `env_name` fields, `odoo/cli/server.py` `os.environ.get(...)` calls, `setup/package.py` GPG environment access, and shell `$VAR` references in `setup/debinstall.sh`.
- A strictly separated secrets table classifying any environment variable, file, or configuration value whose name matches the secret-classification regex (`password`, `secret`, `key`, `token`, `credential`, `apikey`, `auth`, `private`, `cert`) or whose use-site is the value-side of a database/SMTP/API authentication call.

The reference must be self-contained. A reader given only `BUILD_AND_RUN.md` and the repository must be able to provision a host, install dependencies, configure the database, start the server, and reach a documented HTTP ready state with zero recourse to README, CONTRIBUTING, INSTALL, `docs/`, or `*.rst` files.

The deliverable also must include a `## Validation Evidence` section embedded in `BUILD_AND_RUN.md` that records the OS image used, the full command transcript with timestamps, the ready-state HTTP status and latency, the process tree at ready state, and the count of correction cycles required, demonstrating that the documented build and run instructions were executed end-to-end on a clean environment and converged in a final cycle that required zero corrections.

### 0.1.2 Implicit Requirements Surfaced

Beyond the four explicit critical directives in the user prompt, the Blitzy platform identifies the following implicit requirements that follow necessarily from the directives and from the source code:

- The deliverable must reconcile multi-platform conditional dependencies. `requirements.txt` pins distinct versions per Python interpreter (`python_version == '3.10'`, `'3.11'`, `'3.12'`, `'3.13'`) and per platform (`sys_platform != 'win32'`, `sys_platform == 'win32'`); the build instruction must select **one** Python version (the highest explicitly documented per the Setup protocol — Python 3.13, derived from `MAX_PY_VERSION = (3, 13)` in `odoo/release.py`) and freeze the corresponding subset of pinned versions, not reproduce all branches.
- The deliverable must cite the **constraint** that Python 3.13 is the highest documented but not necessarily the recommended version, because `odoo/cli/server.py` `report_configuration` emits a warning when `sys.version_info[:2] > odoo.release.MAX_PY_VERSION`, indicating MAX_PY_VERSION is the upper supported boundary, not strictly above. Document Python 3.13 as the chosen target.
- The deliverable must distinguish OS-level prerequisites that are required for **building Python wheels** from prerequisites required at **runtime**. Python packages such as `psycopg2`, `lxml`, `Pillow`, `python-magic`, and `python-ldap` are C-extension wheels with system header dependencies (`libpq-dev`, `libxml2-dev`, `libxslt1-dev`, `libjpeg-dev`, `libpng-dev`, `libldap2-dev`, `libsasl2-dev`); these dependencies are derivable from the package names listed in `requirements.txt` plus the Debian package transcript pattern in `setup/debinstall.sh` (which depends on a `debian/control` file not present in this repository copy and therefore must be compensated via direct apt-package enumeration).
- The deliverable must document that the canonical CLI entry point is `python -m odoo` (per `odoo/__main__.py:L1-L3`) which delegates to `odoo.cli.command.main()` (per `odoo/cli/command.py:L109-L139`), and that the default sub-command when no command is specified is `server` (per `odoo/cli/command.py:L127-L129`). The `setup.py` `scripts=['setup/odoo']` line declares an installable script, but that file is not present in the inspected repository copy; the executable entry point must therefore be documented as `python -m odoo` using `odoo/__main__.py`.
- The deliverable must document the database bootstrap behavior: `odoo/cli/server.py:L101-L113` `main()` iterates `config['db_name']` and calls `odoo.service.db._create_empty_database` for each, automatically creating any missing database (subject to `InsufficientPrivilege` and `DatabaseExists` handling). This is critical for the validation execution because it means a documented DB user with `CREATEDB` privilege can bootstrap the database on first run; without it, the run command will fail.
- The deliverable must document the master-password security finding: `odoo/tools/config.py:L207` declares `admin_passwd` with `my_default='admin'`, hardcoding the master DB-management password to `admin` unless explicitly overridden in the config file. This must appear in the Secrets table as a **flagged finding** per the secrets directive's "MUST be flagged as a security finding" rule.
- The deliverable must document the `db_user='postgres'` rejection: `odoo/cli/server.py:L37-L44` exits the process if the configured database user (or `PGUSER` env) equals `postgres`. This is a hard runtime constraint — the validation execution must not use the `postgres` superuser.
- The deliverable must document that auto-prefixed environment variables exist for every option indexed in `odoo/tools/config.py` per `_OdooOption.__init__:L105-L109` which generates `env_name = 'ODOO_' + self.dest.upper()` for every `file_loadable` option that does not have an explicit `env_name`. This dramatically expands the env-var table beyond explicitly named PG/ODOO variables.
- The deliverable must document the bind interface and ports: `--http-interface 0.0.0.0` (default), `--http-port 8069`, and `--gevent-port 8072` per `odoo/tools/config.py:L255-L260`. The validation HTTP GET probe targets `http://0.0.0.0:8069/` (or the documented bind), and the longpolling/gevent worker probe targets port 8072.
- The deliverable must enumerate the required server-wide modules `['base', 'web']` (`REQUIRED_SERVER_WIDE_MODULES` in `odoo/tools/config.py:L31`) and the default set `['base', 'rpc', 'web']` (`DEFAULT_SERVER_WIDE_MODULES` in `odoo/tools/config.py:L30`) because these modules are auto-loaded at startup and inform the module-install fixtures for the validation cycle.
- The validation cycle must use `--init base --stop-after-init` on first invocation to seed the database (because `_create_empty_database` only creates the empty DB; the `base` module must be installed before the application is functional), then re-run without `--stop-after-init` to enter steady state.

### 0.1.3 Task Categorization

| Dimension | Classification |
|-----------|----------------|
| Primary task type | Documentation (single source-derived reference) |
| Secondary aspects | Build/Deploy reverse-engineering, Configuration enumeration, Secrets audit, End-to-end validation execution |
| Scope classification | Cross-cutting change — reads from packaging, runtime, CLI, config, and packaging-tools subsystems but writes only one new file at the repository root |
| Output mode | Single new file (`BUILD_AND_RUN.md`); zero existing files modified |

### 0.1.4 Special Instructions and Constraints

The Blitzy platform records the following directives verbatim from the user prompt, each of which is non-negotiable and must shape every step of execution:

- **CRITICAL Directive 1 — Source restriction.** "Document build and run instructions derived solely from source code and configuration artifacts." PERMITTED inputs: `Dockerfile*`, `docker-compose*.yml`, `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements*.txt`, `MANIFEST.in`, `__manifest__.py`, `Makefile`, shell scripts (`*.sh`), CI configs (`.github/workflows/*`, `.gitlab-ci.yml`), `package.json`, `debian/` packaging, `odoo-bin`, entry-point Python modules. PROHIBITED inputs: `README*`, `CONTRIBUTING*`, `INSTALL*`, `docs/`, `*.rst`, wiki content, any human-authored prose documentation. Each instruction MUST cite the source file and line range it was derived from in the format `[source: path/to/file:L42-L58]`. Comments in the deliverable explain WHY, not WHAT.
- **CRITICAL Directive 2 — Environment variable enumeration.** "Enumerate every environment variable consumed by the application, derived from source code references only." Discovery method: scan all `.py`, `.sh`, `.yml`, `Dockerfile*`, and entry-point files for `os.environ`, `os.getenv`, `getenv`, `${VAR}`, shell `$VAR` references, and `config.get` calls that read from environment. Output format: markdown table with columns `Variable | Default | Required | Purpose | Source`. Variables MUST be grouped by functional domain (database, mail, workers, addons paths, logging, security). No variable may appear without a source citation. No purpose may be stated without code-derived evidence.
- **CRITICAL Directive 3 — Secrets enumeration.** "Enumerate every secret required for build or runtime, derived from source code references only." Classification rule: a value is a secret if (1) it is read from environment, file, or vault AND (2) its variable name or usage context contains any of: `password`, `secret`, `key`, `token`, `credential`, `apikey`, `auth`, `private`, `cert`, OR it is the value side of a database/SMTP/API authentication call. Secrets MUST be listed separately from non-secret environment variables. Output MUST flag any secret with a hardcoded default value as a security finding. No secret value may be reproduced in the output, even if hardcoded in source — cite location only.
- **CRITICAL Directive 4 — Execution validation.** "Execute the derived build and run instructions on a clean environment and reconcile any divergence before finalizing the deliverable." Execution sequence: (1) provision prerequisites exactly as documented, (2) execute build commands in documented order, (3) provision database per documented setup, (4) execute run command with minimum required environment variables and secrets set to valid test values, (5) verify the application reaches a ready state. Ready-state verification: HTTP GET against the documented bind address and port returns a response within 120 seconds of process start. The longpolling/worker process MUST also be reachable. Database connection MUST be established (verified via process logs or a successful login page render). Maximum 5 correction cycles before halting and reporting. Halt-and-report trigger: if the same step fails 3 consecutive times after correction attempts, OR if a required environment variable cannot be satisfied without consulting prohibited sources, halt and report the specific source ambiguity. Evidence requirements appended to `BUILD_AND_RUN.md` under a `## Validation Evidence` section: exact OS image and version used, full command transcript with timestamps, ready-state HTTP response status and latency, process tree at ready state, and the count of correction cycles required.
- **CRITICAL Directive 5 — Completeness gates.** "Validate output completeness against measurable thresholds before delivery." Coverage gate: zero environment variable references in scanned source files may be absent from the output table. Verify by re-scanning and diffing. Citation gate: 100% of build steps, run steps, environment variables, and secrets must have source file citations. Entries without citations fail validation. Source restriction gate: zero references to README, CONTRIBUTING, INSTALL, docs/, or *.rst content may appear in output or in derivation reasoning. Execution evidence gate: `## Validation Evidence` section MUST be present and MUST report a successful final cycle per the execution directive above. Deliverable: single markdown file `BUILD_AND_RUN.md` at repository root. No other files modified.

The Blitzy platform also notes the following methodological constraints that follow from the directives:

- No web search may be used to determine Odoo-specific configuration, command syntax, or behavior. Web searches are permissible only to confirm OS-package availability (apt repository contents, Debian/Ubuntu package metadata) and to confirm general toolchain semantics (e.g., what `apt-get install -y --no-install-recommends` does), never to look up Odoo documentation.
- Any deliverable claim that cannot be backed by `[source: path/to/file:L<start>-L<end>]` must be removed, not weakened.
- The `Validation Evidence` section must reflect a successful final cycle (zero corrections required in the final cycle); if convergence requires up to 5 correction cycles, only the **final** cycle's evidence is canonical, but the cycle count must be reported.

### 0.1.5 Technical Interpretation

These requirements translate to the following technical implementation strategy:

- To **establish the runtime baseline**, the Blitzy platform will derive the Python version from `odoo/release.py:L40` (`MAX_PY_VERSION = (3, 13)`) and `setup.py:L70` (`python_requires='>=' + ".".join(map(str, MIN_PY_VERSION))`), and cross-reference with `requirements.txt` Python markers to confirm Python 3.13 has a fully resolvable dependency set; the Blitzy platform will derive the PostgreSQL minimum from `odoo/release.py:L41` (`MIN_PG_VERSION = 13`) and select PostgreSQL 16 (the highest Noble-available major version per Ubuntu apt indexing) for the validation run.
- To **derive OS-level prerequisites**, the Blitzy platform will reverse-map each `requirements.txt` Python package to its required system development headers (e.g., `psycopg2` → `libpq-dev`, `lxml` → `libxml2-dev libxslt1-dev`, `Pillow` → `libjpeg-dev libpng-dev zlib1g-dev`, `python-ldap` → `libldap2-dev libsasl2-dev`, `libsass` → `g++`/build toolchain) using the package-import-name → system-package mapping derivable from compiler error patterns and from `setup/requirements-check.py:L62-L65`'s `SPECIAL = {'pytz': 'tz', 'libsass': 'libsass-python'}` mapping. The Blitzy platform will also document the `wkhtmltopdf` binary dependency derivable from `odoo.tools.pdf` module references and report rendering, and the GeoIP database file paths from `odoo/tools/config.py:L448-L451` (`/usr/share/GeoIP/GeoLite2-City.mmdb` and `/usr/share/GeoIP/GeoLite2-Country.mmdb`).
- To **derive build commands**, the Blitzy platform will document a four-step sequence: (1) install OS prerequisites via `apt-get install -y --no-install-recommends <packages>` modeled on `setup/debinstall.sh:L9` patterns; (2) create a Python 3.13 virtual environment; (3) install Python dependencies with `pip install -r requirements.txt`; (4) install the Odoo package itself with `pip install -e .` (editable install) leveraging `setup.py:L13-L77`. No `make`, `npm`, or `mvn` step exists because no `Makefile`, `package.json`, or Java build descriptor is present in the repository root.
- To **derive run commands**, the Blitzy platform will document `python -m odoo` (per `odoo/__main__.py:L1-L3`) with the minimum required flags: `--addons-path=./addons,./odoo/addons` (per `odoo/cli/server.py:L51-L56` reading `odoo.addons.__path__`), `-d <db_name>` (per `odoo/tools/config.py:L367-L368`), `--db_host`, `--db_port`, `--db_user`, `-i base` (initial install), `--without-demo=all` (for production-like ready state), `--http-interface 0.0.0.0`, `--http-port 8069`. The minimum-flag derivation respects environment-variable substitutability: if `PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD` are set in the environment, the corresponding CLI flags become optional per `odoo/tools/config.py:L612-L618` `_load_env_options`.
- To **enumerate environment variables**, the Blitzy platform will produce a table grouped into six functional domains: **Database** (PG* + ODOO_DB_*), **HTTP/Web** (ODOO_HTTP_*, ODOO_PROXY_MODE), **Mail/SMTP** (ODOO_SMTP_*, ODOO_EMAIL_FROM), **Workers/Process** (ODOO_WORKERS, ODOO_LIMIT_*, ODOO_PIDFILE), **Addons/Paths** (ODOO_ADDONS_PATH, ODOO_DATA_DIR, ODOO_UPGRADE_PATH, ODOO_RC), **Logging/Security** (ODOO_LOGFILE, ODOO_LOG_LEVEL, ODOO_LOG_HANDLER, ODOO_LIST_DB, ODOO_DEV). The variable list is derived programmatically from `odoo/tools/config.py:L207-L494` parser definitions plus the `_OdooOption.__init__:L105-L109` auto-prefix rule, supplemented by explicit `os.environ.get(...)` lookups in `odoo/cli/server.py:L42`, `:L61-L63`, `setup/package.py` GPG access, and shell `$DEBIAN_FRONTEND` in `setup/debinstall.sh:L27`.
- To **enumerate secrets**, the Blitzy platform will isolate variables matching the classification rule: `db_password`/`PGPASSWORD` (`odoo/tools/config.py:L371-L372`), `admin_passwd` (`odoo/tools/config.py:L207` — flagged as security finding due to hardcoded default `'admin'`), `smtp_password` (`odoo/tools/config.py:L357-L358`), `proxy_access_token` (`odoo/tools/config.py:L214`), `smtp_ssl_certificate_filename` and `smtp_ssl_private_key_filename` (`odoo/tools/config.py:L359-L362` — secrets-as-files), and the `GPGPASSPHRASE` build-time secret (`setup/package.py` summary; only relevant for packaging, not runtime). No secret value will be reproduced in the deliverable; only `[source:...]` citations.
- To **execute and validate**, the Blitzy platform will provision a clean Ubuntu 24.04 (Noble) container, install Python 3.13 from the deadsnakes PPA, install PostgreSQL 16 from the Ubuntu archive, create an unprivileged `odoo` PostgreSQL role with `CREATEDB`, run the documented build sequence, run `python -m odoo -d odoo_test -i base --stop-after-init --without-demo=all` to seed, then run `python -m odoo -d odoo_test --http-interface 0.0.0.0 --http-port 8069` and probe `http://localhost:8069/web/database/selector` (a no-DB endpoint that always responds when HTTP is up) and `http://localhost:8072/longpolling/poll` (gevent worker probe). Ready state is achieved when both endpoints return within 120 seconds. The transcript, OS image, latency, and process tree are appended to `BUILD_AND_RUN.md` under `## Validation Evidence`.
- To **enforce completeness gates**, the Blitzy platform will, after the run, re-scan the repository with `grep -rn "os\\.environ\\|os\\.getenv\\|getenv\\|env_name=" --include="*.py"` and `grep -rn '\\$[A-Z_][A-Z0-9_]*' --include="*.sh"` against the Variable column of the env-vars table; any unmatched reference fails the coverage gate and is added before re-validation.


## 0.2 Repository Scope Discovery

### 0.2.1 Comprehensive File Analysis

The Blitzy platform conducted an exhaustive scan of the repository to identify every artifact relevant to deriving build, run, environment, and secret instructions. The scan obeys the user's PERMITTED/PROHIBITED source list. Files are organized below by their role in the derivation pipeline.

#### 0.2.1.1 Permitted Source Files Identified (in scope as derivation inputs)

The following files are confirmed present in the repository and are the sole inputs from which the deliverable is derived:

**Packaging and dependency manifests:**

- `setup.py` — Python package descriptor; declares `install_requires` (40 packages), `python_requires=">=" + MIN_PY_VERSION` (sourced from `odoo/release.py`), `extras_require={'ldap': ['python-ldap']}`, `tests_require=['freezegun']`, and `scripts=['setup/odoo']`. This file is the canonical Python package contract. [source: setup.py:L1-L77]
- `setup.cfg` — setuptools install option `optimize=1`; flake8 plugin configuration with `extend-exclude=.git,.tx,debian,doc,setup` and RST role/directive whitelists. Provides packaging-time hints, no runtime impact. [source: setup.cfg:L1-L35]
- `requirements.txt` — Pinned Python dependencies with conditional markers spanning Python 3.10 → 3.13 and `sys_platform != 'win32'` / `== 'win32'`; comments cite "Ubuntu 24.04" (Noble) and "Debian 12" (Bookworm) as the canonical OS targets, and individual entries reference Jammy (22.04), Bookworm (12), Noble (24.04), and Trixie (Debian 13). [source: requirements.txt:L1-L99]

**Runtime entry points and CLI:**

- `odoo/__main__.py` — Module-level entry point `python -m odoo`; imports and calls `odoo.cli.command.main()`. [source: odoo/__main__.py:L1-L3]
- `odoo/cli/command.py` — CLI dispatch. `main()` parses `argv[1:]`, optionally consumes a leading `--addons-path=` token, defaults to the `server` command when none specified, and invokes `command().run(args)`. Defines `commands` registry, `find_command()`, `load_internal_commands()`, `load_addons_commands()`. [source: odoo/cli/command.py:L1-L139]
- `odoo/cli/server.py` — `Server` class (default command) with `main()` lifecycle: `check_root_user()`, `config.parse_config(args, setup_logging=True)`, `check_postgres_user()`, `report_configuration()`, optional auto-creation of databases per `config['db_name']`, `setup_pid_file()`, and `server.start(preload=config['db_name'], stop=config["stop_after_init"])`. [source: odoo/cli/server.py:L1-L128]
- `odoo/cli/__init__.py` and the other 14 sibling CLI command modules — Define alternate sub-commands (`db`, `deploy`, `i18n`, `module`, `populate`, `scaffold`, `shell`, `start`, `cloc`, `obfuscate`, `populate`, `neutralize`, `upgrade_code`, `help`). [source: odoo/cli/]
- `odoo/release.py` — Version metadata and runtime bounds: `version_info = (19, 0, 0, FINAL, 0, '')`, `MIN_PY_VERSION = (3, 10)`, `MAX_PY_VERSION = (3, 13)`, `MIN_PG_VERSION = 13`, `nt_service_name = 'odoo-server-19.0'`. [source: odoo/release.py:L1-L42]

**Configuration parser (single source of truth for env vars and CLI flags):**

- `odoo/tools/config.py` — `configmanager`/`_OdooOption` class hierarchy. Defines every configuration option Odoo recognizes via `parser.add_option(...)` calls within `_build_cli()`; each `_OdooOption` records `dest`, `my_default`, `env_name`, `cli_loadable`, `file_loadable`, and `file_exportable` flags. Crucially, `_OdooOption.__init__:L105-L109` auto-generates `env_name = 'ODOO_' + self.dest.upper()` for every option that does not have an explicit `env_name` set, so the env-var inventory is derived programmatically from this file. [source: odoo/tools/config.py:L40-L494]

**WSGI deployment template:**

- `setup/odoo-wsgi.example.py` — Sample WSGI module for `gunicorn` and `uwsgi` deployments. Documents `bind = '127.0.0.1:8069'`, `workers = 4`, `timeout = 240`, `max_requests = 2000` Gunicorn globals, and shows `from odoo.http import root as application`. [source: setup/odoo-wsgi.example.py:L1-L48]

**Debian/apt provisioning script and packaged config:**

- `setup/debinstall.sh` — Shell script that extracts the Depends: stanza from `debian/control`, deduplicates package names, and runs `DEBIAN_FRONTEND=noninteractive xargs apt-get install -y --no-install-recommends`. Implements quiet mode (`-q`/`--quiet`) and dry-run list mode (`-l`/`--list`). [source: setup/debinstall.sh:L1-L28]
- `debian/odoo.conf` — Debian-packaged INI config template. Sets `db_host=False`, `db_port=False`, `db_user=odoo`, `db_password=False`, `default_productivity_apps=True`. Contains commented `admin_passwd = admin` and `addons_path = /usr/lib/python3/dist-packages/odoo/addons` examples. [source: debian/odoo.conf:L1-L9]

**Packaging orchestrator (build-time only):**

- `setup/package.py` — Docker-based packaging script that reads `GPGPASSPHRASE`/`GPGID` env vars, dispatches to `DockerTgz`, `DockerDeb`, `DockerRpm`, `DockerWine`, `DockerIot` builders. Relevant only for distribution-package construction, not for the run-cycle derivation. [source: setup/package.py]
- `setup/requirements-check.py` — Cross-distro requirements validator; cross-checks `requirements.txt` pins against Debian/Ubuntu archives and PyPI wheels; defines `SUPPORTED_FORMATS` and `PLATFORM_CODES = ('linux', 'win32', 'darwin')`. [source: setup/requirements-check.py:L1-L80]

**HTTP/WSGI runtime:**

- `odoo/http.py` — Defines `Application` (WSGI callable bound to `root`) used by both the standalone server and the WSGI deployment template. References `config['proxy_mode']`, `config['x_sendfile']`, `config['session_dir']`, `config['geoip_city_db']`, `config['geoip_country_db']`, `config['dbfilter']`, `config['db_name']`, `config['dev_mode']`. [source: odoo/http.py]
- `odoo/service/server.py` — Process orchestration: `CommonServer`, `ThreadedServer`, `GeventServer`, `PreforkServer`, `Worker`, `WorkerHTTP`, `WorkerCron`. Implements signal-driven lifecycle, `set_limit_memory_hard` via RLIMIT_AS, optional `setproctitle`, optional `inotify`/`watchdog` source-watching, `psutil` memory polling. [source: odoo/service/server.py:L1-L100]

**Database connection layer:**

- `odoo/sql_db.py` — `connection_info_for`, `db_connect`, `ConnectionPool`, `Cursor` classes. Reads `config['db_host']`, `config['db_port']`, `config['db_user']`, `config['db_password']`, `config['db_sslmode']`, `config['db_app_name']`, `config['db_maxconn']`, `config['db_replica_host']`, `config['db_replica_port']`. [source: odoo/sql_db.py]

**Module loading and dependency graph:**

- `odoo/modules/__init__.py`, `odoo/modules/db.py`, `odoo/modules/loading.py`, `odoo/modules/module.py`, `odoo/modules/module_graph.py` — Define module discovery, manifest parsing (`__manifest__.py`), dependency graph computation, and the `base` module bootstrap that installs `odoo/addons/base/data/base_data.sql` on a fresh database. The `base` module's existence and bootstrap behavior are essential to documenting first-run install (`-i base`). [source: odoo/modules/]

**Add-ons inventory (300+ modules):**

- `addons/` — Each module exposes a `__manifest__.py` declaring `name`, `version`, `depends`, `data`, `assets`, `installable`. Module install order, `auto_install` semantics, and demo-data toggles are inferred from manifest keys but are **not** required for the build/run reference except in the addons-path documentation. The reference will document `--addons-path=./addons,./odoo/addons` (the two canonical addon roots in the repo). [source: addons/]

#### 0.2.1.2 Permitted Source Files Listed by User but ABSENT in This Repository

The user's PERMITTED list mentions several artifacts that are **not present** in this repository copy. The Blitzy platform records these absences explicitly because their absence shapes the derivation:

| Artifact | Status | Implication for Derivation |
|----------|--------|----------------------------|
| `Dockerfile*` at root | Absent | No containerized build is documented at root; the validation cycle uses a host (or container) provisioned manually rather than via a repository-supplied Dockerfile |
| `docker-compose*.yml` | Absent | No multi-container orchestration is supplied; the validation cycle provisions PostgreSQL alongside Odoo manually |
| `pyproject.toml` | Absent | Python build is governed by `setup.py` only; PEP 517 build metadata is not present |
| `Makefile` | Absent | No make-target build automation; build is direct `pip install` |
| `package.json` | Absent at root | No Node.js root build; per-addon JS is bundled via Odoo's asset pipeline at server startup, not via npm |
| `.github/workflows/*.yml` | Absent | No GitHub Actions CI; the `.github` directory contains only `PULL_REQUEST_TEMPLATE.md` and `ISSUE_TEMPLATE/`. The Blitzy platform must **not** infer build/run instructions from CI files because none exist |
| `.gitlab-ci.yml` | Absent | No GitLab CI pipeline; same reasoning as above |
| `MANIFEST.in` | Absent at root | Package data inclusion governed by `setup.py:L26` `include_package_data=True` and `setup.cfg`'s flake8-only `[flake8]` section |
| `odoo-bin` (root-level executable) | Absent | The runnable entry point is `python -m odoo` via `odoo/__main__.py:L1-L3`; the `setup.py:L23` `scripts=['setup/odoo']` declaration references a `setup/odoo` script that is also not present in the inspected `setup/` directory listing (only `debinstall.sh`, `odoo-wsgi.example.py`, `package.py`, `requirements-check.py`, and `win32/` are listed). The reference must therefore document `python -m odoo` as the canonical entry point |
| `debian/control` | Absent | `setup/debinstall.sh:L23` resolves `../debian/control` and extracts `Depends:` packages from it, but only `debian/odoo.conf` is present. The OS-prerequisite list cannot be auto-generated from `debian/control`; the Blitzy platform must derive OS prerequisites by reverse-mapping each Python package in `requirements.txt` to its system header dependencies |

#### 0.2.1.3 PROHIBITED Source Files (must not be read or referenced)

The following files exist in the repository and **must not** be read, summarized, paraphrased, or cited in any form during derivation or in the deliverable. The Blitzy platform records their existence solely so it can be enforced that no derivation step opens them:

- `README.md` — PROHIBITED (human-authored prose)
- `CONTRIBUTING.md` — PROHIBITED (human-authored prose)
- `SECURITY.md` — PROHIBITED (security policy document, human-authored prose)
- `LICENSE` — Permitted to read for licensing display only, but no build/run derivation is taken from it
- `doc/` and any `*.rst` file — PROHIBITED
- `.weblate.json` — Permitted (machine-readable translation mapping); not required for build/run derivation

The Blitzy platform commits to enforcing these exclusions throughout the deliverable construction.

### 0.2.2 Web Search Research Conducted

Per the user's CRITICAL Directive 1, web search must not be used to look up Odoo-specific configuration, command syntax, or behavior; the deliverable's content is derived solely from the source. However, the following narrow web-search uses are permissible because they confirm OS-toolchain semantics that are not Odoo-specific:

- **Web search 1** — Confirm Ubuntu 24.04 Noble's Python and PostgreSQL package availability (deadsnakes PPA for Python 3.13; `postgresql-16` as the default-archive PostgreSQL major version). This information is required to materialize the OS-prerequisites list when no `Dockerfile` or CI config dictates the OS image.
- **Web search 2** — Confirm `apt-get install -y --no-install-recommends` semantics and `DEBIAN_FRONTEND=noninteractive` semantics, both of which are referenced in `setup/debinstall.sh:L9,L27` but not defined there. (The setup file uses these flags, so their semantic interpretation is referenced from apt's standard behavior.)
- **Web search 3** — Confirm the system-package names that satisfy each Python C-extension's build-time headers (e.g., `libpq-dev` for `psycopg2`, `libxml2-dev libxslt1-dev` for `lxml`, `libldap2-dev libsasl2-dev` for `python-ldap`, `libjpeg-dev zlib1g-dev` for `Pillow`). This mapping is **not** Odoo-specific and is used only to translate `requirements.txt` Python package names to the apt packages that supply their header files.

No other web searches are required. No web search will be performed against Odoo's website, Odoo wiki, Odoo forums, or any documentation site.

### 0.2.3 Existing Infrastructure Assessment

The repository's build-and-run posture, as evidenced by the inspected files, is summarized below. This summary informs what the deliverable must document and what fixtures the validation cycle must provision.

| Aspect | Evidence | Implication |
|--------|----------|-------------|
| Project structure | Root contains `setup.py`, `setup.cfg`, `requirements.txt`, `addons/` (300+), `odoo/` (core package), `setup/` (build/packaging), `debian/odoo.conf`, `.github/` (templates only) | Standard Python package layout; build is `pip install -r requirements.txt && pip install -e .` |
| Python version policy | `odoo/release.py:L39-L40` declares `MIN_PY_VERSION = (3, 10)` and `MAX_PY_VERSION = (3, 13)`; `requirements.txt` has explicit pins for `python_version == '3.10'`, `'3.11'`, `'3.12'`, `'3.13'` | Documented Python target = 3.13 (highest documented per Setup protocol) |
| PostgreSQL version policy | `odoo/release.py:L41` declares `MIN_PG_VERSION = 13`; no max declared | Documented PostgreSQL target ≥ 13; validation will use PostgreSQL 16 (Ubuntu Noble default-archive) |
| Default config file location | `odoo/tools/config.py:L513-L521`: Windows uses `<argv[0]_dir>/odoo.conf`, POSIX uses `~/.odoorc` (or legacy `~/.openerp_serverrc`) | Validation will set `ODOO_RC=/etc/odoo/odoo.conf` or `--config <path>` explicitly |
| Default data directory | `odoo/tools/config.py:L505-L511`: `appdirs.user_data_dir('Odoo','OpenERP S.A.')` if home dir exists, `appdirs.site_data_dir(...)` on win32/darwin, `/var/lib/Odoo` otherwise | Documented; configurable via `--data-dir` or `ODOO_DATA_DIR` |
| Default HTTP bind | `odoo/tools/config.py:L255-L256` defaults `--http-interface` to `'0.0.0.0'` | Documented; ready-state probe targets `http://0.0.0.0:8069` |
| Default HTTP ports | `odoo/tools/config.py:L257-L260` defaults `--http-port=8069`, `--gevent-port=8072` | Documented; both ports probed during validation |
| Build/Deploy automation present | None at repository root: no Makefile, no Dockerfile, no `.github/workflows/*`, no `package.json`, no `pyproject.toml` | Build instructions must be derived from `setup.py`/`requirements.txt`/`setup/` directly, not from CI YAML |
| Testing infrastructure | `odoo/tools/config.py:L280-L313` exposes `--test-enable`, `--test-tags`, `--test-file`, `--screenshots`, `--screencasts`. `odoo/tests/` provides the harness | Optional; not required for ready-state validation |
| WSGI deployment template | `setup/odoo-wsgi.example.py:L13-L48` shows Gunicorn config | Documented as alternative to `python -m odoo` for production WSGI deployments |


## 0.3 Scope Boundaries

### 0.3.1 Exhaustively In Scope

The Blitzy platform's work for this task is scoped to:

**Single new file creation:**

- `BUILD_AND_RUN.md` — created at the repository root. This is the only file the Blitzy platform will write to the repository for this task.

**Sources read for derivation (read-only inputs):**

- Packaging/dependency manifests:
    - `setup.py`
    - `setup.cfg`
    - `requirements.txt`
- Runtime entry points and CLI sources:
    - `odoo/__main__.py`
    - `odoo/cli/__init__.py`
    - `odoo/cli/command.py`
    - `odoo/cli/server.py`
    - `odoo/cli/db.py` (db CLI sub-command, used for create/restore semantics in env-var derivation)
    - `odoo/cli/deploy.py` (HTTP deploy CLI; documents login/upload endpoints)
    - `odoo/cli/start.py` (auto-discovery convenience wrapper; documents addons-path defaults)
    - `odoo/cli/shell.py`
    - `odoo/cli/scaffold.py`
- Runtime configuration source of truth:
    - `odoo/tools/config.py` (entire file, focus on `_OdooOption`, `configmanager._build_cli`, `_load_default_options`, `_load_env_options`)
- Release/version manifest:
    - `odoo/release.py`
- Process orchestration and HTTP layer:
    - `odoo/service/server.py`
    - `odoo/http.py`
- Database connectivity:
    - `odoo/sql_db.py`
    - `odoo/service/db.py`
- Module loading bootstrap:
    - `odoo/modules/__init__.py`
    - `odoo/modules/db.py`
    - `odoo/modules/loading.py`
    - `odoo/modules/module.py`
- Logging configuration:
    - `odoo/netsvc.py`
    - `odoo/loglevels.py`
- Cross-platform path resolution:
    - `odoo/tools/appdirs.py`
- Debian/apt provisioning and packaged config:
    - `setup/debinstall.sh`
    - `setup/odoo-wsgi.example.py`
    - `setup/package.py` (only for build-time secrets enumeration)
    - `setup/requirements-check.py` (only for system-package mapping cues)
    - `debian/odoo.conf`
- All `addons/*/__manifest__.py` files for addons-path documentation (manifest contents are the only addon files read for this task; addon source code is out of scope)

**Source code scanning for environment variable references (read-only globs):**

- `odoo/**/*.py` — every Python file in the core `odoo/` package, scanned for `os.environ`, `os.getenv`, `os.environ.get`, and `getenv` references
- `setup/**/*.py` — every Python file under `setup/`
- `setup/**/*.sh` — every shell script under `setup/`, scanned for `${VAR}` and `$VAR` references
- `*.sh` at root — none present, but the glob is run for completeness
- All entry-point Python modules (`odoo/__main__.py`, `odoo/cli/*.py`)

**Source code scanning for secret references (subset of env-var scan):**

- The same scanning glob as env-vars, filtered through the secret-classification regex defined in CRITICAL Directive 3
- `odoo/tools/config.py:L207` `admin_passwd` declaration — flagged as security finding
- `odoo/tools/config.py:L357-L362` `smtp_password`, `smtp_ssl_certificate_filename`, `smtp_ssl_private_key_filename`
- `odoo/tools/config.py:L371-L372` `db_password` and `PGPASSWORD` env mapping
- `odoo/tools/config.py:L214` `proxy_access_token`
- `setup/package.py` `GPGPASSPHRASE`, `GPGID` references

**Validation execution scope:**

- Provision a clean Ubuntu 24.04 (Noble) container/VM (matches `requirements.txt` Noble pin annotations)
- Install Python 3.13 from the deadsnakes PPA (matches `MAX_PY_VERSION`)
- Install PostgreSQL 16 from the Ubuntu archive (satisfies `MIN_PG_VERSION = 13`)
- Install OS-level prerequisites derived from `requirements.txt` package names (libpq-dev, libxml2-dev, libxslt1-dev, libjpeg-dev, libpng-dev, zlib1g-dev, libldap2-dev, libsasl2-dev, libsasl2-modules, libffi-dev, build-essential, node-less, fonts-noto-cjk, wkhtmltopdf if available in archive)
- Create a Python 3.13 virtualenv
- `pip install -r requirements.txt`
- `pip install -e .`
- Initialize an empty PostgreSQL role `odoo` with `CREATEDB` privilege; do **not** use `postgres` role (per `odoo/cli/server.py:L42-L44`)
- Run `python -m odoo -d odoo_test -i base --without-demo=all --stop-after-init` for first-run database seeding
- Run `python -m odoo -d odoo_test --http-interface 0.0.0.0 --http-port 8069 --gevent-port 8072`
- Probe `http://localhost:8069/web/database/selector` and the longpolling/websocket endpoint within 120 seconds
- Append the validation transcript, OS image, ready-state status, latency, and process tree to `BUILD_AND_RUN.md` under the `## Validation Evidence` heading
- Up to 5 correction cycles permitted; halt-and-report after 3 consecutive identical failures or unsatisfiable env-var gap

### 0.3.2 Explicitly Out of Scope

The following items are explicitly **not** in scope for this task and the Blitzy platform must not undertake them:

**Files NOT to be created or modified:**

- Any file other than `BUILD_AND_RUN.md` at the repository root. The user's CRITICAL Directive 5 final clause states "single markdown file `BUILD_AND_RUN.md` at repository root. No other files modified." This is enforced absolutely.
- No README.md updates, no CONTRIBUTING.md updates, no SECURITY.md updates.
- No new Dockerfile, no docker-compose.yml, no Makefile, no .github/workflows/*.yml, no .gitlab-ci.yml — even though the absence of these files was noted as a gap, **creating them is out of scope** because the user's deliverable is documentation, not new build infrastructure.
- No edits to `setup.py`, `setup.cfg`, `requirements.txt`, `debian/odoo.conf`, or any source file under `odoo/`, `addons/`, or `setup/`.
- No new test files, no new sample configuration files, no new shell scripts.

**Sources NOT to be read (PROHIBITED inputs):**

- `README.md`
- `CONTRIBUTING.md`
- `SECURITY.md`
- Any file under `doc/`
- Any `*.rst` file anywhere in the repository
- Any wiki, blog, forum, or web-hosted prose documentation about Odoo, including `odoo.com/documentation`, `odoo.com/forum`, `runbot.odoo.com`, GitHub wiki pages, and StackOverflow answers
- The `LICENSE` file (read only for confirming licensing display, never as a build/run derivation source)

**Behaviors NOT to be undertaken:**

- No "best-effort" guesses about Odoo behavior. Every claim in `BUILD_AND_RUN.md` must trace to a `[source: path/to/file:L<start>-L<end>]` citation. Items that cannot be sourced must be **omitted**, not weakened or hedged.
- No reproduction of secret values. Even when a hardcoded default appears in source (e.g., `admin_passwd = 'admin'` in `odoo/tools/config.py:L207`), only the citation is recorded; the literal value is **not** reproduced in the deliverable.
- No exhaustive enumeration of all 300+ addon-specific environment variables. Per the env-var directive, only environment variables actually referenced in source code are listed. Most addons rely on `ir.config_parameter` (database-stored) configuration, not OS environment variables; those are **out of scope** for the env-var table because they are not `os.environ` references.
- No documentation of database-stored configuration parameters (`ir.config_parameter` rows). These are runtime-set values, not build/run-time inputs.
- No documentation of front-end JavaScript build steps. Although addons under `addons/*/static/src/` contain JS, SCSS, and OWL components, Odoo's asset pipeline transpiles and bundles these at server startup (`odoo.tools.js_transpiler`), so there is no separate build step to document.
- No documentation of localization installation. The 100+ `l10n_*` modules are optional installs and not required for ready-state validation. Only `base` (and the auto-loaded server-wide modules `web`, `rpc` per `odoo/tools/config.py:L30-L31`) are required.
- No performance tuning beyond what is required for ready-state achievement. The reference documents the **default** values for `--workers`, `--max-cron-threads`, `--limit-memory-soft`, `--limit-memory-hard`, `--limit-time-cpu`, `--limit-time-real` (all from `odoo/tools/config.py:L457-L493`) but does **not** prescribe production-tuned values.
- No security hardening beyond the security findings derived from source. The reference flags `admin_passwd` default, the `db_user='postgres'` rejection, the `--no-database-list` security flag, and `--proxy-mode` semantics, but does not prescribe specific production hardening recipes.
- No Windows-specific or macOS-specific build instructions. Although `odoo/tools/appdirs.py` and `requirements.txt` contain platform-conditional logic, the user's validation environment is described as a "clean container or VM" which is implicitly Linux. The reference documents Linux (Debian/Ubuntu) only; Windows and macOS branches are out of scope for the validation but their existence in source is acknowledged in the env-var table where relevant (e.g., `pypiwin32` Windows-only entry).
- No Docker-image build for the validation. Although `setup/package.py` defines Docker builders for distribution packaging, the user's validation explicitly says "clean container or VM" which the Blitzy platform interprets as a stock Ubuntu/Debian image, not a repository-built Docker image. Repository-built Docker images are out of scope.
- No publication of the deliverable to any external system. The deliverable is a file in the repository tree; the Blitzy platform does not push to package indexes, container registries, documentation sites, or any other external destination.


## 0.4 Dependency Inventory

### 0.4.1 Runtime Toolchain

The Blitzy platform identifies the highest explicitly documented supported version for each runtime, per the Setup protocol's "Logic for highest explicitly documented version" rule. Where a range is specified, the upper bound is selected.

| Runtime | Version | Source Citation | Selection Logic |
|---------|---------|-----------------|-----------------|
| Python | 3.13 | `odoo/release.py:L40` (`MAX_PY_VERSION = (3, 13)`); `odoo/release.py:L39` (`MIN_PY_VERSION = (3, 10)`); `setup.py:L70` (`python_requires='>=' + MIN_PY_VERSION`); `requirements.txt:L1-L99` (explicit `python_version` markers for `'3.10'`, `'3.11'`, `'3.12'`, `'3.13'`) | Upper-bound `MAX_PY_VERSION` selects 3.13; corroborated by per-package pins targeting Python 3.13 (e.g., `Babel==2.17.0 ; python_version >= '3.13'`, `Pillow==11.1.0 ; python_version >= '3.13'`, `psycopg2==2.9.10 ; python_version >= '3.13'`) |
| PostgreSQL | 16 (validation); ≥ 13 (minimum) | `odoo/release.py:L41` (`MIN_PG_VERSION = 13`) | Lower-bound 13 specified; no upper bound declared. Validation uses PostgreSQL 16 (default in Ubuntu 24.04 Noble apt archive); MIN_PG_VERSION=13 is the documented minimum |
| Operating System | Ubuntu 24.04 LTS (Noble) for validation; Debian 12 (Bookworm) and Ubuntu 24.04 (Noble) are canonical targets | `requirements.txt:L1-L2` ("officially supported versions of the following packages are their python3-* equivalent distributed in Ubuntu 24.04 and Debian 12"); per-line markers reference Jammy (22.04), Bookworm (12), Noble (24.04), Trixie (Debian 13) | Comments in `requirements.txt` are pseudo-machine-readable (they pin specific package versions per OS); validation selects Noble (24.04) as the highest stable Ubuntu LTS that is explicitly named |

### 0.4.2 Key Public Python Packages

The following table lists every Python package declared in `requirements.txt`, with the version that resolves under Python 3.13 (the selected runtime). Versions are taken verbatim from `requirements.txt`; markers that exclude Python 3.13 result in "N/A" entries that are not installed on this runtime.

| Registry | Package Name | Version (Python 3.13) | Source Citation | Purpose |
|----------|--------------|------------------------|-----------------|---------|
| pip | asn1crypto | 1.5.1 | `requirements.txt:L4` | ASN.1 cryptography parsing for X.509, PKCS, EDI signing |
| pip | Babel | 2.17.0 | `requirements.txt:L7` | Locale, date/number formatting, gettext catalogs |
| pip | cbor2 | 5.6.2 | `requirements.txt:L9` | CBOR (RFC 7049) serialization for WebAuthn/passkey support |
| pip | chardet | 5.2.0 | `requirements.txt:L11` | Character-encoding detection for imports |
| pip | cryptography | 42.0.8 | `requirements.txt:L13` | Primitive cryptography (TLS, signing, encryption) |
| pip | docutils | 0.20.1 | `requirements.txt:L15` | reStructuredText parsing (used by ORM docstrings, NOT user-facing docs) |
| pip | freezegun | 1.5.1 | `requirements.txt:L18` | Test-time mocking (test-only) |
| pip | geoip2 | 2.9.0 | `requirements.txt:L19` | MaxMind GeoIP2 database reader |
| pip | gevent | 24.11.1 | `requirements.txt:L23` | Cooperative-multithreading runtime for the longpolling worker |
| pip | greenlet | 3.1.1 | `requirements.txt:L27` | Coroutine primitive for gevent |
| pip | idna | 3.6 | `requirements.txt:L29` | Internationalized domain name handling |
| pip | Jinja2 | 3.1.2 | `requirements.txt:L31` | Server-side template rendering |
| pip | libsass | 0.22.0 | `requirements.txt:L33` | SCSS → CSS compilation for asset pipeline |
| pip | lxml | 5.2.1 | `requirements.txt:L36` | XML/HTML parsing (views, QWeb, EDI) |
| pip | lxml-html-clean | unpinned | `requirements.txt:L37` | HTML sanitization (split from lxml in Noble) |
| pip | MarkupSafe | 2.1.5 | `requirements.txt:L40` | Safe-string primitives for Jinja2 |
| pip | num2words | 0.5.13 | `requirements.txt:L42` | Number-to-words for invoice amounts |
| pip | ofxparse | 0.21 | `requirements.txt:L43` | OFX bank statement parser |
| pip | openpyxl | 3.1.2 | `requirements.txt:L45` | XLSX reader/writer |
| pip | passlib | 1.7.4 | `requirements.txt:L46` | Password hashing (`pbkdf2_sha512`, used by `crypt_context` in `odoo/tools/config.py:L21-L23`) |
| pip | Pillow | 11.1.0 | `requirements.txt:L50` | Image processing (PIL fork) |
| pip | polib | 1.1.1 | `requirements.txt:L51` | gettext .po/.pot file handling |
| pip | psutil | 5.9.8 | `requirements.txt:L54` | Process and resource monitoring (worker memory limits) |
| pip | psycopg2 | 2.9.10 | `requirements.txt:L58` | PostgreSQL adapter (synchronous; required for `odoo/sql_db.py`) |
| pip | pyopenssl | 24.1.0 | `requirements.txt:L60` | OpenSSL bindings (TLS handshake helpers) |
| pip | PyPDF2 | 2.12.1 | `requirements.txt:L62` | PDF reading/writing (older API; replaced by pypdf in successors) |
| pip | pyserial | 3.5 | `requirements.txt:L64` | Serial port I/O (POS hardware integration) |
| pip | python-dateutil | 2.8.2 | `requirements.txt:L66` | Relative-date arithmetic |
| pip | python-magic | 0.4.27 | `requirements.txt:L68` | libmagic bindings for MIME detection |
| pip | python-ldap | 3.4.4 | `requirements.txt:L70` | LDAP bindings (used only when `auth_ldap` addon installed) |
| pip | python-stdnum | 1.19 | `requirements.txt:L72` | National ID and tax-ID validation |
| pip | pytz | unpinned | `requirements.txt:L73` | IANA timezone database |
| pip | pyusb | 1.2.1 | `requirements.txt:L74` | USB device I/O (POS hardware) |
| pip | qrcode | 7.4.2 | `requirements.txt:L76` | QR code generation |
| pip | reportlab | 4.1.0 | `requirements.txt:L79` | PDF generation engine |
| pip | requests | 2.31.0 | `requirements.txt:L81` | HTTP client (outbound integrations) |
| pip | rjsmin | 1.2.0 | `requirements.txt:L83` | JavaScript minifier for asset pipeline |
| pip | urllib3 | 2.0.7 | `requirements.txt:L86` | Lower-level HTTP transport |
| pip | vobject | 0.9.6.1 | `requirements.txt:L87` | iCalendar/vCard parsing |
| pip | Werkzeug | 3.0.1 | `requirements.txt:L90` | WSGI toolkit (request/response, routing) |
| pip | xlrd | 2.0.1 | `requirements.txt:L92` | Legacy XLS reader |
| pip | XlsxWriter | 3.1.9 | `requirements.txt:L94` | XLSX writer |
| pip | xlwt | 1.3.0 | `requirements.txt:L95` | Legacy XLS writer |
| pip | zeep | 4.3.1 | `requirements.txt:L98` | SOAP client (used by EDI integrations) |

The following packages declared in `setup.py:L27-L69` `install_requires` are **not** explicitly pinned in `requirements.txt` and thus take their latest-compatible version per pip resolver:

| Registry | Package Name | Source Citation | Notes |
|----------|--------------|-----------------|-------|
| pip | odoo | `setup.py:L14-L15` | The Odoo package itself, installed from the repository (`pip install -e .`) at version 19.0 derived from `odoo/release.py:L15-L17` |

### 0.4.3 OS-Level Prerequisites Derived from Python C-Extension Requirements

Because `debian/control` is not present in this repository, the OS-prerequisites list is derived by reverse-mapping each Python C-extension package in `requirements.txt` to its Debian/Ubuntu development headers. The mapping below is materialized from standard apt-package conventions (each package's well-known build-time header dependencies); web search confirms the apt-package names against the Ubuntu 24.04 archive.

| Apt Package | Required For | Source Citation |
|-------------|--------------|-----------------|
| `python3.13` | Python 3.13 interpreter | `odoo/release.py:L40` |
| `python3.13-venv` | Virtual environment creation | (toolchain) |
| `python3.13-dev` | Python C headers for building C-extension wheels | `requirements.txt` (any `psycopg2`, `lxml`, `Pillow`, `python-ldap`, `gevent`, `cryptography`, `libsass` source build) |
| `build-essential` | gcc, g++, make for C-extension compilation | `requirements.txt:L33` (`libsass==0.22.0`), `requirements.txt:L23` (`gevent`), and any wheel-not-available scenario |
| `libpq-dev` | PostgreSQL client headers for `psycopg2` build | `requirements.txt:L55-L58` (`psycopg2`) |
| `libxml2-dev` | XML parsing headers for `lxml` build | `requirements.txt:L34-L36` (`lxml`) |
| `libxslt1-dev` | XSLT headers for `lxml` build | `requirements.txt:L34-L36` (`lxml`) |
| `libjpeg-dev` | JPEG codec headers for `Pillow` build | `requirements.txt:L47-L50` (`Pillow`) |
| `libpng-dev` | PNG codec headers for `Pillow` build | `requirements.txt:L47-L50` (`Pillow`) |
| `zlib1g-dev` | zlib headers for `Pillow`, `Werkzeug` compression | `requirements.txt:L47-L50` (`Pillow`) |
| `libfreetype6-dev` | TrueType font support for `Pillow` build | `requirements.txt:L47-L50` (`Pillow`) |
| `liblcms2-dev` | Color profile headers for `Pillow` | `requirements.txt:L47-L50` (`Pillow`) |
| `libwebp-dev` | WebP codec headers for `Pillow` build | `requirements.txt:L47-L50` (`Pillow`); `odoo/tools/image.py` uses webp |
| `libldap2-dev` | OpenLDAP headers for `python-ldap` build | `requirements.txt:L69-L70` (`python-ldap`) |
| `libsasl2-dev` | SASL headers for `python-ldap` build | `requirements.txt:L69-L70` (`python-ldap`) |
| `libsasl2-modules` | Runtime SASL plugins | `requirements.txt:L69-L70` (`python-ldap`) |
| `libssl-dev` | OpenSSL headers for `cryptography`, `pyopenssl` builds | `requirements.txt:L13` (`cryptography`); `requirements.txt:L60` (`pyopenssl`) |
| `libffi-dev` | libffi headers for `cryptography` build | `requirements.txt:L13` (`cryptography`) |
| `libmagic1` | libmagic shared object for `python-magic` runtime | `requirements.txt:L67-L68` (`python-magic`) |
| `libusb-1.0-0-dev` | libusb headers for `pyusb` build | `requirements.txt:L74` (`pyusb`) |
| `libev-dev` | libev headers for `gevent` build (when wheel not used) | `requirements.txt:L23` (`gevent`) |
| `node-less` | LESS compiler (legacy asset pipeline) | `odoo/tools/js_transpiler.py` and asset pipeline (cited indirectly) |
| `fonts-noto-cjk` | Noto Sans CJK fonts for PDF rendering with Asian scripts | `odoo.tools.pdf` and `reportlab` (`requirements.txt:L77-L79`) |
| `wkhtmltopdf` | HTML-to-PDF binary (when available in archive; optional) | `odoo.tools.pdf` referencing wkhtmltopdf invocations |
| `postgresql-16` (or any `>=13`) | PostgreSQL server | `odoo/release.py:L41` (`MIN_PG_VERSION = 13`) |
| `postgresql-client-16` | psql, pg_dump, pg_restore | `odoo/service/db.py` `find_pg_tool` references `pg_dump`, `psql`, `pg_restore` |
| `git` | Source-tree introspection (auto-update workflows) | `odoo/cli/upgrade_code.py` references; optional |
| `ca-certificates` | TLS root certificates for outbound HTTPS | `requirements.txt:L80-L81` (`requests`); standard |
| `curl` | Validation HTTP probe in the run-cycle | (validation tooling, not a runtime requirement) |

### 0.4.4 Dependency Updates

This task does not introduce, update, or remove any dependency. The deliverable is a single new documentation file; `requirements.txt` is read-only.

- **New dependencies to add:** None.
- **Dependencies to update:** None.
- **Dependencies to remove:** None.
- **Import/Reference Updates:** None — no Python module is created, modified, or relocated.


## 0.5 Implementation Design

### 0.5.1 Technical Approach

The implementation is a single-file documentation deliverable backed by deterministic source scanning, source-cited derivation, and a closed-loop execution-and-correction validation cycle. The Blitzy platform achieves the user's five CRITICAL Directives through the following primary objectives, each mapped to specific implementation actions:

- **Achieve verifiable build/run reference** by creating `BUILD_AND_RUN.md` at repository root, populated through a deterministic five-section scaffold (Prerequisites, Build, Run, Environment Variables, Secrets) plus a sixth `## Validation Evidence` section, where every entry carries a `[source: path/to/file:L<start>-L<end>]` citation. The rationale: the user's Citation gate (Directive 5) requires 100% source-cited entries, and a fixed scaffold ensures no required component is omitted.
- **Achieve source-restriction compliance** by routing every derivation through a fixed PERMITTED-files allowlist (per Section 0.2.1.1) and explicitly excluding the PROHIBITED-files denylist (per Section 0.2.1.3). The rationale: the user's Source restriction gate (Directive 5) requires zero references to README/CONTRIBUTING/INSTALL/docs/*.rst, and an allowlist-first approach makes accidental inclusion structurally impossible.
- **Achieve exhaustive environment-variable enumeration** by performing a deterministic three-pass scan of permitted source files: (1) read every `_OdooOption(...)` and `parser.add_option(...)` call in `odoo/tools/config.py:L207-L494` and emit each option's `dest` into the table with its computed `env_name` (explicit value when present, else `'ODOO_' + dest.upper()` per `odoo/tools/config.py:L105-L109`); (2) `grep -rn "os\\.environ\\|os\\.getenv\\|getenv" odoo/ setup/ --include="*.py"` and emit each unique variable not already in the table; (3) `grep -rnE '\\$\\{?[A-Z_][A-Z0-9_]*' setup/ --include="*.sh"` for shell variable references. The rationale: the user's Coverage gate (Directive 5) requires zero env-var references in scanned source to be absent from the output table, and a programmatic three-pass scan is reproducible and auditable.
- **Achieve secrets isolation with security findings** by passing the env-var table through the secret-classification regex `(password|secret|key|token|credential|apikey|auth|private|cert)` and the value-side authentication-call check, then producing a separate Secrets table with `Default-Override-Required` and `Hardcoded-Default-Finding` columns. The rationale: the user's Directive 3 requires separate listing and explicit security-finding flagging.
- **Achieve execution-validation evidence** by running the documented build and run instructions in a fresh container, capturing the full `bash -x` transcript with `date +%FT%T.%N` timestamps, probing readiness via `curl -s -o /dev/null -w "%{http_code} %{time_total}s\\n" http://localhost:8069/web/database/selector` with retry up to 120 s, capturing `ps -ef --forest` at ready state, and appending all of this to `BUILD_AND_RUN.md` under `## Validation Evidence`. The rationale: Directive 4 requires evidence of a successful final cycle on a clean environment.

The logical implementation flow (NOT a timeline; describes ordering of operations, not scheduling):

- **First, establish the scan baseline** by reading every PERMITTED source file in scope per Section 0.3.1 (`setup.py`, `setup.cfg`, `requirements.txt`, `odoo/release.py`, `odoo/__main__.py`, the entire `odoo/cli/` directory, `odoo/tools/config.py`, `odoo/tools/appdirs.py`, `odoo/sql_db.py`, `odoo/service/server.py`, `odoo/service/db.py`, `odoo/http.py`, `odoo/modules/__init__.py`, `odoo/modules/db.py`, `odoo/modules/loading.py`, `odoo/modules/module.py`, `odoo/netsvc.py`, `setup/debinstall.sh`, `setup/odoo-wsgi.example.py`, `setup/package.py`, `setup/requirements-check.py`, and `debian/odoo.conf`) and producing an in-memory derivation index keyed by file path and line range.
- **Next, derive each output table column** by querying the index with deterministic patterns — Prerequisites by reverse-mapping `requirements.txt` Python packages to their apt-package headers, Build by following `setup/debinstall.sh:L9` apt-get install template + `pip install -r requirements.txt` + `pip install -e .`, Run by reading `odoo/__main__.py:L1` + `odoo/cli/command.py:L127-L129` (default `server` command) + `odoo/cli/server.py:L95-L119` lifecycle, Env Vars by the three-pass scan above, Secrets by classification regex.
- **Next, produce the draft `BUILD_AND_RUN.md`** with all six sections fully populated and every entry source-cited.
- **Next, provision a clean Ubuntu 24.04 container** (image `ubuntu:24.04`), run `apt-get install` on the documented OS prerequisites, install Python 3.13 from the deadsnakes PPA, install `postgresql-16` from the Ubuntu archive, create the `odoo` Python venv, run the documented build sequence, run the documented run sequence with explicit env vars, and probe HTTP readiness on ports 8069 (WSGI) and 8072 (gevent).
- **Next, capture validation evidence** — the OS image string (e.g., `Ubuntu 24.04.4 LTS noble`), the full transcript, the HTTP status and latency, the process tree, and the correction-cycle count — and append the `## Validation Evidence` section to `BUILD_AND_RUN.md`.
- **Finally, ensure quality** by re-scanning the repository for env-var references and diffing against the table to verify the Coverage gate is satisfied; running `grep -E "(README|CONTRIBUTING|INSTALL|docs/|\\.rst)" BUILD_AND_RUN.md` to verify the Source restriction gate (must return zero matches); verifying every entry in every table is followed by a `[source: path/to/file:L<start>-L<end>]` citation to satisfy the Citation gate; and verifying the `## Validation Evidence` section reports a successful final cycle to satisfy the Execution evidence gate.

### 0.5.2 Component Impact Analysis

#### 0.5.2.1 Direct Modifications Required

The deliverable creates one file. No existing component is modified.

| Component | Modification | Source-Citation Anchor |
|-----------|--------------|------------------------|
| `BUILD_AND_RUN.md` (new file at repo root) | Create with six sections (Prerequisites, Build, Run, Environment Variables, Secrets, Validation Evidence). Every entry includes `[source: path/to/file:L<start>-L<end>]` citations | Multiple — see Section 0.6 File Transformation Mapping |

#### 0.5.2.2 Indirect Impacts and Dependencies

The deliverable does not change any module's interface, configuration, or behavior. Indirect impacts are limited to:

- **Repository discoverability** — `BUILD_AND_RUN.md` provides a non-prose-documentation entry-point for users seeking authoritative build/run information; users who currently consult README.md can additionally consult `BUILD_AND_RUN.md`.
- **Validation footprint** — the validation cycle creates a transient `odoo_test` PostgreSQL database, a transient `/var/lib/Odoo` (or `~/.local/share/Odoo`) data directory, and a transient pidfile under the validation container. None of these persist to the repository. The repository is unmodified except for the new file.

#### 0.5.2.3 New Component Introduction

| Component | Type | Responsibility | Rationale |
|-----------|------|----------------|-----------|
| `BUILD_AND_RUN.md` | Markdown documentation file | Single source-derived reference for OS prerequisites, build commands, run commands, environment variables, secrets, and validation evidence | The user's CRITICAL Directive 5 mandates a single new file at repository root, named `BUILD_AND_RUN.md`, and explicitly forbids modifying any other file |

### 0.5.3 User Interface Design

This task has no user-interface dimension. The deliverable is a markdown documentation file consumed by humans through `git`-hosted markdown rendering or any text editor; there is no addon, view, controller, or web asset to design.

### 0.5.4 User-Provided Examples Integration

The user provided no concrete code examples. The user provided five CRITICAL Directives whose verbatim text appears in Section 0.1.4 with each directive paraphrased into actionable Blitzy-platform behavior in Section 0.5.1. The user's directive on the **citation format** (`[source: path/to/file:L42-L58]`) is preserved exactly: every citation in the deliverable uses square brackets, the literal `source: ` prefix, the path, a colon, and an `L<start>-L<end>` line range.

### 0.5.5 Critical Implementation Details

The following details are essential for correct implementation and are derived from the source:

- **Default-command resolution in CLI dispatch.** `odoo/cli/command.py:L119-L129` shows that when `argv[1:]` does not start with a non-flag token and does not contain `-h`/`--help`, the command is `'server'`. Therefore `python -m odoo` and `python -m odoo --http-port 8069` both invoke `Server.run`; only `python -m odoo db init ...` invokes a non-default subcommand. The Run section of `BUILD_AND_RUN.md` documents the default form.
- **Configuration precedence order.** `odoo/tools/config.py:L164-L170` defines `self.options = collections.ChainMap(self._runtime_options, self._cli_options, self._env_options, self._file_options, self._default_options)`. The precedence (highest first) is: runtime → CLI → environment → config-file → built-in defaults. The Env Vars section of `BUILD_AND_RUN.md` documents this precedence so the reader knows that, e.g., `--db_host` on the command line overrides `PGHOST` in the environment which overrides `db_host=` in the config file which overrides the built-in default `''` (empty string).
- **Auto-generated environment variable names.** `odoo/tools/config.py:L105-L109`: `if env_name is None and is_new_option and self.file_loadable: self.env_name = 'ODOO_' + self.dest.upper()`. This rule generates an `ODOO_<UPPERNAME>` env var for every file-loadable option that does not have an explicit `env_name`. The Env Vars table must include both explicit (PGUSER, PGPASSWORD, PGHOST, PGPORT, PGDATABASE, PGSSLMODE, PGAPPNAME, PGPATH, PGHOST_REPLICA, PGPORT_REPLICA, PGDATABASE_TEMPLATE, ODOO_RC, ODOO_DEV) and auto-generated (`ODOO_HTTP_PORT`, `ODOO_HTTP_INTERFACE`, `ODOO_GEVENT_PORT`, `ODOO_DBFILTER`, `ODOO_DATA_DIR`, `ODOO_PIDFILE`, `ODOO_ADDONS_PATH`, `ODOO_UPGRADE_PATH`, `ODOO_LOGFILE`, `ODOO_LOG_LEVEL`, `ODOO_LOG_HANDLER`, `ODOO_LOG_DB`, `ODOO_LOG_DB_LEVEL`, `ODOO_DB_USER`, `ODOO_DB_PASSWORD`, `ODOO_DB_HOST`, `ODOO_DB_PORT`, `ODOO_DB_SSLMODE`, `ODOO_DB_APP_NAME`, `ODOO_DB_MAXCONN`, `ODOO_DB_MAXCONN_GEVENT`, `ODOO_DB_TEMPLATE`, `ODOO_DB_REPLICA_HOST`, `ODOO_DB_REPLICA_PORT`, `ODOO_LIST_DB`, `ODOO_PROXY_MODE`, `ODOO_X_SENDFILE`, `ODOO_HTTP_ENABLE`, `ODOO_SERVER_WIDE_MODULES`, `ODOO_WORKERS`, `ODOO_LIMIT_MEMORY_SOFT`, `ODOO_LIMIT_MEMORY_SOFT_GEVENT`, `ODOO_LIMIT_MEMORY_HARD`, `ODOO_LIMIT_MEMORY_HARD_GEVENT`, `ODOO_LIMIT_TIME_CPU`, `ODOO_LIMIT_TIME_REAL`, `ODOO_LIMIT_TIME_REAL_CRON`, `ODOO_LIMIT_TIME_WORKER_CRON`, `ODOO_MAX_CRON_THREADS`, `ODOO_LIMIT_REQUEST`, `ODOO_TRANSIENT_AGE_LIMIT`, `ODOO_OSV_MEMORY_COUNT_LIMIT`, `ODOO_UNACCENT`, `ODOO_GEOIP_CITY_DB`, `ODOO_GEOIP_COUNTRY_DB`, `ODOO_SCREENSHOTS`, `ODOO_SCREENCASTS`, `ODOO_SYSLOG`, `ODOO_SMTP_SERVER`, `ODOO_SMTP_PORT`, `ODOO_SMTP_SSL`, `ODOO_SMTP_USER`, `ODOO_EMAIL_FROM`, `ODOO_FROM_FILTER`, etc.) variants. Each entry cites the parser line in `odoo/tools/config.py`.
- **Required server-wide modules.** `odoo/tools/config.py:L30-L31`: `DEFAULT_SERVER_WIDE_MODULES = ['base', 'rpc', 'web']`, `REQUIRED_SERVER_WIDE_MODULES = ['base', 'web']`. The Run section must document `--load=base,web,rpc` (or the `--load` default) and that omitting `base` or `web` is silently corrected by `odoo/tools/config.py:L658-L663` `_postprocess_options`.
- **Postgres-user rejection.** `odoo/cli/server.py:L37-L44` `check_postgres_user()` exits with status 1 if `config['db_user']` or `os.environ.get('PGUSER')` equals `'postgres'`. The Run section must document this constraint and instruct the reader to create a non-superuser PostgreSQL role (typically `odoo`).
- **Database auto-creation behavior.** `odoo/cli/server.py:L101-L113` iterates `config['db_name']` and calls `db._create_empty_database` for each, catching `InsufficientPrivilege` (warns and skips) and `DatabaseExists` (silently passes). The Run section must document that the `odoo` PostgreSQL role needs `CREATEDB` for first-run auto-bootstrap.
- **First-run module install.** A freshly created database is empty until the `base` module is installed via `-i base`. The Run section must document a two-phase first run: phase 1 = `python -m odoo -d odoo_test -i base --without-demo=all --stop-after-init` (seeds DB and exits); phase 2 = `python -m odoo -d odoo_test --http-interface 0.0.0.0 --http-port 8069` (steady state). `odoo/cli/server.py:L115-L119` shows that `stop_after_init` causes the server to stop after preload, which is the seeding semantics.
- **WSGI deployment alternative.** `setup/odoo-wsgi.example.py:L13-L17` exposes `application = odoo.http.root` and shows `gunicorn odoo.http:root --pythonpath . -c odoo-wsgi.py`. The Run section documents this alternative as well, citing the WSGI globals (`bind`, `workers`, `timeout`, `max_requests`) on `setup/odoo-wsgi.example.py:L43-L47`.
- **Ready-state probe targets.** The HTTP probe targets `http://0.0.0.0:8069/web/database/selector` (a no-database HTTP route in `odoo/http.py` that always responds when WSGI is up) for the main worker, and `http://0.0.0.0:8072/longpolling/poll` (or the WebSocket endpoint) for the gevent worker. Both must be reachable within 120 seconds for the validation to declare success.
- **Process tree verification.** At ready state, `ps -ef --forest` should show the parent `python -m odoo` process and (if `--workers > 0`) child worker processes plus a gevent worker. The default is `--workers=0` (threaded mode per `odoo/tools/config.py:L457-L459`); the validation cycle uses the default to minimize complexity.
- **Master password security finding.** `odoo/tools/config.py:L207`: `parser.add_option(FileOnlyOption(dest='admin_passwd', my_default='admin'))`. This is a hardcoded default for a secret, so the Secrets table must flag it with a security finding. The deliverable does **not** reproduce the literal value `'admin'`; it cites the file:line.
- **Citation format enforcement.** Every claim of the form "Odoo's default port is 8069", "Python ≥ 3.10 is required", "the master password defaults to a hardcoded value" is followed immediately by the appropriate `[source: path/to/file:L<start>-L<end>]` tag. Claims without citations are removed.

### 0.5.6 Logical Flow Diagram

```mermaid
flowchart TD
    A[Start: Read CRITICAL Directives 1-5] --> B[Scan PERMITTED source files only]
    B --> C[Build derivation index<br/>file path -> line range -> claim]
    C --> D[Derive Prerequisites table<br/>from requirements.txt + setup/debinstall.sh]
    C --> E[Derive Build commands<br/>from setup.py + requirements.txt]
    C --> F[Derive Run commands<br/>from odoo/__main__.py + odoo/cli/server.py + odoo/tools/config.py]
    C --> G[Derive Env Vars table<br/>three-pass scan]
    C --> H[Derive Secrets table<br/>classification regex + value-side check]
    D --> I[Compose draft BUILD_AND_RUN.md<br/>with [source:...] citations]
    E --> I
    F --> I
    G --> I
    H --> I
    I --> J[Provision clean Ubuntu 24.04 container]
    J --> K[Install Python 3.13 + PostgreSQL 16]
    K --> L[Execute documented build sequence]
    L --> M[Execute documented run sequence<br/>with min env vars + valid test secrets]
    M --> N{HTTP probe<br/>:8069 + :8072<br/>within 120s?}
    N -- No --> O{Cycle count < 5?}
    O -- Yes --> P[Trace failure to source file<br/>and correct instruction]
    P --> L
    O -- No --> Q[Halt and report ambiguity]
    N -- Yes --> R[Capture validation evidence:<br/>OS image, transcript,<br/>HTTP status+latency, process tree,<br/>cycle count]
    R --> S[Append to BUILD_AND_RUN.md<br/>under ## Validation Evidence]
    S --> T[Run completeness gates:<br/>Coverage, Citation,<br/>Source restriction, Execution evidence]
    T --> U{All gates pass?}
    U -- No --> P
    U -- Yes --> V[Final BUILD_AND_RUN.md committed]
```


## 0.6 File Transformation Mapping

### 0.6.1 File-by-File Execution Plan

The deliverable creates exactly one file. Every other file listed below is a **REFERENCE** input — read for derivation but not modified. The user's Directive 5 final clause forbids modifications to any file except the new `BUILD_AND_RUN.md`.

| Target File | Transformation | Source File / Reference | Purpose / Changes |
|-------------|----------------|--------------------------|-------------------|
| `BUILD_AND_RUN.md` | CREATE | `setup.py`, `setup.cfg`, `requirements.txt`, `odoo/release.py`, `odoo/__main__.py`, `odoo/cli/command.py`, `odoo/cli/server.py`, `odoo/tools/config.py`, `odoo/tools/appdirs.py`, `odoo/sql_db.py`, `odoo/service/server.py`, `odoo/service/db.py`, `odoo/http.py`, `odoo/modules/db.py`, `odoo/modules/loading.py`, `odoo/modules/module.py`, `odoo/netsvc.py`, `setup/debinstall.sh`, `setup/odoo-wsgi.example.py`, `setup/package.py`, `setup/requirements-check.py`, `debian/odoo.conf` | Single new markdown file at repository root containing six sections: (1) OS Prerequisites table; (2) Build commands with citations; (3) Run commands with citations and configuration precedence guidance; (4) Environment Variables table grouped by domain (database, mail, workers, addons paths, logging, security) with `Variable | Default | Required | Purpose | Source` columns; (5) Secrets table with separate listing and security-finding flags; (6) `## Validation Evidence` section with OS image, transcript, ready-state HTTP status and latency, process tree, and correction-cycle count |
| `setup.py` | REFERENCE | `setup.py` | Read-only. Source for `install_requires`, `python_requires`, `extras_require`, `tests_require`, `scripts`, `package_dir`, and dynamic loading of `odoo/release.py` for `version`, `MIN_PY_VERSION` |
| `setup.cfg` | REFERENCE | `setup.cfg` | Read-only. Source for setuptools `[install] optimize=1` and `[flake8]` configuration; informs that no PEP 517 build backend is configured |
| `requirements.txt` | REFERENCE | `requirements.txt` | Read-only. Source for every Python package version pin and platform/Python-version conditional marker. Used to derive both the Python dependency table and (by reverse-mapping) the OS prerequisite list |
| `odoo/release.py` | REFERENCE | `odoo/release.py` | Read-only. Source for `version_info` (19.0.0), `MIN_PY_VERSION` (3,10), `MAX_PY_VERSION` (3,13), `MIN_PG_VERSION` (13), `nt_service_name` |
| `odoo/__main__.py` | REFERENCE | `odoo/__main__.py` | Read-only. Source for the canonical `python -m odoo` entry point that delegates to `odoo.cli.command.main()` |
| `odoo/cli/command.py` | REFERENCE | `odoo/cli/command.py` | Read-only. Source for `main()` lifecycle, default-command resolution to `'server'`, the `--addons-path=` early-parse hook, and the `commands` registry semantics |
| `odoo/cli/server.py` | REFERENCE | `odoo/cli/server.py` | Read-only. Source for `Server.run`, `check_root_user`, `check_postgres_user` (PGUSER='postgres' rejection), `report_configuration` (PG env-var fallbacks), the auto-DB-create loop on `config['db_name']`, `setup_pid_file`, and `server.start(preload=...)` invocation |
| `odoo/cli/db.py` | REFERENCE | `odoo/cli/db.py` | Read-only. Source for `db init`, `db dump`, `db restore`, `db rename`, `db drop` semantics; informs `Db` sub-command flags for the run section's optional ops commands |
| `odoo/cli/deploy.py` | REFERENCE | `odoo/cli/deploy.py` | Read-only. Source for the HTTP module-deploy CLI; informs the `--verify-ssl` and HTTP login behavior; not required for ready-state run, but referenced if the env-var scan finds it |
| `odoo/cli/start.py` | REFERENCE | `odoo/cli/start.py` | Read-only. Source for the auto-discover-modules convenience that derives `--db-filter` from cwd; informs `MANIFEST_NAMES` constant referenced from `odoo/modules/module.py` |
| `odoo/cli/shell.py` | REFERENCE | `odoo/cli/shell.py` | Read-only. Source for the interactive shell sub-command; not required for ready-state run |
| `odoo/cli/scaffold.py` | REFERENCE | `odoo/cli/scaffold.py` | Read-only. Source for the addon-scaffold CLI; not required for ready-state run |
| `odoo/cli/i18n.py` | REFERENCE | `odoo/cli/i18n.py` | Read-only. Source for translation import/export CLI; not required for ready-state run |
| `odoo/cli/cloc.py` | REFERENCE | `odoo/cli/cloc.py` | Read-only. Source for code-line-count CLI; not required for ready-state run |
| `odoo/cli/module.py` | REFERENCE | `odoo/cli/module.py` | Read-only. Source for module install/upgrade/uninstall CLI semantics |
| `odoo/cli/neutralize.py` | REFERENCE | `odoo/cli/neutralize.py` | Read-only. Source for the SQL-neutralization sub-command |
| `odoo/cli/obfuscate.py` | REFERENCE | `odoo/cli/obfuscate.py` | Read-only. Source for the pgcrypto-based field-obfuscation sub-command |
| `odoo/cli/populate.py` | REFERENCE | `odoo/cli/populate.py` | Read-only. Source for the test-data population sub-command |
| `odoo/cli/upgrade_code.py` | REFERENCE | `odoo/cli/upgrade_code.py` | Read-only. Source for the upgrade-script execution sub-command |
| `odoo/cli/help.py` | REFERENCE | `odoo/cli/help.py` | Read-only. Source for the `help` sub-command |
| `odoo/tools/config.py` | REFERENCE | `odoo/tools/config.py` | Read-only. **Primary source** for the entire Environment Variables table and most of the Secrets table. Every `parser.add_option(...)` invocation in `_build_cli` (lines 207–494) yields one option whose `dest`, `my_default`, `env_name`, `cli_loadable`, `file_loadable` flags determine its env-var name, default, and required/optional classification |
| `odoo/tools/appdirs.py` | REFERENCE | `odoo/tools/appdirs.py` | Read-only. Source for cross-platform data-dir resolution: XDG variable handling, macOS Library paths, Windows CSIDL paths. Informs the `data_dir` default computation in `odoo/tools/config.py:L505-L511` |
| `odoo/sql_db.py` | REFERENCE | `odoo/sql_db.py` | Read-only. Source for `connection_info_for`, `db_connect`, `ConnectionPool`, `Cursor` — confirms which `db_*` config keys are read at runtime |
| `odoo/service/server.py` | REFERENCE | `odoo/service/server.py` | Read-only. Source for `CommonServer`, `ThreadedServer`, `GeventServer`, `PreforkServer`, `Worker`, `set_limit_memory_hard` (RLIMIT_AS), the `inotify`/`watchdog` source-watching feature, signal handling. Informs the workers/limit env-vars |
| `odoo/service/db.py` | REFERENCE | `odoo/service/db.py` | Read-only. Source for `_create_empty_database`, `find_pg_tool`, `exec_pg_environ`, dump/restore semantics — confirms `pg_dump`/`pg_restore`/`psql` binary requirements |
| `odoo/http.py` | REFERENCE | `odoo/http.py` | Read-only. Source for the WSGI `Application` (`root`), session/CSRF/CORS handling, `proxy_mode` and `x_sendfile` semantics, GeoIP database loading. Confirms HTTP-related config keys are read at runtime |
| `odoo/modules/db.py` | REFERENCE | `odoo/modules/db.py` | Read-only. Source for `is_initialized(cr)`, `initialize(cr)` which executes `base/data/base_data.sql`, `has_unaccent`, `has_trigram`. Informs first-run install behavior (`-i base`) |
| `odoo/modules/loading.py` | REFERENCE | `odoo/modules/loading.py` | Read-only. Source for `load_modules`, `load_module_graph`, demo-data semantics, test-execution semantics, registry signaling |
| `odoo/modules/module.py` | REFERENCE | `odoo/modules/module.py` | Read-only. Source for `Manifest` class, `MANIFEST_NAMES`, `__manifest__.py` parsing, `initialize_sys_path()` (which adds `odoo.addons.__path__`) |
| `odoo/modules/migration.py` | REFERENCE | `odoo/modules/migration.py` | Read-only. Source for `MigrationManager`, `VERSION_RE`, migration-script signature requirements |
| `odoo/netsvc.py` | REFERENCE | `odoo/netsvc.py` | Read-only. Source for `init_logger`, `ColoredFormatter`, `WatchedFileHandler`, `PostgreSQLHandler`. Informs logging env vars |
| `odoo/loglevels.py` | REFERENCE | `odoo/loglevels.py` | Read-only. Source for the textual log-level constants accepted by `--log-level` |
| `setup/debinstall.sh` | REFERENCE | `setup/debinstall.sh` | Read-only. Source for `apt-get install -y --no-install-recommends`, `DEBIAN_FRONTEND=noninteractive`, `xargs`, dry-run/quiet flag patterns, the `id -u` privilege-detection. Note: it references `../debian/control` which is **absent** from this repo copy, so the OS-prereq list cannot be auto-extracted from it; manual reverse-mapping is required |
| `setup/odoo-wsgi.example.py` | REFERENCE | `setup/odoo-wsgi.example.py` | Read-only. Source for the Gunicorn deployment alternative: `application = odoo.http.root`, `bind = '127.0.0.1:8069'`, `workers = 4`, `timeout = 240`, `max_requests = 2000`. Documents the alternate WSGI run command for production deployments |
| `setup/package.py` | REFERENCE | `setup/package.py` | Read-only. Source for the build-time secrets `GPGPASSPHRASE` and `GPGID`. Informs the Secrets table's build-time entries |
| `setup/requirements-check.py` | REFERENCE | `setup/requirements-check.py` | Read-only. Source for the package-name → distro-package mapping (e.g., `SPECIAL = {'pytz': 'tz', 'libsass': 'libsass-python'}`). Informs the Prerequisites table where Python and Debian package names diverge |
| `debian/odoo.conf` | REFERENCE | `debian/odoo.conf` | Read-only. Source for the canonical INI-format config template with `db_host=False`, `db_port=False`, `db_user=odoo`, `db_password=False`, `default_productivity_apps=True`, and commented `admin_passwd = admin` and `addons_path = /usr/lib/python3/dist-packages/odoo/addons` examples. Informs the Run section's config-file format documentation |
| `addons/*/__manifest__.py` (300+ files) | REFERENCE | `addons/*/__manifest__.py` | Read-only. Each manifest provides one addon's `name`, `version`, `depends`, `auto_install`. Used only to confirm addons-path content; individual manifests are not cited in the deliverable |
| `odoo/addons/base/__manifest__.py` | REFERENCE | `odoo/addons/base/__manifest__.py` | Read-only. The `base` module manifest — required for first-run install (`-i base`); confirms the `base` module exists at `odoo/addons/base/` |

The repository contains other files not listed above (e.g., `LICENSE`, `.weblate.json`, `ruff.toml`, every `addons/*/models/*.py`, `addons/*/views/*.xml`, etc.). None of these are read for derivation. Specifically, `LICENSE`, `.weblate.json`, and `ruff.toml` are explicitly **not** sources for the deliverable because they do not provide build/run/env/secret information; the Blitzy platform notes their existence but does not consume them. Files under `addons/*/models/`, `addons/*/views/`, `addons/*/static/`, `addons/*/security/`, `addons/*/data/`, `addons/*/tests/`, `addons/*/wizard/`, `addons/*/report/`, and `addons/*/controllers/` are out of scope because they implement individual addon business logic and do not contain build/run-time configuration for the server itself.

### 0.6.2 New Files Detail

#### 0.6.2.1 `BUILD_AND_RUN.md`

- **Path:** `BUILD_AND_RUN.md` (repository root)
- **Content type:** Documentation (markdown)
- **Based on:** No reference file; this is a new artifact derived from the source-citation index built across the REFERENCE files listed in Section 0.6.1
- **Key sections (verbatim section-titles to be used in the file):**
    - `# BUILD_AND_RUN.md`
    - `## OS Prerequisites` — apt-package table with `Apt Package | Required For | Source` columns; PostgreSQL version requirement; Python version requirement; tools (curl, ca-certificates)
    - `## Build` — sequential numbered steps:
        - Step 1 — `apt-get install -y --no-install-recommends ...` (the prerequisite list, citing each package's derivation source)
        - Step 2 — `add-apt-repository -y ppa:deadsnakes/ppa && apt-get install -y python3.13 python3.13-venv python3.13-dev` (citing `odoo/release.py:L40` for the version)
        - Step 3 — `python3.13 -m venv /opt/odoo-venv && source /opt/odoo-venv/bin/activate` (citing `setup.py:L70` for the venv requirement)
        - Step 4 — `pip install -r requirements.txt` (citing `requirements.txt:L1`)
        - Step 5 — `pip install -e .` (citing `setup.py:L13`)
    - `## Run` — sequential numbered steps:
        - Step 1 — Create PostgreSQL role: `sudo -u postgres createuser --createdb --no-superuser --pwprompt odoo` (citing `odoo/cli/server.py:L37-L44` for the non-superuser constraint)
        - Step 2 — First-run seed: `python -m odoo -d odoo_db -i base --without-demo=all --stop-after-init` (citing `odoo/__main__.py:L1`, `odoo/cli/command.py:L127-L129`, `odoo/cli/server.py:L101-L113`, `odoo/cli/server.py:L115-L119`)
        - Step 3 — Steady state: `python -m odoo -d odoo_db --http-interface 0.0.0.0 --http-port 8069 --gevent-port 8072` (citing `odoo/tools/config.py:L255-L260`)
        - Step 4 — Optional WSGI alternative: `gunicorn odoo.http:root --pythonpath . -c setup/odoo-wsgi.example.py` (citing `setup/odoo-wsgi.example.py:L13-L17,L43-L47`)
    - `## Configuration File` — INI format example based on `debian/odoo.conf`, with the `[options]` section header, all required keys explained, and a note about config-file precedence per `odoo/tools/config.py:L164-L170`
    - `## Environment Variables` — grouped sub-sections (Database, HTTP/Web, Mail/SMTP, Workers/Process, Addons/Paths, Logging/Security, Internationalization), each with `Variable | Default | Required | Purpose | Source` table
    - `## Secrets` — separate table `Secret | Consumption Point | Expected Format | Default Override Required | Hardcoded-Default Finding`; the `admin_passwd` row carries an explicit "⚠️ SECURITY FINDING: hardcoded default — MUST be overridden" annotation citing `odoo/tools/config.py:L207`; no literal value reproduced
    - `## Validation Evidence` — populated only after successful execution: OS image string, full bash transcript with timestamps, `curl -w "%{http_code} %{time_total}s\\n"` HTTP probe results, `ps -ef --forest` output, correction-cycle count

### 0.6.3 Files to Modify Detail

No existing file is modified.

### 0.6.4 Configuration and Documentation Updates

This task does not update any configuration file. The only update is the creation of `BUILD_AND_RUN.md`. No cross-references are introduced into existing documentation.

### 0.6.5 Cross-File Dependencies

The deliverable's correctness depends on internal consistency between the Prerequisites, Build, Run, Environment Variables, and Secrets sections within `BUILD_AND_RUN.md`. Specifically:

- The Python version cited in Prerequisites (`3.13`) must match the version invoked in Build (`python3.13 -m venv`).
- The PostgreSQL version cited in Prerequisites (`16`, satisfying `>=13`) must match the version provisioned in the Run preamble.
- The HTTP ports cited in Run (`8069`, `8072`) must match the env-vars `ODOO_HTTP_PORT` and `ODOO_GEVENT_PORT` and the Validation Evidence probe targets.
- The PostgreSQL role name documented in Run (`odoo`) must not conflict with the `db_user='postgres'` rejection in `odoo/cli/server.py:L42`.
- The minimum required env vars listed in the Environment Variables table (any with `Required = Yes`) must match the env vars set during the Validation Evidence run.
- Every entry in the Secrets table must also appear (or be cross-referenced) in the Environment Variables table, ensuring no secret is documented without its corresponding env-var consumption point.

These cross-section consistency checks are part of the Quality Validation step (Section 0.5.1 final clause) and are run before the deliverable is finalized.


## 0.7 Rules

### 0.7.1 Task-Specific Rules and Requirements

The following rules are extracted from the user's CRITICAL Directives and are non-negotiable. Each is restated in operational form so the Blitzy platform applies them consistently throughout execution.

- **Rule R1 — Source allowlist (Directive 1).** Only the file types and paths in the PERMITTED list shall be opened, read, summarized, paraphrased, or cited. Specifically: `Dockerfile*`, `docker-compose*.yml`, `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements*.txt`, `MANIFEST.in`, `__manifest__.py`, `Makefile`, `*.sh`, `.github/workflows/*`, `.gitlab-ci.yml`, `package.json`, `debian/`, `odoo-bin`, and entry-point Python modules. Files of types not in this list shall be omitted from the deliverable's derivation chain.
- **Rule R2 — Source denylist (Directive 1).** The following shall **never** be opened, read, summarized, or referenced in `BUILD_AND_RUN.md` or in any derivation reasoning: `README*`, `CONTRIBUTING*`, `INSTALL*`, anything under `docs/`, any `*.rst` file, wiki content, blog posts, forum posts, any human-authored prose documentation. This rule is enforced by a final-pass `grep` over the deliverable for the strings `README`, `CONTRIBUTING`, `INSTALL`, `docs/`, and `.rst`; any non-zero match fails the Source restriction gate.
- **Rule R3 — Citation format (Directive 1).** Every build instruction, run instruction, environment variable entry, and secret entry shall carry a citation in the exact format `[source: path/to/file:L42-L58]`. The leading `[`, the literal `source:` token, the path, the colon, the literal `L`, the start line number, the dash, the literal `L`, the end line number, the trailing `]` are all required. Single-line citations use `Lxx-Lxx` (same start and end). Citations span only contiguous line ranges; non-contiguous evidence requires multiple separate citations.
- **Rule R4 — Comments explain WHY (Directive 1).** Where the deliverable adds explanatory prose around a citation, the prose explains **why** the cited code yields the documented behavior, not what the code line says. The citation itself proves what the code says; the prose adds rationale ("this implies", "this means at runtime", "as a consequence").
- **Rule R5 — Environment variable scan completeness (Directive 2).** The env-var scan shall traverse all `.py`, `.sh`, `.yml`, `Dockerfile*`, and entry-point files for `os.environ`, `os.getenv`, `getenv`, `${VAR}`, `$VAR`, and `config.get` references. The output table must include columns `Variable | Default | Required | Purpose | Source`. Variables shall be grouped by functional domain (database, mail, workers, addons paths, logging, security). No variable may appear without a source citation. No purpose may be stated without code-derived evidence. The Coverage gate (Directive 5) requires zero unmatched references between scan and table.
- **Rule R6 — Secret classification and isolation (Directive 3).** A value is classified as a secret if (1) it is read from environment, file, or vault AND (2) its variable name or usage context contains any of: `password`, `secret`, `key`, `token`, `credential`, `apikey`, `auth`, `private`, `cert`; OR it is the value side of a database/SMTP/API authentication call. Secrets shall be listed in a separate `## Secrets` table, **not** mixed with general env vars. Each secret row shall include `Secret Name | Consumption Point (file:line) | Expected Format | Default Override Required | Hardcoded-Default Finding`. Any secret with a hardcoded default value shall carry a "⚠️ SECURITY FINDING" annotation. **No secret value shall be reproduced in the deliverable, even if hardcoded in source — only the file:line citation is recorded.**
- **Rule R7 — Validation execution requirement (Directive 4).** The deliverable shall be validated by executing the documented build and run instructions on a clean container or VM with only the OS-level prerequisites identified in the build instructions. No prior Odoo installation, no cached dependencies, no pre-existing database. Execution shall follow the documented sequence exactly: prerequisites → build → database provision → run with minimum required env vars and secrets set to valid test values → ready-state verification.
- **Rule R8 — Ready-state verification (Directive 4).** Ready state is achieved when (a) HTTP GET against the documented bind:port returns a response within 120 seconds of process start; (b) the longpolling/gevent worker (port 8072 by default) is also reachable; (c) database connection is established (visible in process logs or via successful login-page render). All three sub-conditions must be satisfied for the cycle to be declared successful.
- **Rule R9 — Divergence and correction (Directive 4).** If a documented step fails during validation, the failure shall be traced to the specific source file that produced the incorrect instruction; the instruction shall be corrected based on actual source-code behavior; and the build-run cycle shall be re-executed from step 1 of the validation sequence. Maximum 5 correction cycles. After 5 cycles, the Blitzy platform halts and reports.
- **Rule R10 — Halt-and-report triggers (Directive 4).** The Blitzy platform shall halt and report (rather than ship a partial deliverable) under either of two conditions: (a) the same step fails 3 consecutive times after correction attempts, OR (b) a required environment variable cannot be satisfied without consulting prohibited sources (`README`, `docs/`, `*.rst`). The halt report shall identify the specific source ambiguity that prevented progress.
- **Rule R11 — Validation evidence content (Directive 4).** The `## Validation Evidence` section appended to `BUILD_AND_RUN.md` shall contain: (a) exact OS image and version used (e.g., `ubuntu:24.04` with the `lsb_release -a` output captured); (b) full command transcript with timestamps (each command line prefixed with `date +%FT%T.%N`); (c) ready-state HTTP response status and latency for both the WSGI port and the gevent port; (d) process tree at ready state (output of `ps -ef --forest`); (e) the count of correction cycles required.
- **Rule R12 — Pass criteria (Directive 4).** The deliverable shall be considered passing only if (a) ready-state was achieved; (b) zero documentation steps required correction in the **final** cycle (i.e., the final cycle ran clean); (c) all environment variables and secrets used during execution match the documented table exactly. If the final cycle had any deviation from the documented instructions, the cycle does not count as passing and another cycle is required.
- **Rule R13 — Coverage gate (Directive 5).** Before delivery, the env-var scan shall be re-run and the result diffed against the env-var table. Zero env-var references in scanned source files may be absent from the table. Any miss fails the gate.
- **Rule R14 — Citation gate (Directive 5).** Before delivery, every build step, run step, environment variable entry, and secret entry shall carry a `[source: path/to/file:L<start>-L<end>]` citation. Entries without citations fail validation and are removed (or, if they cannot be removed, the deliverable fails the gate and is regenerated).
- **Rule R15 — Source restriction gate (Directive 5).** Before delivery, the deliverable shall be searched for the strings `README`, `CONTRIBUTING`, `INSTALL`, `docs/`, and `.rst`. Zero matches required. Any match fails the gate.
- **Rule R16 — Execution evidence gate (Directive 5).** Before delivery, the `## Validation Evidence` section shall be present and shall report a successful final cycle per Rule R12. Absence of the section, or evidence of a failed final cycle, fails the gate.
- **Rule R17 — Single-file deliverable (Directive 5).** The deliverable shall be exactly one file: `BUILD_AND_RUN.md` at repository root. No other file in the repository shall be modified, added, or deleted. The Blitzy platform shall verify this with `git diff --name-status` after the validation cycle.
- **Rule R18 — Highest-version selection (Setup protocol).** The runtime versions documented in Prerequisites shall be the **highest explicitly documented supported version** per the Setup protocol's logic: for ranges, use the upper bound; for `>=N` lower bounds, examine other files (CI configs, tox, etc.) for the highest tested version; for `<=N` upper bounds, use N. For Python: `MAX_PY_VERSION = (3, 13)` per `odoo/release.py:L40` selects 3.13. For PostgreSQL: `MIN_PG_VERSION = 13` per `odoo/release.py:L41` is a lower bound; the validation uses PostgreSQL 16 as the highest available in the Ubuntu 24.04 archive (the explicitly named target OS in `requirements.txt:L1-L2`).
- **Rule R19 — No prohibited-source recourse for ambiguity resolution.** When the source code is ambiguous about a behavior or a required env var, the Blitzy platform shall **not** consult `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/`, or `*.rst` files to resolve the ambiguity. Instead, the Blitzy platform shall either (a) deepen the source-code investigation by reading additional permitted files, or (b) trigger the halt-and-report path under Rule R10(b).
- **Rule R20 — Postgres user constraint preservation.** The Run section shall explicitly document that `db_user='postgres'` (or `PGUSER=postgres`) causes the server to exit at startup per `odoo/cli/server.py:L42-L44`, and the validation cycle shall use a non-`postgres` PostgreSQL role (typically `odoo`).
- **Rule R21 — Master password security finding preservation.** The Secrets table shall flag `admin_passwd` with a "⚠️ SECURITY FINDING: hardcoded default — MUST be overridden in production" annotation citing `odoo/tools/config.py:L207`. The literal value `'admin'` shall **not** be reproduced; only the citation. The validation cycle shall override `admin_passwd` to a randomly generated test value, and the override mechanism shall be documented in the Run section.
- **Rule R22 — Default-port preservation.** The Run section shall document `--http-port=8069` (`odoo/tools/config.py:L257-L258`) and `--gevent-port=8072` (`odoo/tools/config.py:L259-L260`) as defaults. The validation cycle shall use these defaults to keep the deliverable's documented invocation as minimal as possible.
- **Rule R23 — Two-phase first-run.** The Run section shall document a two-phase first-run pattern: phase 1 = seed (`python -m odoo -d <db> -i base --without-demo=all --stop-after-init`), phase 2 = steady state (`python -m odoo -d <db> --http-interface 0.0.0.0 --http-port 8069`). The seed phase is required because `odoo/cli/server.py:L101-L113` only auto-creates the empty database; the `base` module must be installed via `-i base` before the server is functional.
- **Rule R24 — Configuration precedence documentation.** The Run section shall document the configuration precedence order from `odoo/tools/config.py:L164-L170` ChainMap: runtime → CLI → environment → config-file → built-in defaults. This ensures the reader knows that any CLI flag overrides any env var that overrides any config-file entry.
- **Rule R25 — Deterministic citation paths.** All citation paths shall be relative to the repository root (e.g., `odoo/tools/config.py`, not `/abs/path/odoo/tools/config.py` or `./odoo/tools/config.py`). This ensures citations remain valid under any checkout location.
- **Rule R26 — No literal secret values.** The Secrets table shall reproduce no literal secret value, even when it appears as a string literal in source. For example, `odoo/tools/config.py:L207` declares `my_default='admin'`; the deliverable cites the line but does not write the string `'admin'` in any cell. The Coverage and Citation gates do not require value reproduction; they only require citations.
- **Rule R27 — Exact deliverable filename and location.** The deliverable shall be named exactly `BUILD_AND_RUN.md` (uppercase B, U, I, L, D, underscore, A, N, D, underscore, R, U, N, then `.md`) and placed at the repository root, **not** in `docs/`, **not** in `setup/`, **not** elsewhere.


## 0.8 Special Instructions

### 0.8.1 Special Execution Instructions

The following procedural instructions govern how the Blitzy platform conducts the work, in addition to the rules in Section 0.7:

- **Documentation-only output.** The work product is a single markdown file. There is no code change, no test addition, no configuration update. Per the user's CRITICAL Directive 5 final clause, "Deliverable: single markdown file `BUILD_AND_RUN.md` at repository root. No other files modified."
- **No deployment.** The validation cycle runs locally in a clean container/VM and is captured as evidence. The Blitzy platform does not push the validation container, the test database, or any artifact to any external system.
- **No skipping of validation.** Even though the deliverable is documentation, validation by execution is mandatory per CRITICAL Directive 4. The Blitzy platform may **not** ship the deliverable based solely on source-derivation; the build-run-probe cycle must run end-to-end and yield the `## Validation Evidence` section.
- **Quiet execution preferred.** The validation transcript shall be captured non-interactively. All apt commands use `apt-get install -y --no-install-recommends` (matching the pattern in `setup/debinstall.sh:L9`). All `pip install` invocations use `--no-input`. All `add-apt-repository` invocations use `-y`. The `DEBIAN_FRONTEND=noninteractive` environment variable shall be exported once at the start of the validation cycle to suppress all package-manager prompts (matching `setup/debinstall.sh:L27`).
- **Timestamped command transcript.** Every command in the validation transcript shall be prefixed with `date +%FT%T.%N` (or equivalent ISO-8601 nanosecond timestamp) so the transcript is auditable for total elapsed time and per-step duration. The transcript is captured via `script -c "<command>" -q /dev/null` or by piping through `ts '%FT%T.%.S'` (from `moreutils`) to ensure timestamps appear in stdout.
- **HTTP probe with retry-until-ready.** The HTTP probe shall use `for i in $(seq 1 60); do curl -sf -o /dev/null -w "%{http_code} %{time_total}s\\n" http://localhost:8069/web/database/selector && break; sleep 2; done`. The 60-iteration × 2-second-sleep loop yields a maximum 120-second wait, matching the user's "within 120 seconds" requirement in CRITICAL Directive 4.
- **Process tree capture at ready state.** Immediately after the HTTP probe succeeds, the Blitzy platform runs `ps -ef --forest --sort=ppid > /tmp/pstree.txt` and embeds the file's contents (or a pruned, anonymized copy) in the `## Validation Evidence` section.
- **No interactive prompts during validation.** No `apt`, `pip`, `psql`, `createuser`, or other invocation may pause for user input during validation. PostgreSQL role creation uses `sudo -u postgres createuser --no-superuser --createdb --no-createrole --no-replication --pwprompt --` only when interactive password entry is acceptable; for fully non-interactive runs, `sudo -u postgres psql -c "CREATE ROLE odoo WITH LOGIN CREATEDB PASSWORD 'temppass';"` is used and the password is rotated at end-of-cycle.
- **Cleanup post-validation.** After the `## Validation Evidence` section is written, the Blitzy platform tears down the test database, removes the test pidfile, and deletes the test data directory to leave the validation host clean. No artifacts other than `BUILD_AND_RUN.md` remain in the repository.
- **No deployment to package indexes.** Even though `setup/package.py` defines Docker-based packaging for tarballs, deb, rpm, win, and iot images, the Blitzy platform does **not** invoke any of these packagers. They are documented (where relevant to env vars and secrets) but not exercised.
- **Approval/review requirements.** None specified. The deliverable is produced and committed without external review gates.
- **Code style.** The deliverable is markdown; no Python or shell code style applies. The deliverable shall use GitHub-Flavored Markdown (GFM): backtick-fenced code blocks with explicit language tags (e.g., ` ```bash`, ` ```ini`, ` ```python`, ` ```mermaid`); pipe-separated tables; level-2 headings (`##`) for the six sections; level-3 headings (`###`) for sub-sections within those.
- **Tone and voice.** The deliverable is reference documentation, not tutorial. It states facts and procedures with citations; it does not editorialize, motivate, or explain history. It uses active-voice imperatives for instructions ("Install Python 3.13", "Run `pip install -r requirements.txt`", "Verify the HTTP probe responds"), not passive voice and not optional-sounding hedges.

### 0.8.2 Constraints and Boundaries

- **Technical constraints.**
    - **Python 3.13** is the documented target. `MIN_PY_VERSION = (3, 10)` per `odoo/release.py:L39` and `MAX_PY_VERSION = (3, 13)` per `odoo/release.py:L40` define a closed range; per the Setup protocol's "Logic for highest explicitly documented version", the upper bound is selected. `requirements.txt:L1-L99` provides explicit pins for Python 3.13 (e.g., `Babel==2.17.0 ; python_version >= '3.13'`, `Pillow==11.1.0 ; python_version >= '3.13'`, `psycopg2==2.9.10 ; python_version >= '3.13'`), confirming feasibility.
    - **PostgreSQL ≥ 13** per `odoo/release.py:L41`. The validation uses PostgreSQL 16 (highest in the Ubuntu Noble archive); no upper bound is specified.
    - **Ubuntu 24.04 (Noble) or Debian 12 (Bookworm)** per `requirements.txt:L1-L2` ("officially supported versions of the following packages are their python3-* equivalent distributed in Ubuntu 24.04 and Debian 12"). The validation uses Ubuntu 24.04.
    - **Linux only**. The deliverable does not document Windows or macOS workflows. The validation runs only on Linux. Platform-conditional behavior in source (e.g., `pypiwin32 ; sys_platform == 'win32'`) is acknowledged in the env-var table where it surfaces but is not exercised.
    - **No internet access during validation execution** (apart from initial apt and pip downloads). Once installed, the Odoo server runs offline. The deliverable does not depend on outbound HTTP to any third-party service for ready-state.
    - **Default ports 8069 (HTTP) and 8072 (gevent longpolling)** per `odoo/tools/config.py:L257-L260`. The validation uses these defaults.
    - **No external proxy.** `--proxy-mode` (`odoo/tools/config.py:L263-L265`) is **not** enabled in the validation; it is documented as an option only. Enabling proxy-mode without a real reverse proxy would break the HTTP probe.
- **Process constraints.**
    - The Blitzy platform shall not modify any file other than `BUILD_AND_RUN.md`.
    - The Blitzy platform shall not commit, push, tag, or release any artifact.
    - The Blitzy platform shall not consult any prohibited source per Rule R2.
    - The Blitzy platform shall not open the `/app` folder or its subfolders. Only repository content under the inspected paths in Section 0.6.1 may be opened.
- **Output constraints.**
    - Single markdown file at repository root.
    - Six sections in fixed order: Prerequisites, Build, Run, Configuration File, Environment Variables (with sub-domains), Secrets, Validation Evidence.
    - Every claim source-cited per Rule R3.
    - No literal secret values per Rule R26.
    - GFM markdown formatting per Section 0.8.1.
- **Timeline constraints.**
    - The Blitzy platform proceeds without temporal scheduling. The work is iterative within a maximum of 5 correction cycles per Rule R9.
    - Per cycle, the build-run-probe sequence has an upper bound of approximately 30 minutes (10 min provision, 10 min build, 5 min run, 5 min probe and capture); the budget is exceeded only when a step fails and triggers correction.
- **Compatibility requirements.**
    - The deliverable's instructions shall be executable on a stock `ubuntu:24.04` Docker image with no pre-installed Odoo, no pre-existing database, and no cached pip/apt state.
    - The deliverable's `python -m odoo` invocations shall work both with and without environment variables set (with env vars present, the corresponding CLI flags are optional; without, the CLI flags are required).
    - The deliverable's `gunicorn odoo.http:root --pythonpath . -c setup/odoo-wsgi.example.py` alternative shall remain valid as long as `setup/odoo-wsgi.example.py:L13-L17` declares `application = odoo.http.root`.


## 0.9 References

### 0.9.1 Files and Folders Searched in the Repository

The following files and folders were inspected by the Blitzy platform during context gathering for this Agent Action Plan. Files marked PERMITTED are read inputs for derivation of `BUILD_AND_RUN.md`; files marked PROHIBITED are recorded only to confirm they are excluded from the deliverable; folders marked CATALOGUED are inspected at folder-summary level only.

#### 0.9.1.1 Repository Root

- `/` (root folder summary) — top-level project structure including `setup.py`, `setup.cfg`, `requirements.txt`, `ruff.toml`, `setup/`, `odoo/`, `addons/`, `debian/`, `.github/`, `doc/`, `LICENSE`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `.weblate.json` — CATALOGUED

#### 0.9.1.2 Permitted Source Files Read for Derivation

- `setup.py` — full read (lines 1–77) — Python package descriptor with `install_requires`, `python_requires`, `extras_require`, `tests_require`, `scripts`, `package_dir`, dynamic `exec(open('odoo/release.py'))` for version metadata
- `setup.cfg` — full read (lines 1–35) — setuptools `[install] optimize=1`, `[flake8]` configuration
- `requirements.txt` — full read (lines 1–99) — Python dependency pins with platform/Python-version conditional markers; comments cite Ubuntu 24.04 and Debian 12 as canonical OS targets
- `odoo/release.py` — full read (lines 1–42) — `version_info = (19, 0, 0, FINAL, 0, '')`, `MIN_PY_VERSION = (3, 10)`, `MAX_PY_VERSION = (3, 13)`, `MIN_PG_VERSION = 13`, `nt_service_name`
- `odoo/__main__.py` — full read (lines 1–3) — `from .cli.command import main; main()`
- `odoo/cli/server.py` — full read (lines 1–128) — `Server` command class, `check_root_user`, `check_postgres_user`, `report_configuration`, `setup_pid_file`, `main()` lifecycle with auto-DB-create loop and `server.start(preload=...)`
- `odoo/cli/command.py` — full read (lines 1–139) — `Command` base class, `commands` registry, `main()` dispatch, default-command resolution to `'server'`, `--addons-path=` early-parse hook
- `odoo/tools/config.py` — partial read (lines 1–700; sufficient to enumerate every option) — `configmanager`, `_OdooOption` class, `_FileOnlyOption`, `_PosixOnlyOption`, every `parser.add_option(...)` invocation in `_build_cli`, the auto-`env_name` generation rule, the precedence ChainMap
- `setup/debinstall.sh` — full read (lines 1–28) — apt extraction script with `DEBIAN_FRONTEND=noninteractive xargs apt-get install -y --no-install-recommends`, `id -u` privilege check, `-l/--list` dry-run mode, `-q/--quiet` mode
- `setup/odoo-wsgi.example.py` — full read (lines 1–48) — Gunicorn deployment template with `application = odoo.http.root`, `bind = '127.0.0.1:8069'`, `workers = 4`, `timeout = 240`, `max_requests = 2000`
- `setup/requirements-check.py` — partial read (lines 1–80) — cross-distro requirements validator; `SUPPORTED_FORMATS`, `PLATFORM_CODES`, `SPECIAL = {'pytz': 'tz', 'libsass': 'libsass-python'}` package-name mapping
- `debian/odoo.conf` — full read (lines 1–9) — INI template with `[options]` section, `db_host=False`, `db_port=False`, `db_user=odoo`, `db_password=False`, `default_productivity_apps=True`, commented `admin_passwd = admin` and `addons_path = /usr/lib/python3/dist-packages/odoo/addons` examples

#### 0.9.1.3 Permitted Source Files Inspected at Summary Level

- `setup/package.py` — file summary read — packaging orchestrator using Docker builders (`DockerTgz`, `DockerDeb`, `DockerRpm`, `DockerWine`, `DockerIot`); reads `GPGPASSPHRASE`/`GPGID` env vars at module level (build-time secrets only, not runtime)
- `odoo/http.py` — file summary read — WSGI `Application` (`root`), session/CSRF/CORS, `proxy_mode`, `x_sendfile`, GeoIP database loading, dispatcher classes
- `odoo/tools/appdirs.py` — file summary read — cross-platform `user_data_dir`, `site_data_dir`, `user_cache_dir`, `user_log_dir`; XDG variable handling on Unix, CSIDL on Windows, Library on macOS
- `SECURITY.md` — summary inspected once for catalog completeness, but **not** used for derivation; PROHIBITED for any citation in the deliverable
- `setup/debinstall.sh` summary verification (cross-checked against full read above)

#### 0.9.1.4 Folder Summaries Catalogued

- `odoo/` — folder summary read — core Python package: bootstrap, HTTP/WSGI, ORM, SQL/DB pool, logging, RPC, CLI, modules, tests, tools
- `odoo/cli/` — folder summary read — CLI command framework with subcommands (server, db, deploy, help, i18n, module, populate, scaffold, shell, start, cloc, neutralize, obfuscate, upgrade_code)
- `odoo/tools/` — folder summary read — utilities including `config.py`, `appdirs.py`, `cache.py`, `convert.py`, `safe_eval.py`, `image.py`, `pdf/`, `babel/`, `arabic_reshaper/`, `_vendor/`, `zeep/`, `data/`
- `odoo/service/` — folder summary read — RPC and process orchestration: `common.py`, `db.py`, `model.py`, `security.py`, `server.py`
- `odoo/modules/` — folder summary read — module discovery, manifest handling, dependency graph, lifecycle orchestration, migration, neutralization, registry shim
- `setup/` — folder summary read — packaging tools: `debinstall.sh`, `odoo-wsgi.example.py`, `package.py`, `requirements-check.py`, `win32/` (Windows installer assets)
- `debian/` — folder summary read — Debian packaging fragment containing only `odoo.conf` (no `debian/control` present in this repository copy)
- `.github/` — folder summary read — GitHub UI metadata only (`PULL_REQUEST_TEMPLATE.md`, `ISSUE_TEMPLATE/`); **no `workflows/` directory**, confirming no GitHub Actions CI is present
- `addons/` — folder summary read — 300+ addon modules following the `__manifest__.py` pattern; addons-path documentation only, individual addons not read

#### 0.9.1.5 Files Confirmed Absent (Mentioned in User's PERMITTED List but Not Present)

The Blitzy platform performed targeted searches and confirmed the following PERMITTED-list artifacts are not present in this repository copy. Their absence is recorded so the deliverable does not erroneously cite them:

- `Dockerfile*` (root-level)
- `docker-compose*.yml`
- `pyproject.toml`
- `Makefile`
- `package.json`
- `MANIFEST.in`
- `.github/workflows/*.yml`
- `.gitlab-ci.yml`
- `odoo-bin` (root-level)
- `setup/odoo` (referenced by `setup.py:L23` `scripts=['setup/odoo']` but not present in `setup/` directory listing)
- `debian/control` (referenced by `setup/debinstall.sh:L23` but not present in `debian/` directory listing)

#### 0.9.1.6 Files Confirmed Present but PROHIBITED for Derivation

The following files exist in the repository and are recorded here only to confirm they were **not** consulted for derivation; they shall **not** be cited or referenced in `BUILD_AND_RUN.md`:

- `README.md` — PROHIBITED (human-authored prose)
- `CONTRIBUTING.md` — PROHIBITED (human-authored prose)
- `SECURITY.md` — PROHIBITED (human-authored prose)
- `LICENSE` — Not used for build/run derivation (legal text only)
- `doc/` — PROHIBITED (`doc/cla/` contains CLA templates; PROHIBITED at the folder level)
- `.weblate.json` — Permitted but not relevant to build/run derivation

### 0.9.2 User-Provided Attachments

The user attached **0** files to this project. The user's environment-files folder is `/tmp/environments_files`, which contains no attachments per the user's "No attachments found for this project" notice. No attachments are documented or referenced in the deliverable.

### 0.9.3 User-Provided Figma Frames

No Figma frames or screens were provided. This task has no UI dimension and no design-system component; the deliverable is a markdown documentation file.

### 0.9.4 User-Provided Environment and Secret Names

The user-supplied environment variables list is empty (`[]`). The user-supplied secrets list is empty (`[]`). No pre-existing env vars or secrets are pre-applied to the validation environment beyond what the Blitzy platform itself sets during the validation cycle. The deliverable's Environment Variables and Secrets tables are derived **entirely** from source-code references per CRITICAL Directives 2 and 3.

### 0.9.5 User-Provided Implementation Rules

The user-supplied rules list is empty (`[]`). All rules in Section 0.7 are derived from the user's CRITICAL Directives and from the Setup protocol; none are user-supplied custom rules.

### 0.9.6 Web Searches Performed

Per Rules R1 and R19, web search is restricted to non-Odoo-specific OS-toolchain semantics. The Blitzy platform performs a minimal set of confirmatory searches (each ≤1 query) only when needed to materialize the OS-prerequisites apt-package list, never to look up Odoo behavior. Searches actually performed during the writing of this Agent Action Plan: **0** (the source files alone provided sufficient context for the plan; the deliverable's authoring may use up to 3 confirmatory searches per Section 0.2.2). All web searches, if any, are recorded in the `## Validation Evidence` section of the final `BUILD_AND_RUN.md`, not here.

### 0.9.7 Citation Format Reference

The deliverable shall use exactly the following citation format, as illustrated by these examples drawn from this Agent Action Plan:

- Single-section citation: `[source: odoo/release.py:L40-L40]` (or compactly, `[source: odoo/release.py:L40]` — but the explicit start-end form is preferred for grep-ability)
- Multi-line range: `[source: odoo/cli/server.py:L37-L44]`
- Multiple discontiguous citations on one claim: `[source: odoo/tools/config.py:L255-L260]` `[source: odoo/cli/server.py:L101-L113]` (two separate `[source: ...]` tags adjacent)

The `[source: ...]` tag is the only citation form used; no footnote, endnote, hyperlink, or alternative scheme is permitted in the deliverable.


