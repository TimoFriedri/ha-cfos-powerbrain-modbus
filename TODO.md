# To do

## Get into the Marketplace catalog

The Marketplace (Home Assistant 2026.11, **Settings → Marketplace**) shows the
catalog in [hacs/default](https://github.com/hacs/default) to everyone. Until
this repository is in it, users add it from the README's Marketplace button as
a custom repository, which needs the Marketplace's GitHub connection. See
[Get into the catalog](https://contributors.home-assistant.io/marketplace/guides/catalog/).

- [ ] Update the repository description on GitHub: it still says
      "Installable via HACS" and leaves out the Charging Manager.
- [ ] Publish 0.6.0 as a full GitHub release, after CI (with the HACS and
      hassfest jobs) passed on `main`.
- [ ] Open the pull request to hacs/default from your own account: add
      `TimoFriedri/ha-cfos-powerbrain-modbus` to the `integration` file, in
      alphabetical order, from a branch of a fork. Fill in its template: the
      checklist, and links to the 0.6.0 release, a passing run of the HACS job
      and a passing run of the hassfest job.
- [ ] Wait for the review; it can take months.

## Icon in the Marketplace

The icon ships in `custom_components/cfos_powerbrain/brand/`. Home Assistant
shows it once the integration is installed, and so does the Marketplace since
2026.11. Before installation, the Marketplace only shows icons of
repositories in the catalog: the brands site picks them up from their latest
release.

- [ ] Check the icon of the installed integration in the Marketplace.
- [ ] After the catalog took the repository in, check the icon before
      installation.

## Home Assistant 2026.11 follow-up

A second pull request, once `pytest-homeassistant-custom-component` is
published for Home Assistant 2026.11; the one for 2026.10.4 does not run on it.

- [ ] Move the `dev` pins in `pyproject.toml` to Home Assistant 2026.11, with
      the Modbus packages it ships (`modbus-connection[tmodbus]==4.12.7`,
      `tmodbus==1.1.0`), and drop the Pillow override: 2026.11 pins Pillow
      13.0.0 itself.
- [ ] hassfest is split into `packages/hassfest` (`hassfest.model`) and
      `script/hassfest` since 2026.11: adapt `script/check_quality_scale.py`,
      the quality scale job's sparse checkout, and the local instructions in
      `AGENTS.md`.
- [ ] The library job's oldest `modbus-connection` becomes 4.12.7.
- [ ] Register the wallbox with `async_get_or_create_from_info` instead of
      unpacking its `DeviceInfo`, which only still works through a
      compatibility layer.
- [ ] Let `async_setup_entry`, `async_unload_entry` and `async_migrate_entry`
      return `None`, with `async_unload_platforms_or_raise`.
- [ ] Show the Charging Manager port and Modbus ID in the setup and options
      forms only while the Charging Manager is switched on (`visible`).

## Before Home Assistant 2027.11

- [ ] Implement `async_entity_id_changed` in the sensors that override
      `async_added_to_hass`, so a renamed entity ID is updated in place.

## Features

- [ ] Read the wallboxes and meters the Charging Manager manages, from its
      SunSpec server under Modbus ID + 1.
