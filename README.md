> [!IMPORTANT]
> Independent community integration, not developed, endorsed or supported by
> cFos Software GmbH. Report problems [here][issues], not to cFos support.

# cFos Power Brain Wallbox (Modbus) for Home Assistant

[![CI][ci-badge]][ci]
[![Open your Home Assistant instance and open a repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=TimoFriedri&repository=ha-cfos-powerbrain-modbus&category=integration)

Monitors and controls a **cFos Power Brain Wallbox**, or a wallbox built
around the **cFos Power Brain Controller**, and its built-in **cFos Charging
Manager** (load management, solar surplus charging, charging rules).

- Modbus TCP only, over Home Assistant's shared Modbus connections
  ([`modbus.async_get_unit`][ha-modbus]): other integrations can use the same
  wallbox.
- Set up in the UI; no YAML.

## Requirements

- Home Assistant **2026.11.0** or newer.
- The wallbox reachable on Modbus TCP: port 4701, and 4702 and 4703 for the S0
  meters.
- A fixed IP address for the wallbox (e.g. a DHCP reservation);
  **Reconfigure** updates a changed one.
- For the Charging Manager: its SunSpec server switched on, see
  [below](#charging-manager-setup).

## Installation

**Marketplace** (**Settings → Marketplace**):

1. Open the integration with the Marketplace button above. Until it is in the
   Marketplace catalog, the Marketplace adds it as a custom repository first,
   which needs its GitHub connection. Or add
   `https://github.com/TimoFriedri/ha-cfos-powerbrain-modbus` as a custom
   repository of the type **Integration**.
2. Install **cFos Power Brain Wallbox (Modbus)**; it loads without a restart.

**Manual:** copy `custom_components/cfos_powerbrain` into the
`custom_components` folder of your configuration and restart.

## Configuration

**Settings → Devices & services → Add integration → cFos Power Brain Wallbox
(Modbus)**, or:
[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=cfos_powerbrain)

| Setup field | Default | |
| --- | --- | --- |
| Host | | IP address or host name of the wallbox |
| Port | 4701 | Modbus TCP port of the charging station |
| Modbus slave ID | 1 | Slave ID of the charging station |
| Polling interval | 10 s | Seconds between reads of the live values, 1–30 |
| Charging Manager | off | Adds the Charging Manager as its own device |
| Charging Manager port | 502 | Port of its SunSpec server; shown while the Charging Manager is on |
| Charging Manager Modbus ID | 1 | Modbus ID of its SunSpec server; shown while the Charging Manager is on |

- Setup checks the vendor ID and serial number, and that the Charging
  Manager's SunSpec server answers when it is on.
- **Reconfigure** changes host, port and slave ID.
- **Options** (gear on the entry): polling interval; **S0 meters** 1 and 2 as
  devices below the wallbox; the Charging Manager fields above. Settings like
  the fail-safe are read every 5 minutes.
- Runs side by side with the HTTP-API-based
  [`powerbrain` integration][rest-integration] (another domain).

### Charging Manager setup

1. In the Charging Manager configuration, under **SunSpec address settings**,
   set a TCP port (502 on the cFos Power Brain Wallbox) and a Modbus ID. This
   switches its SunSpec server on.
2. Switch on **Charging Manager** in the setup or the options, with the same
   port and Modbus ID.

- It appears as the device *cFos Charging Manager* next to the wallbox.
- If its server does not answer at startup, the wallbox still sets up; the
  Charging Manager's entities follow once it answers.
- The wallboxes and meters it manages (Modbus ID + 1) are not read yet.

## Entities

**Writes:** *volatile* values may be written as often as needed; *flash*
values wear the flash memory, see [Writing values](#writing-values).

### Wallbox

Modbus slave ID 1, port 4701; per cFos'
[register documentation][cfos-registers].

| Register | Entity | Type | Writes | Notes |
| --- | --- | --- | --- | --- |
| 8058 | Total energy | sensor | read-only | with a meter (8112) |
| 8058, 8092 | Session energy | sensor, derived | read-only | since plug-in; kept until the next session |
| 8062 | Power | sensor | read-only | with a meter (8112) |
| 8064–8069 | Current L1, L2, L3 | sensor | read-only | with a meter (8112) |
| 8064–8069 | Active phases | sensor, derived | read-only | phases carrying at least 1 A |
| 8080 | Default cable current override | config, disabled | **flash** | applied after a reboot |
| 8081 | Default charging current limit | config, disabled | **flash** | applied after a reboot |
| 8082 | Default charging enabled | config, disabled | **flash** | applied after a reboot |
| 8083 | Fail-safe timeout | config, disabled | **flash** | see [fail-safe](#modbus-fail-safe) |
| 8085 | Fail-safe current | config, disabled | **flash** | see [fail-safe](#modbus-fail-safe) |
| 8086 | Wake up vehicle | button | volatile | interrupts the control pilot for 5 s |
| 8087 | Phase mode (1 / 3 phases) | select | volatile | if phase switching is allowed (8113 bit 8) |
| 8088 | Relay 2 | switch | volatile | if a second relay is fitted (8113 bits 9–10) |
| 8090 | Cable current rating | diagnostic | read-only | |
| 8091 | Cable current override | config, disabled | volatile | |
| 8092 | Charging state | sensor (enum) | read-only | waiting, vehicle connected, charging, charging (ventilation), no power, error, DC sensor error |
| 8092 | Vehicle connected, Charging, Problem | binary sensor, derived | read-only | from the charging state |
| 8093 | Charging current limit | number | volatile | 6–32 A in 0.1 A steps |
| 8094 | Charging enabled | switch | volatile | |
| 8095 | Signaled charging current | sensor | read-only | current signaled to the vehicle |
| 8096 | Last RFID | diagnostic, disabled | read-only | |
| 8113 | Phase switching allowed | diagnostic | read-only | |
| 8120 | Restarts | diagnostic, disabled | read-only | |
| 8122 | Controller temperature | diagnostic | read-only | controller Rev. 3.0 and later |

- Energy totals: unavailable while the wallbox cannot be read; 0 Wh after a
  controller restart reads as unknown; a reading just below the last one is
  ignored.

### S0 meters

Optional; slave IDs 2 and 3, ports 4702 and 4703; devices below the wallbox.

- Power, total energy, currents L1–L3: read-only.
- Disabled by default: pulse counter, time between pulses (read-only); pulses
  per kWh, nominal voltages (**flash**); reset energy and reset pulses buttons
  (**flash**).

### Charging Manager

Optional; its own device, through its SunSpec server. Register addresses can
change between firmware versions, so the integration scans the SunSpec model
chain from 40000 at startup, finds each value by model and offset, and
rescans when the models move. *Register* shows the address on current
firmware.

| Register | Model, offset | Entity | Type | Writes | Notes |
| --- | --- | --- | --- | --- | --- |
| 40098 | 213 (1st), 28 | Grid power | sensor | read-only | grid consumption |
| 40074–40079 | 213 (1st), 4–8 | Grid current L1, L2, L3 | sensor, disabled | read-only | |
| 40130, 40138 | 213 (1st), 60, 68 | Grid energy exported, imported | sensor, disabled | read-only | |
| 40224 | 213 (2nd), 28 | Consumers power | sensor | read-only | total of the consumers |
| 40350 | 213 (3rd), 28 | Generators power | sensor | read-only | total of the generators |
| 40476 | 213 (4th), 28 | PV surplus | sensor | read-only | |
| 40602 | 213 (5th), 28 | Wallbox power used | sensor | read-only | |
| 40728 | 213 (6th), 28 | Wallbox power available | sensor | read-only | |
| 40704–40709 | 213 (6th), 4–8 | Wallbox current available L1, L2, L3 | sensor, disabled | read-only | |
| 40854 | 213 (7th), 28 | Fault power | sensor | read-only | |
| 40954 | 60000, 2 | Maximum total current | config, disabled | **flash** | |
| 40956 | 60000, 4 | Power reserve | config, disabled | **flash** | |
| 40958 | 60000, 6 | Overdraw | config, disabled | **flash** | |
| 40960 | 60000, 8 | Maximum wallbox current | config, disabled | **flash** | total of all wallboxes, per phase |
| 40962 | 60000, 10 | Maximum phase imbalance | config, disabled | **flash** | |
| 40964 | 60000, 12 | Load management | config, disabled | **flash** | switch |
| 40966 | 60000, 14 | Imbalance includes consumers | config, disabled | **flash** | switch |
| 40968 | 60000, 16 | Total current limit | number | volatile | percent of the maximum total current |
| 40972–41003 | 60001, 2–33 | Flag 1 … Flag 32 | switch, disabled | volatile | `CM._flag1` … `CM._flag32` in formulas |
| from 41006 | 60002 | Variable *name* | sensor | volatile | one per variable; set with the [action](#action-set-charging-manager-variable) |

## Writing values

| | Volatile | Flash |
| --- | --- | --- |
| Write often (e.g. from a surplus automation) | ✅ | ❌ set once, then leave alone |
| Kept across a reboot or power cut | ❌ falls back to its default | ✅ |
| In Home Assistant | normal controls (cable override disabled) | disabled by default, under *Configuration*; unchanged values are not written |

### Volatile values of the wallbox

| Entity | After a reboot | Notes |
| --- | --- | --- |
| Charging current limit (8093) | Default charging current limit (8081) | The value for surplus charging and load management. The register takes up to 63 A, the UI stops at 32 A. Model, cable and vehicle can cap it lower (the 11 kW cFos Power Brain Wallbox at 16 A); **Signaled charging current** (8095) shows the result. |
| Charging enabled (8094) | Default charging enabled (8082) | Off stops charging, the vehicle stays plugged in. A sleeping vehicle may need **Wake up vehicle**. |
| Phase mode (8087) | not documented | 1 or 3 phases; on 1 phase, 6 A is about 1.4 kW instead of 4.1 kW. Controller Rev. F or later. Switches a contactor: leave minutes between switches. |
| Relay 2 (8088) | not documented | Controller Rev. F or later, relay fitted (8113 bits 9–10). Only switches on while relay 1 is off. |
| Cable current override (8091) | Default cable current override (8080) | Replaces the rating detected from the cable (8090). **Never above the cable's rating.** |
| Wake up vehicle (8086) | – | Disconnects the control pilot for 5 s: wakes most vehicles that fell asleep. |

Re-apply volatile values after a wallbox reboot, e.g. when **Charging state**
changes from `unavailable`.

### Flash values

- Wallbox: power-on defaults (8080–8082), fail-safe (8083–8085).
- S0 meters: pulses per kWh, nominal voltages, counter resets.
- Charging Manager: the parameters of model 60000; it saves a change within
  150 s.

### Volatile values of the Charging Manager

- **Total current limit** (40968): 0–100 % of the maximum total current. cFos'
  way to adjust charging power dynamically, e.g. on request of the grid
  operator; it lowers what the Charging Manager shares out.
- **Flag 1–32**: on/off values its formulas and charging rules read as
  `CM._flag1` … `CM._flag32`, e.g. for "cheap electricity now".
- **Variables**: writing a value **replaces the variable's formula**, so the
  entities are read-only and writing is the action below.

### Action: Set Charging Manager variable

`cfos_powerbrain.set_charging_manager_variable` gives a variable a fixed value,
replacing its formula. Not saved by the Charging Manager; set it as often as
needed. Needs the Charging Manager switched on.

| Field | Required | Description |
| --- | --- | --- |
| `name` | yes | Variable name, exactly as in the Charging Manager. An unknown name is rejected with the list of its variables. |
| `value` | yes | The number to set. |
| `config_entry_id` | no | The wallbox entry, when more than one is set up. |

```yaml
action: cfos_powerbrain.set_charging_manager_variable
data:
  name: pv_mode   # as set up in the Charging Manager
  value: 1
```

## Who controls charging

| | Charging Manager in control | Home Assistant in control |
| --- | --- | --- |
| When | Its surplus charging, load management or charging rules manage the wallbox | It does not manage the wallbox's own charging point (set up as for an *external* charging manager, see the [cFos documentation][cfos-docs]) |
| Charging current limit, Charging enabled | Overwritten on its next cycle; the entity jumps back on the next poll | Write as often as needed |
| Phase mode | Changed back if it switches phases automatically | Write as needed |
| Steer from Home Assistant through | Total current limit, flags, variables | The wallbox entities |

- Readings are the same either way.
- Which applies: while charging, set **Charging current limit** to 6 A. If it
  or **Signaled charging current** returns to another value within a minute,
  the Charging Manager is in control.

### Modbus fail-safe

- The wallbox applies **Fail-safe current** (8085; 0 A stops charging) when no
  Modbus request arrived for **Fail-safe timeout** (8083, 300 s by default).
- Every poll (10 s by default) counts, so it only triggers while Home
  Assistant is down or cannot reach the wallbox.
- Both values are flash: set them once to what should happen then.

## Example: follow solar surplus

Only when Home Assistant is in control (see [above](#who-controls-charging)).

```yaml
automation:
  - alias: "Wallbox follows PV surplus"
    triggers:
      - trigger: state
        entity_id: sensor.pv_surplus_power   # your surplus in W
    conditions:
      - condition: state
        entity_id: binary_sensor.cfos_power_brain_wallbox_vehicle_connected
        state: "on"
    actions:
      - variables:
          amps: "{{ (states('sensor.pv_surplus_power') | float(0) / (230 * 3)) | round(1) }}"
      - if: "{{ amps >= 6 }}"
        then:
          - action: number.set_value
            target:
              entity_id: number.cfos_power_brain_wallbox_charging_current_limit
            data:
              value: "{{ [amps, 16] | min }}"
          - action: switch.turn_on
            target:
              entity_id: switch.cfos_power_brain_wallbox_charging_enabled
        else:
          - action: switch.turn_off
            target:
              entity_id: switch.cfos_power_brain_wallbox_charging_enabled
```

## Compared with the HTTP API integration

| Feature of the [HTTP API integration][rest-integration] | Here |
| --- | --- |
| Charging state, power, energy, currents | ✅ |
| Charging current limit, charging enable | ✅ |
| 1/3-phase switching | ✅ |
| Session energy, used phases | ✅ derived |
| Charging Manager variables (`set_variable`) | ✅ action |
| Charging Manager parameters (`set_params`) | ✅ model 60000 |
| Grid, consumer, generator, PV surplus and wallbox power | ✅ |
| Charging rules, user rules switch | ❌ no Modbus counterpart; flags can feed rules |
| RFID/PIN entry, HTTP input meters (`set_meter`), pause reason and time | ❌ no Modbus counterpart |
| Other devices of the Charging Manager | ❌ not yet (Modbus ID + 1) |

## Removal

1. **Settings → Devices & services → cFos Power Brain Wallbox (Modbus) → ⋮ →
   Delete**: removes devices, entities and Modbus connections.
2. Marketplace: remove it from its menu under **Settings → Marketplace**, then
   restart when the repair asks. Manual: delete
   `custom_components/cfos_powerbrain` and restart.

Afterwards, on the wallbox:

- Volatile values keep their last value until the next restart, then fall
  back to their defaults; flash values stay.
- Nothing polls it any more: with the [fail-safe](#modbus-fail-safe) on, the
  fail-safe current applies after the fail-safe timeout. Check both first.
- Switch the Charging Manager's SunSpec server off again if only this
  integration used it.

## Reporting problems

1. Download diagnostics: **Settings → Devices & services → cFos Power Brain
   Wallbox (Modbus) → ⋮ → Download diagnostics**. Holds every register read
   (serial numbers and RFID tag redacted) and the Charging Manager's SunSpec
   models.
2. Or, without Home Assistant: `uv run script/dump_registers.py <host> --raw`,
   plus `--charging-manager` for the Charging Manager. Without [uv][uv]:
   `pip install "modbus-connection[tmodbus]>=4.12.3"`, then `python` instead of
   `uv run`.
3. Open an [issue][issues] with the file and what you expected.

## Development

- `custom_components/cfos_powerbrain/cfos_modbus/`: device library on
  [`modbus-connection`][modbus-connection], no Home Assistant imports. Typed
  components for the register blocks; reads documented ranges only; validates
  writes; scans the Charging Manager's SunSpec models.
- `custom_components/cfos_powerbrain/`: the integration (config flow,
  coordinators, entities), with Modbus units from the `modbus` integration.

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest
```

Conventions, CI and the quality scale target: [AGENTS.md](AGENTS.md).

## Disclaimer

"cFos", "Power Brain" and the cFos eMobility logo are trademarks of cFos
Software GmbH; the logo identifies the product, as for the HTTP API
integration in Home Assistant's [brands repository](https://github.com/home-assistant/brands).
Writing to a wallbox controls real hardware; use at your own risk.

[ci]: https://github.com/TimoFriedri/ha-cfos-powerbrain-modbus/actions/workflows/ci.yml
[ci-badge]: https://github.com/TimoFriedri/ha-cfos-powerbrain-modbus/actions/workflows/ci.yml/badge.svg
[issues]: https://github.com/TimoFriedri/ha-cfos-powerbrain-modbus/issues
[ha-modbus]: https://contributors.home-assistant.io/core/internals/modbus/
[modbus-connection]: https://github.com/home-assistant-libs/modbus-connection
[cfos-registers]: https://www.cfos-emobility.de/en/cfos-power-brain/modbus-registers.htm
[cfos-docs]: https://www.cfos-emobility.de/en/cfos-charging-manager/documentation/power-brain-configuration.htm
[rest-integration]: https://github.com/guibrazlima/homeassistant-powerbrain
[uv]: https://docs.astral.sh/uv/
