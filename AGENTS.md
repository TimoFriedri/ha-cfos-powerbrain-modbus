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

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt   # pins the Home Assistant version tested against
ruff check . && ruff format --check .
mypy
pytest
```

All four must pass before a commit. CI (`.github/workflows/`) runs them,
the library tests on the oldest and newest supported `modbus-connection`,
hassfest and the HACS validation.

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

## Integration Quality Scale: target Bronze

The current target is the **Bronze** tier. `quality_scale.yaml` records each
rule; every Bronze rule must stay `done` or `exempt` with a reason. Higher
tiers are `todo` until reviewed; do not mark them `done` without checking the
rule. In practice, Bronze here means:

- Setup only through the config flow, which tests the connection before it
  creates an entry and never configures the same controller twice.
- `config_flow.py` keeps **100 % test coverage**, and every error case is
  followed by a successful retry.
- Every config flow field has a `data_description`.
- Entities have unique IDs and `has_entity_name`; runtime state lives in
  `entry.runtime_data`.
- Setup fails with `ConfigEntryNotReady` or `ConfigEntryError` when the
  wallbox cannot be used. The optional devices (S0 meters, Charging Manager)
  must not block it.
- Actions are registered in `async_setup`; a bad call raises
  `ServiceValidationError`.
- The README covers the high-level description, installation, removal and
  every action with its fields.
- Brand images ship in `brand/`.

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
- Each commit passes the checks on its own. Do not create pull requests,
  tags or releases unless asked.
- Releases: bump `version` in `manifest.json`, then the maintainer tags
  `X.Y.Z` (no `v` prefix) on GitHub and writes the release notes. HACS offers
  the GitHub releases.
- The manifest `categories` are held back until hassfest accepts them
  (expected with Home Assistant 2026.11); see [TODO.md](TODO.md).
