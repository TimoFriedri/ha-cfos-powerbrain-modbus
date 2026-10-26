# Working on this repository

Guidance for anyone changing this repository, human or AI agent. The
[README](README.md) describes what the integration does for users; this file
covers how to develop it.

## What this is

A Home Assistant custom integration (domain `cfos_powerbrain`, installed
through HACS) for the cFos Power Brain Wallbox and the cFos Charging Manager,
over **Modbus TCP only**. The HTTP API is out of scope.

- It requires Home Assistant **2026.10.0** or newer (`hacs.json`).
- Connections come from Home Assistant's `modbus` integration
  (`modbus.async_get_unit`, `async_get_temporary_unit` in the config flow), so
  the manifest lists `modbus` as a dependency and has no requirements of its
  own.
- Use cFos' product names: **cFos Power Brain Wallbox**, **cFos Power Brain
  Controller**, **cFos Charging Manager**, in every language. The integration
  is named **cFos Power Brain Wallbox (Modbus)**; keep the "(Modbus)".

## Layout

| Path | Contents |
| --- | --- |
| `custom_components/cfos_powerbrain/` | The integration: config flow, coordinators, entity platforms, action, diagnostics |
| `custom_components/cfos_powerbrain/cfos_modbus/` | Vendored device library on `modbus-connection`, **no Home Assistant imports** |
| `tests/lib/` | Library tests; they run without Home Assistant |
| `tests/integration/` | Integration tests against Home Assistant, only the Modbus transport mocked |
| `tests/registers.py` | Register images of the wallbox, S0 meters and Charging Manager, and a write recorder |
| `script/dump_registers.py` | Reads a real device without Home Assistant, for bug reports |

## Set up and check

