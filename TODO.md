# To do

## Marketplace catalog

Until the repository is in [hacs/default](https://github.com/hacs/default),
users add it as a custom repository
([guide](https://contributors.home-assistant.io/marketplace/guides/catalog/)).

- [ ] Publish 0.6.0 as a full GitHub release once CI passed on `main`.
- [ ] Open the pull request to hacs/default from a fork: add
      `TimoFriedri/ha-cfos-powerbrain-modbus` to `integration`, alphabetically.
      Fill in its template: checklist, links to the 0.6.0 release and to
      passing HACS and hassfest runs.
- [ ] Wait for the review; it can take months.

## Marketplace icon

The icon ships in `custom_components/cfos_powerbrain/brand/`. The Marketplace
shows it after installation; before installation, only for catalog
repositories.

- [ ] Check the icon of the installed integration.
- [ ] Once in the catalog, check the icon before installation.

## Before Home Assistant 2027.11

- [ ] Implement `async_entity_id_changed` in the sensors that override
      `async_added_to_hass`.

## Features

- [ ] Read the wallboxes and meters the Charging Manager manages (Modbus ID
      + 1).
