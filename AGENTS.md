# Working on this repository

How to develop this repository, for humans and AI agents. What it does for
users: [README](README.md).

## What this is

- Home Assistant custom integration `cfos_powerbrain` for the cFos Power Brain
  Wallbox and the cFos Charging Manager, **Modbus TCP only** (no HTTP API).
- Installed through the Marketplace; needs Home Assistant **2026.11.0**
  (`hacs.json`).
- Connections come from the `modbus` integration (`modbus.async_get_unit`;
  `async_get_temporary_unit` in the config flow): `modbus` is a manifest
  dependency, there are no requirements.
- Product names in every language: **cFos Power Brain Wallbox**, **cFos Power
  Brain Controller**, **cFos Charging Manager**. The integration is **cFos
  Power Brain Wallbox (Modbus)**; keep the "(Modbus)".

## Layout

| Path | Contents |
| --- | --- |
| `custom_components/cfos_powerbrain/` | Config flow, coordinators, entity platforms, action, diagnostics |
| `custom_components/cfos_powerbrain/cfos_modbus/` | Vendored device library on `modbus-connection`, **no Home Assistant imports** |
| `tests/lib/` | Library tests, without Home Assistant |
| `tests/integration/` | Integration tests, only the Modbus transport mocked |
| `tests/registers.py` | Register images of wallbox, S0 meters, Charging Manager; write recorder |
| `script/dump_registers.py` | Reads a real device without Home Assistant, for bug reports |

## Set up and check

- [uv](https://docs.astral.sh/uv/) in the version of `required-version`
  (`pyproject.toml`), as in CI.
- `.python-version`: Python 3.14, as Home Assistant. Otherwise uv picks a newer
  Python without wheels for many packages.
- The `dev` group pins Home Assistant; `uv.lock` pins the rest. After changing
  a pin: `uv lock`, commit both files.

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
```

All four pass before every commit. Coverage and quality scale locally, with
the Home Assistant version of `pyproject.toml` as the branch:

```bash
uv run pytest --cov --cov-report=json && uv run python script/check_coverage.py
git clone --depth 1 --branch 2026.11.0 --filter=blob:none --sparse \
  https://github.com/home-assistant/core ../home-assistant-core
git -C ../home-assistant-core sparse-checkout set script/hassfest packages/hassfest
uv run python script/check_quality_scale.py ../home-assistant-core
```

## CI

`main` is protected; a pull request merges once both are green:

- **CodeQL**: GitHub's default setup (Python, GitHub Actions), configured in
  the repository settings. No CodeQL workflow of our own: it would conflict.
- **CI passed** (`.github/workflows/ci.yml`): needs every job.

| Job | Checks |
| --- | --- |
| Lint and type-check | ruff, ruff format, mypy |
| Integration tests | pytest; every module above 95 % coverage, `config_flow.py` 100 % (`script/check_coverage.py`) |
| Device library | library tests on the oldest and newest supported `modbus-connection` |
| Quality scale | `script/check_quality_scale.py`: target rules done or exempt, hassfest's rule checks |
| Version | `script/check_version.py`, see [releases](#commits-and-releases) |
| Hassfest, HACS | Home Assistant's and HACS' validation |

- The `changes` job runs each job only when its files change: Markdown alone
  runs none, and **CI passed** still reports.
- Changes to `ci.yml`, scheduled and manual runs run every job.
- A job that starts to depend on a new file: add it to the job's filter.

## Code conventions

- **Style:** ruff (rules, import sections in `pyproject.toml`), mypy strict.
  Docstrings everywhere; comments say why. Follow the surrounding code.
- **Library first:** registers, decoding and validation in `cfos_modbus`; the
  integration only maps components to entities. Read documented registers
  only.
- **Entities:** entity descriptions; `value_fn` and `exists_fn` get the
  component, the base entity handles a missing one. Unique IDs
  `{serial}_{key}` (Charging Manager and S0 meters add a prefix) never change.
- **Devices:** wallbox main device; S0 meters its child devices (inputs of
  its controller); Charging Manager a device next to it.
- **Volatile or flash:** values stored in flash get `flash=True` (unchanged
  values are not written), `EntityCategory.CONFIG`, disabled by default.
  Volatile values may be written freely. The README tables say which is which.
- **Translations:** `translations/en.json` is the source (no `strings.json`
  in custom integrations); `de.json` kept in sync. User-facing errors use
  translation keys.
- **Config entry migrations:** a change to what an entry stores or to unique
  IDs migrates existing entries in `async_migrate_entry`. `MINOR_VERSION` for
  a compatible change, `VERSION` for an incompatible one; test from each older
  version. Breaking changes go into the README.
- **Docs:** new entities into the README tables (by register), new options
  into the configuration section.

## Quality scale: Silver plus strict-typing

`quality_scale.yaml` records every rule. Silver (with Bronze) and Platinum's
strict-typing stay `done` or `exempt` with a reason; other rules stay `todo`
until reviewed.

- Setup only via the config flow; it tests the connection first and never
  adds a controller twice.
- Every config flow field has a `data_description`; the README covers every
  setup field and option.
- Entities: unique IDs, `has_entity_name`. Runtime state in
  `entry.runtime_data`, typed `CfosConfigEntry`.
- Setup raises `ConfigEntryNotReady` or `ConfigEntryError` when the wallbox
  is unusable. S0 meters and Charging Manager never block it.
- Entities are **unavailable** while their data cannot be read; no stale
  values.
- Unavailability and recovery are logged **once** each: coordinators do so
  on `UpdateFailed`; anything extra at info level.
- Actions registered in `async_setup`. Wrong call: `ServiceValidationError`;
  failed write (action or entity): `HomeAssistantError`.
- `PARALLEL_UPDATES` in every platform: 0 read-only, 1 writing.
- **Every module**, library included, above **95 %** coverage;
  `config_flow.py` 100 %, each error case followed by a successful retry.
- mypy strict plus Home Assistant core's checks (`pyproject.toml`);
  `@override` directly above every overriding `def`.
- README: description, installation, removal, every action with its fields.
  Brand images in `brand/`.

## Commits and releases

- [Conventional Commits](https://www.conventionalcommits.org):
  `type(scope): summary`, e.g. `feat: ask for the Charging Manager during
  setup`.
  - Types: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci`,
    `chore`.
  - Scopes: `config-flow`, `lib`, `sensor`, `switch`, `number`, ….
  - Imperative, lower case, no full stop.
  - Breaking: `!` after the type and a `BREAKING CHANGE:` footer.
- Every commit passes the checks. Push to a branch, never `main`; no pull
  requests, tags or releases unless asked.
- Release: bump `version` in `manifest.json`; the maintainer publishes a full
  GitHub release `X.Y.Z` (no `v`) with notes, which the Marketplace shows on
  the update entity. CI enforces:
  - `custom_components/` changed since the latest release tag → the manifest
    version is above it;
  - a pushed release tag equals the manifest version (`release.yml`).
- Manifest categories (one to three): `energy.ev_charging`,
  `energy.meters_monitoring`. The HACS action fails on unknown ones.
