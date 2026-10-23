<img src="https://raw.githubusercontent.com/TimoFriedri/ha-cfos-powerbrain-modbus/main/custom_components/cfos_powerbrain/brand/logo.png" alt="cFos eMobility" height="80">

> [!IMPORTANT]
> This is an independent, third-party community integration. It is not
> developed, endorsed or supported by cFos Software GmbH. For problems with
> it, open an [issue][issues] here, not with cFos support.

# cFos Power Brain (Modbus) for Home Assistant

[![HACS Custom][hacs-badge]][hacs]
[![Validate][validate-badge]][validate]
[![Tests][tests-badge]][tests]

Monitor and control a **cFos Power Brain** wallbox (or Power Brain controller)
from Home Assistant over **Modbus TCP**, using the
[Modbus framework introduced in Home Assistant 2026.9][ha-modbus].

The integration asks Home Assistant's `modbus` integration for a shared
connection to the wallbox (`modbus.async_get_unit`), so it coexists with any
other integration talking to the same device. You set it up in the UI and
write no YAML.

> **Status: first release, not yet verified on real hardware.** The register
> map follows the official [cFos Modbus documentation][cfos-registers] and is
> covered by tests against a simulated wallbox. Please report what your
> wallbox shows; see [Reporting problems](#reporting-problems).

## Features

**Wallbox** (Modbus slave ID 1, TCP port 4701)

The **Writes** column says what writing a value does; see
[Writing values: volatile or flash](#writing-values-volatile-or-flash).

| Register | Entity | Type | Writes | Notes |
| --- | --- | --- | --- | --- |
| 8058 | Total energy | sensor | read-only | only if a meter is attached (8112) |
| 8058, 8092 | Session energy | sensor, derived | read-only | energy since the vehicle was plugged in; kept after unplugging until the next session |
| 8062 | Power | sensor | read-only | only if a meter is attached (8112) |
| 8064–8069 | Current L1, L2, L3 | sensor | read-only | only if a meter is attached (8112) |
| 8064–8069 | Active phases | sensor, derived | read-only | phases carrying at least 1 A |
| 8080 | Default cable current override | config, disabled | **flash** | applied after a reboot |
| 8081 | Default charging current limit | config, disabled | **flash** | applied after a reboot |
| 8082 | Default charging enabled | config, disabled | **flash** | applied after a reboot |
| 8083 | Fail-safe timeout | config, disabled | **flash** | see [Fail-safe](#the-modbus-fail-safe) |
| 8085 | Fail-safe current | config, disabled | **flash** | see [Fail-safe](#the-modbus-fail-safe) |
| 8086 | Wake up vehicle | button | volatile | interrupts the control pilot for 5 s |
| 8087 | Phase mode (1 / 3 phases) | select | volatile | only if the wallbox allows phase switching (8113 bit 8) |
| 8088 | Relay 2 | switch | volatile | only if a second relay is fitted (8113 bits 9–10) |
| 8090 | Cable current rating | diagnostic | read-only | |
| 8091 | Cable current override | config, disabled | volatile | |
| 8092 | Charging state | sensor (enum) | read-only | waiting, vehicle connected, charging, charging (ventilation), no power, error, DC sensor error |
| 8092 | Vehicle connected, Charging, Problem | binary sensor, derived | read-only | from the charging state |
| 8093 | Charging current limit | number | volatile | 6–32 A in 0.1 A steps |
| 8094 | Charging enabled | switch | volatile | |
| 8095 | Signaled charging current | sensor | read-only | current the wallbox signals to the vehicle |
| 8096 | Last RFID | diagnostic, disabled | read-only | |
| 8113 | Phase switching allowed | diagnostic | read-only | |
| 8120 | Restarts | diagnostic, disabled | read-only | |
| 8122 | Controller temperature | diagnostic | read-only | controller Rev. 3.0 and later |

**S0 meters** (optional, slave IDs 2 and 3, TCP ports 4702 and 4703): power,
total energy and currents L1–L3, all read-only. Disabled extras: the pulse
counter and the time between pulses (read-only); pulses per kWh and the
nominal voltages (**flash**); buttons to reset the energy and pulse counters
(**flash**).

Total energy sensors keep their last value while the wallbox is unreachable
and across restarts, so the energy dashboard has no gaps. A reading of 0 Wh,
which the controller reports briefly after it starts, is treated as unknown
rather than as a meter reset.

## Writing values: volatile or flash

The controller stores most writable registers in its flash memory. Flash
survives a reboot but wears out with every write. cFos names six registers
that are **not** stored in flash. These volatile values are meant to be
changed while charging.

| | Volatile | Flash |
| --- | --- | --- |
| Write as often as you like | ✅ e.g. every few seconds from a surplus automation | ❌ set once, then leave alone |
| Survives a wallbox reboot or power cut | ❌ falls back to its default | ✅ |
| Shown in Home Assistant | as normal controls (except the cable override) | disabled by default, under *Configuration* |

### The volatile values

**Charging current limit** (8093, number)
- The most current the vehicle may draw, 6–32 A in 0.1 A steps. The register
  would accept up to 63 A; the UI stops at 32 A, the maximum of a 22 kW
  wallbox.
- The model can cap it lower; for example, the 11 kW Power Brain wallbox
  limits it to 16 A. The cable rating (8090) and the vehicle itself can also
  lower what is actually drawn. **Signaled charging current** (8095) shows
  what the wallbox currently offers the vehicle.
- After a reboot: **Default charging current limit** (8081).
- This is the value for solar surplus charging and load management.

**Charging enabled** (8094, switch)
- On allows charging, off stops it. The vehicle stays plugged in. Most
  vehicles resume charging when it is switched on again; one that has gone to
  sleep may need **Wake up vehicle**.
- After a reboot: **Default charging enabled** (8082).

**Phase mode** (8087, select)
- Charges through the 3-phase contactor (`3 phases`) or the 1-phase contactor
  (`1 phase`). On one phase, 6 A is about 1.4 kW instead of about 4.1 kW, so
  solar charging can start at a lower surplus.
- Needs controller Rev. F or later. The entity only exists if the wallbox
  reports phase switching as allowed (8113 bit 8).
- It is volatile, but it switches a physical contactor. Leave a few minutes
  between switches rather than following every cloud.
- The register documentation does not say what it falls back to after a
  reboot.

**Relay 2** (8088, switch)
- Switches the controller's second relay, if one is fitted (8113 bits 9–10).
  Needs controller Rev. F or later.
- It only switches on while relay 1 is off.
- Like the phase mode, it moves a physical relay.
- The register documentation does not say what it falls back to after a
  reboot.

**Cable current override** (8091, number, disabled by default)
- Replaces the current rating the wallbox detects from the plugged cable
  (8090, proximity pilot). This is for special cases, such as a cable whose
  rating the wallbox cannot detect.
- **Never set it higher than the cable is rated for**: the rating keeps the
  cable from overheating.
- After a reboot: **Default cable current override** (8080).

**Wake up vehicle** (8086, button)
- Disconnects the control pilot for 5 s. The vehicle sees this as unplugging
  and plugging in again, which wakes many vehicles that went to sleep before
  charging started.

Because volatile values are lost on a reboot, an automation that depends on
one should apply it again when the wallbox comes back. For example, trigger
when **Charging state** changes from `unavailable`.

### The flash values

These are the power-on defaults (8080–8082), the fail-safe (8083–8085) and,
on the S0 meters, the pulses per kWh, the nominal voltages and the counter
resets. The integration protects them:

- Their entities are **disabled by default** and listed under
  *Configuration*.
- The integration does not write a value that would not change.

Set them once to suit your installation, and do not change them from
automations.

## Requirements

- Home Assistant **2026.10.0** or newer.
- A cFos Power Brain wallbox or controller reachable on your network, with
  Modbus TCP available on ports 4701 (wallbox) and, for the S0 meters, 4702
  and 4703.

## Installation

### HACS

1. In HACS, open the menu → **Custom repositories**.
2. Add `https://github.com/TimoFriedri/ha-cfos-powerbrain-modbus` with type
   **Integration**.
3. Install **cFos Power Brain (Modbus)** and restart Home Assistant.

### Manual

Copy `custom_components/cfos_powerbrain` into the `custom_components` folder
of your Home Assistant configuration and restart.

## Configuration

**Settings → Devices & services → Add integration → cFos Power Brain (Modbus)**,
then enter:

| Field | Default | |
| --- | --- | --- |
| Host | | IP address or host name of the wallbox |
| Port | 4701 | Modbus TCP port of the charging station |
| Modbus slave ID | 1 | Slave ID of the charging station |
| Polling interval | 10 s | Seconds between reads of the live values, 1–30 |

The integration identifies the device by its vendor ID and serial number
before it creates the entry. **Reconfigure** changes the address later, for
example after the wallbox got a new IP address.

**Options** (the gear on the integration entry):

- **Polling interval**: change the interval set during setup (1–30 s).
  Settings such as the fail-safe are read every 5 minutes regardless.
- **S0 meters**: adds S0 meter 1 and/or 2 as devices.

It can run side by side with the HTTP-API-based
[`powerbrain` integration][rest-integration]; the two use different domains.

## Home Assistant control and the cFos Charging Manager

The Power Brain wallbox has the cFos Charging Manager built in. What happens
to values that Home Assistant writes depends on whether that Charging Manager
manages the wallbox's own charging point.

### When the Charging Manager manages the wallbox

This is the usual setup when you use the Charging Manager's solar surplus
charging, load management or charging rules. The Charging Manager
recalculates the charging current of every charging point it manages in each
control cycle and sets it on the wallbox. Then:

- **Charging current limit** (8093) and **Charging enabled** (8094) written
  from Home Assistant can be **overwritten on the Charging Manager's next
  cycle**. In Home Assistant, the number or switch jumps back to the Charging
  Manager's value on the next poll.
- **Phase mode** (8087) can likewise be changed back if the Charging Manager
  does automatic phase switching.
- Reading is unaffected: all sensors show what the wallbox is doing,
  whoever decided it.

Use the integration mainly for monitoring in this setup, and steer charging
through the Charging Manager. The planned HTTP add-on, see
[Roadmap](#roadmap), will expose the Charging Manager's own controls
(charging rules, overrides, variables).

### When Home Assistant controls the wallbox

To make Home Assistant (or an automation such as solar surplus charging) the
one that decides, keep the built-in Charging Manager from managing the
wallbox's own charging point. This is the same configuration cFos describes
for running the wallbox under an *external* charging manager. The exact
setting depends on your firmware; see the [cFos documentation][cfos-docs].
Then:

- Charging current limit, Charging enabled, Phase mode and Relay 2 can be
  written as often as needed. After a reboot they fall back to their
  defaults; see
  [The volatile values](#the-volatile-values).

### Which one applies to me?

Try this while a vehicle is charging: set **Charging current limit** to 6 A in
Home Assistant and watch it and **Signaled charging current** for a minute. If
they go back to another value on their own, the Charging Manager is in
control.

### The Modbus fail-safe

The wallbox applies **Fail-safe current** (8085) when no Modbus read or write
has arrived for **Fail-safe timeout** (8083, 300 s by default). 0 A stops
charging. The integration polls every 10 s by default, and every poll counts
as activity. The fail-safe therefore triggers only when Home Assistant is down
or cannot reach the wallbox. Set the fail-safe current to what should happen
then. Both fail-safe values are stored in flash: set them once.

## Example: follow solar surplus

```yaml
automation:
  - alias: "Wallbox follows PV surplus"
    triggers:
      - trigger: state
        entity_id: sensor.pv_surplus_power   # your surplus in W
    conditions:
      - condition: state
        entity_id: binary_sensor.cfos_power_brain_vehicle_connected
        state: "on"
    actions:
      - variables:
          amps: "{{ (states('sensor.pv_surplus_power') | float(0) / (230 * 3)) | round(1) }}"
      - if: "{{ amps >= 6 }}"
        then:
          - action: number.set_value
            target:
              entity_id: number.cfos_power_brain_charging_current_limit
            data:
              value: "{{ [amps, 16] | min }}"
          - action: switch.turn_on
            target:
              entity_id: switch.cfos_power_brain_charging_enabled
        else:
          - action: switch.turn_off
            target:
              entity_id: switch.cfos_power_brain_charging_enabled
```

This only works when Home Assistant controls the wallbox; see
[above](#home-assistant-control-and-the-cfos-charging-manager).

## Compared with the HTTP API integration

Modbus covers the wallbox itself. Features of the
[HTTP-API integration][rest-integration] that belong to the Charging Manager
have no Modbus register:

| Feature | This integration |
| --- | --- |
| Charging state, power, energy, currents | ✅ |
| Charging current limit, charging enable | ✅ (register writes, see above) |
| 1/3-phase switching | ✅ |
| Session energy | ✅ (derived from the meter) |
| Used phases | ✅ (derived from the phase currents) |
| Charging rules (get/set/update), user rules switch | ❌ Charging Manager only, planned |
| Enter RFID/PIN, Charging Manager variables and parameters | ❌ Charging Manager only, planned |
| HTTP input meters (`set_meter`) | ❌ Charging Manager only, planned |
| Pause reason, pause time | ❌ Charging Manager only, planned |
| Other devices managed by the Charging Manager | ❌ Charging Manager only, planned |

## Roadmap

- Optional HTTP API add-on (admin login in the options) for the Charging
  Manager features in the table above.

## Reporting problems

1. Download diagnostics: **Settings → Devices & services → cFos Power Brain
   (Modbus) → ⋮ → Download diagnostics**. It contains the raw value of every
   register the integration reads, with the serial number and RFID tag
   redacted.
2. Or, without Home Assistant, run
   `python script/dump_registers.py <host> --raw` (needs
   `pip install "modbus-connection[tmodbus]>=4.12.3"`).
3. Open an [issue][issues] with the file and what you expected to see.

The firmware version decoding (`product_version` / `product_build`, registers
8004–8005) is the part most likely to need adjusting; the register
documentation is ambiguous there.

## How it is built

Following Home Assistant's [Modbus integration guide][ha-modbus], the
integration has two layers:

- `custom_components/cfos_powerbrain/cfos_modbus/`: a device library built
  on [`modbus-connection`][modbus-connection], with no Home Assistant imports.
  It maps the register map to typed components (identity, status, meter,
  settings, health, S0 meters), reads only documented register ranges and
  validates values before writing. It is vendored here so HACS can install
  it, and can move to its own PyPI package unchanged.
- `custom_components/cfos_powerbrain/`: the Home Assistant integration. It
  has the config flow, the coordinators and the entities, and gets its Modbus
  units from the `modbus` integration.

### Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
ruff check . && ruff format --check . && mypy
pytest
```

The tests run the device library against `modbus-connection`'s in-memory mock,
and run the integration against Home Assistant with only the Modbus transport
mocked.

## Disclaimer

Not affiliated with or endorsed by cFos Software GmbH. "cFos", "Power Brain"
and the cFos eMobility logo are their trademarks. The logo identifies the
product here, as it does for the HTTP API integration in Home Assistant's
[brands repository](https://github.com/home-assistant/brands). Writing to a
wallbox controls real hardware; use at your own risk.

[hacs]: https://hacs.xyz
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-orange.svg
[validate]: https://github.com/TimoFriedri/ha-cfos-powerbrain-modbus/actions/workflows/validate.yml
[validate-badge]: https://github.com/TimoFriedri/ha-cfos-powerbrain-modbus/actions/workflows/validate.yml/badge.svg
[tests]: https://github.com/TimoFriedri/ha-cfos-powerbrain-modbus/actions/workflows/tests.yml
[tests-badge]: https://github.com/TimoFriedri/ha-cfos-powerbrain-modbus/actions/workflows/tests.yml/badge.svg
[issues]: https://github.com/TimoFriedri/ha-cfos-powerbrain-modbus/issues
[ha-modbus]: https://developers.home-assistant.io/docs/modbus/introduction
[modbus-connection]: https://github.com/home-assistant-libs/modbus-connection
[cfos-registers]: https://www.cfos-emobility.de/en/cfos-power-brain/modbus-registers.htm
[cfos-docs]: https://www.cfos-emobility.de/en/cfos-charging-manager/documentation/power-brain-configuration.htm
[rest-integration]: https://github.com/guibrazlima/homeassistant-powerbrain
