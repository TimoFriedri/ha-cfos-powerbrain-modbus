# To do

## Marketplace catalog

Until the repository is in [hacs/default](https://github.com/hacs/default),
users add it as a custom repository
([guide](https://contributors.home-assistant.io/marketplace/guides/catalog/)).

- [ ] Wait for the review of
      [hacs/default#13875](https://github.com/hacs/default/pull/13875); it can
      take months. Keep "Allow edits by maintainers" on.
- [ ] Once in the catalog, check the icon before installation. The installed
      integration already shows it (`brand/`).

## Before Home Assistant 2027.11

- [ ] Implement `async_entity_id_changed` in the sensors that override
      `async_added_to_hass`.

## Features

- [ ] Read the wallboxes and meters the Charging Manager manages (Modbus ID
      + 1).