The development setup uses [uv](https://docs.astral.sh/uv/), in the version
`required-version` in `pyproject.toml` names; CI installs the same one.
`.python-version` pins Python to the minor version that Home Assistant
targets, 3.14. Without it, uv would pick the newest Python allowed, for which
many packages have no wheels yet. The `dev` dependency group pins the Home
Assistant version tested against; `uv.lock` pins everything else.

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
```

All four must pass before a commit. Change a pin in `pyproject.toml`, then
run `uv lock` and commit both files.

`main` is protected: changes go through a pull request, which merges only
once two checks are green:

- **CodeQL**: GitHub's code scanning (default setup, Python and GitHub
  Actions) analyses every pull request. Configured in the repository settings,
  not in a workflow; a CodeQL workflow of our own would conflict with it.
- **CI passed** of `.github/workflows/ci.yml`, which needs every job of the
  workflow:

| Job | Checks |
| --- | --- |
| Lint and type-check | ruff, ruff format, `strings.json` equal to `translations/en.json`, mypy |
| Integration tests | pytest; every module above 95 % coverage, `config_flow.py` at 100 % (`script/check_coverage.py`) |
| Device library | the library tests on the oldest and newest supported `modbus-connection` |
| Quality scale | `script/check_quality_scale.py`: the target rules are done or exempt, and hassfest's own rule checks pass |
| Version | `script/check_version.py`: see releases below |
| Hassfest, HACS | Home Assistant's and HACS' validation |

Each job runs only when files it checks change; the `changes` job at the top
of `ci.yml` decides. A pull request that touches only Markdown runs none of
them, and **CI passed** still reports. A change to `ci.yml` itself, and
scheduled and manual runs, run every job. When a job starts to depend on
another file, add that file to the job's filter.

To run the coverage and quality scale checks locally:

```bash
uv run pytest --cov --cov-report=json && uv run python script/check_coverage.py
git clone --depth 1 --branch 2026.10.2 --filter=blob:none --sparse \
  https://github.com/home-assistant/core ../home-assistant-core
git -C ../home-assistant-core sparse-checkout set script/hassfest
uv run python script/check_quality_scale.py ../home-assistant-core
```

Use the Home Assistant version pinned in `pyproject.toml` as the branch.

## Code conventions

- **Style:** ruff (rules and import sections in `pyproject.toml`) and mypy
  `strict`. Every module, class and function has a docstring. Comments say
  why, not what. Match the surrounding code rather than introducing new
  patterns.
- **Device library first:** registers, decoding and value validation belong in
  `cfos_modbus`; the integration only maps components to entities. Read only
  documented register ranges.
- **Entities:** describe them with entity descriptions. `value_fn` and
  `exists_fn` receive the component; the base entity handles a missing one.
  Unique IDs are `{serial}_{key}` (the Charging Manager and S0 meters add
  their own prefix) and must never change.
- **Volatile or flash:** writable values the device stores in flash get
  `flash=True` (unchanged values are not written), `EntityCategory.CONFIG`
  and are disabled by default. Volatile values may be written as often as
  needed. The README tables state which is which.
- **Translations:** `strings.json` and `translations/en.json` are identical;
  `translations/de.json` is kept in sync. Errors raised to the user use
  translation keys.
- **Config entry migrations:** when a change alters what an existing entry
  stores (data, options) or how its entities are identified (unique IDs),
  migrate existing entries in `async_migrate_entry` instead of asking users to
  set the integration up again. Bump the config flow's `MINOR_VERSION` for a
  compatible change and `VERSION` for an incompatible one, and test the
  migration from each older version. 0.3.0 skipped this once, during early
  development. Breaking changes are documented in the README.
- **Keep the docs current:** a new entity goes into the README feature tables
  (ordered by register), a new option into the configuration section.

## Integration Quality Scale: target Silver

The current target is the **Silver** tier (which includes Bronze), plus
Platinum's **strict-typing** rule. `quality_scale.yaml` records each rule;
every rule of these must stay `done` or `exempt` with a reason. The other
rules of higher tiers are `todo` until reviewed; do not mark them `done`
without checking the rule. In practice this means:

- Setup only through the config flow, which tests the connection before it
  creates an entry and never configures the same controller twice.
- Every config flow field has a `data_description`; the README describes
  every setup field and option.
- Entities have unique IDs and `has_entity_name`; runtime state lives in
  `entry.runtime_data`, typed as `CfosConfigEntry`.
- Setup fails with `ConfigEntryNotReady` or `ConfigEntryError` when the
  wallbox cannot be used. The optional devices (S0 meters, Charging Manager)
  must not block it.
- Entities are **unavailable** while their data cannot be read; never show a
  stale value as current.
- Unavailability is logged **once**, and so is the recovery. Coordinators do
  this themselves when the poll raises `UpdateFailed`; anything logged on top
  is at info level.
- Actions are registered in `async_setup`. A wrong call raises
  `ServiceValidationError`, a failed write `HomeAssistantError`; entity
  writes raise `HomeAssistantError` too.
- Every platform sets `PARALLEL_UPDATES`: 0 for read-only ones, 1 for those
  that write.
- **Every module**, the device library included, keeps **above 95 % test
  coverage**; `config_flow.py` stays at 100 %, with every error case
  followed by a successful retry.
- mypy runs strict plus the checks Home Assistant core adds
  (`pyproject.toml`). Every method that overrides one carries `@override`
  directly above the `def`.
- The README covers the high-level description, installation, removal and
  every action with its fields. Brand images ship in `brand/`.

## Commits and releases

- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org):
  `type(scope): summary`, e.g. `feat: ask for the Charging Manager during setup`
  or `refactor(config-flow): share fields and probe helpers`.
  - Types: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci`,
    `chore`.
  - Common scopes: `config-flow`, `lib`, `sensor`, `switch`, `number`.
  - The summary is imperative and lower case, with no full stop.
  - Mark a breaking change with `!` after the type, e.g.
    `feat!: …`, and a `BREAKING CHANGE:` footer.
- Each commit passes the checks on its own. Push changes to a branch, not
  to `main`; do not create pull requests, tags or releases unless asked.
- Releases: bump `version` in `manifest.json`, then the maintainer tags
  `X.Y.Z` (no `v` prefix) on GitHub and writes the release notes. HACS offers
  the GitHub releases. CI enforces both ends:
  - once `custom_components/` changed since the latest release tag, the
    version in `manifest.json` must be above that tag, so the first such pull
    request after a release bumps it;
  - a pushed release tag must equal the version in `manifest.json`
    (`.github/workflows/release.yml`).
- The manifest `categories` are held back until hassfest accepts them
  (expected with Home Assistant 2026.11); see [TODO.md](TODO.md).
