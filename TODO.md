# To do

## Marketplace catalog

Until the repository is in [hacs/default](https://github.com/hacs/default),
users add it as a custom repository
([guide](https://contributors.home-assistant.io/marketplace/guides/catalog/)).

- [ ] Open the pull request to hacs/default from your account, with "Allow
      edits by maintainers" on: add `TimoFriedri/ha-cfos-powerbrain-modbus` to
      `integration`, alphabetically. Fill in its template: checklist, links to
      the 0.6.0 release and to passing HACS and hassfest runs.
- [ ] Wait for the review; it can take months.
- [ ] Once in the catalog, check the icon before installation. The installed
      integration already shows it (`brand/`).

## Before Home Assistant 2027.11

- [ ] Implement `async_entity_id_changed` in the sensors that override
      `async_added_to_hass`.

## Features

- [ ] Read the wallboxes and meters the Charging Manager manages (Modbus ID
      + 1).
