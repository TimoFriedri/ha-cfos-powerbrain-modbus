> [!IMPORTANT]
> This is an independent, third-party community integration. It is not
> developed, endorsed or supported by cFos Software GmbH. For problems with
> it, open an [issue][issues] here, not with cFos support.

# cFos Power Brain Wallbox (Modbus) for Home Assistant

[![HACS Custom][hacs-badge]][hacs]
[![CI][ci-badge]][ci]

Monitor and control a **cFos Power Brain Wallbox**, or a wallbox built around
the **cFos Power Brain Controller**, from Home Assistant over **Modbus TCP**,
using the [Modbus framework introduced in Home Assistant 2026.9][ha-modbus].

[![Open your Home Assistant instance and open a repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?category=custom+integration&owner=TimoFriedri&repository=https%3A%2F%2Fgithub.com%2FTimoFriedri%2Fha-cfos-powerbrain-modbus)

[cFos Software GmbH](https://www.cfos-emobility.de) makes the cFos Power
Brain Wallbox and the cFos Power Brain Controller, which other wallbox makers
build in. Both have the **cFos Charging Manager** built in, which does load
management, solar surplus charging and charging rules for one or many
charging points. This integration reads and controls the charging point, its
meters and the cFos Charging Manager, all over Modbus.

The integration asks Home Assistant's `modbus` integration for a shared
connection to the wallbox (`modbus.async_get_unit`), so it coexists with any
other integration talking to the same device. You set it up in the UI and
write no YAML.

> **Status:** the charging point runs on a real cFos Power Brain Wallbox.
> The cFos Charging Manager device is tested against a simulated SunSpec
> server built from the cFos documentation, not yet on hardware. Please
> report what your wallbox shows; see [Reporting problems](#reporting-problems).

## Features

**Wallbox** (Modbus slave ID 1, TCP port 4701), following cFos'
[Modbus register documentation][cfos-registers]. The **Writes** column says
what writing a value does; see
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

Like every entity, the total energy sensors are unavailable while the wallbox
cannot be read. A reading of 0 Wh, which the controller reports briefly after
it starts, is treated as unknown rather than as a meter reset, and a reading
just below the last one is ignored.

**Charging Manager** (optional, its own device *cFos Charging Manager* next to
the charging point). The built-in Charging Manager is read and controlled
through its SunSpec Modbus server; see
[Setting up the Charging Manager](#setting-up-the-charging-manager).

cFos states that the register addresses can change between firmware versions.
The integration therefore scans the SunSpec model chain from 40000 at startup
and finds each value by its model and offset, and rescans when the models move.
The *Register* column shows where each value is on current firmware.

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
| from 41006 | 60002 | Variable *name* | sensor | volatile | one per Charging Manager variable; set with the [action](#action-set-charging-manager-variable) |

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
- The model can cap it lower; for example, the 11 kW cFos Power Brain Wallbox
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

### Charging Manager values

The Charging Manager follows the same split, per its SunSpec documentation:

- **Volatile:**
  - **Total current limit** (40968): the maximum total current in percent,
    0–100. cFos describes it as the way to adjust the charging power
    dynamically, for example at the grid operator's request. Because it
    lowers the total current the Charging Manager shares out among its
    charging points, it is also a way to steer charging from Home Assistant
    while the Charging Manager stays in control.
  - **Flag 1–32** (model 60001): on/off values that the Charging Manager's
    formulas and charging rules can read as `CM._flag1` … `CM._flag32`.
    Use them to hand a decision from Home Assistant to a charging rule,
    such as "cheap electricity now".
  - **Variables** (model 60002): writing a value **replaces the formula**
    the variable had with that fixed value. That is why variables are
    read-only sensors, and writing is the separate action below.
- **Flash:** the parameters of model 60000 (maximum total current, power
  reserve, overdraw, maximum wallbox current, maximum phase imbalance, load
  management and imbalance including consumers). The Charging Manager saves
  a change within 150 s. Like the wallbox's flash values, their entities are
  disabled by default and unchanged values are not written.

#### Action: Set Charging Manager variable

`cfos_powerbrain.set_charging_manager_variable` gives a Charging Manager
variable a fixed value. This **replaces the formula** the variable had. The
value is not saved by the Charging Manager and may be set as often as needed.
The action needs the Charging Manager device switched on, during setup or
in the options.

| Field | Required | Description |
| --- | --- | --- |
| `name` | yes | Name of the variable, exactly as set up in the Charging Manager. |
| `value` | yes | The number to give the variable. |
| `config_entry_id` | no | The wallbox entry whose Charging Manager to use. Needed only when more than one wallbox is set up. |

```yaml
action: cfos_powerbrain.set_charging_manager_variable
data:
  name: pv_mode   # as set up in the Charging Manager
  value: 1
```

An unknown name is rejected with the list of the variables the Charging
Manager has.

## Requirements

- Home Assistant **2026.10.0** or newer.
- A cFos Power Brain Wallbox, or a wallbox with the cFos Power Brain
  Controller, reachable on your network, with Modbus TCP available on ports
  4701 (wallbox) and, for the S0 meters, 4702 and 4703.
- A fixed IP address for the wallbox, for example a DHCP reservation in your
  router. If the address changes anyway, **Reconfigure** updates it.
- For the Charging Manager device: its SunSpec server switched on, see
  [Setting up the Charging Manager](#setting-up-the-charging-manager).

## Installation

### HACS

1. In HACS, open the menu → **Custom repositories**.
2. Add `https://github.com/TimoFriedri/ha-cfos-powerbrain-modbus` with type
   **Integration**.
3. Install **cFos Power Brain Wallbox (Modbus)** and restart Home Assistant.

### Manual

Copy `custom_components/cfos_powerbrain` into the `custom_components` folder
of your Home Assistant configuration and restart.

## Configuration

**Settings → Devices & services → Add integration → cFos Power Brain Wallbox
(Modbus)**, then enter:

| Field | Default | |
| --- | --- | --- |
| Host | | IP address or host name of the wallbox |
| Port | 4701 | Modbus TCP port of the charging station |
| Modbus slave ID | 1 | Slave ID of the charging station |
| Polling interval | 10 s | Seconds between reads of the live values, 1–30 |
| Charging Manager | off | Adds the Charging Manager as its own device; see [below](#setting-up-the-charging-manager) |
| Charging Manager port | 502 | TCP port of the Charging Manager's SunSpec server |
| Charging Manager Modbus ID | 1 | Modbus ID of the Charging Manager's SunSpec server |

The integration identifies the device by its vendor ID and serial number
before it creates the entry. With the Charging Manager switched on, it also
checks that the Charging Manager's SunSpec server answers. **Reconfigure**
changes the address later, for example after the wallbox got a new IP
address.

**Options** (the gear on the integration entry):

- **Polling interval**: change the interval set during setup (1–30 s).
  Settings such as the fail-safe are read every 5 minutes regardless.
- **S0 meters**: adds S0 meter 1 and/or 2 as devices.
- **Charging Manager**, **Charging Manager port**, **Charging Manager Modbus
  ID**: switch the Charging Manager on or off, or change its port and Modbus
  ID, as set during setup.

It can run side by side with the HTTP-API-based
[`powerbrain` integration][rest-integration]; the two use different domains.

### Setting up the Charging Manager

1. In the Charging Manager's configuration, under **SunSpec address
   settings**, enter a TCP port and a Modbus ID. On the cFos Power Brain
   Wallbox the port is 502. This switches on the Charging Manager's SunSpec
   Modbus server.
2. When adding the integration, or later in its options, switch on
   **Charging Manager** and enter the same port and Modbus ID. The integration
   checks that the server answers before it saves them.

The *cFos Charging Manager* device then appears next to the charging point.
If the server does not answer when Home Assistant starts, the charging point
still sets up. The Charging Manager's entities appear once the server answers.

The Charging Manager also lists the wallboxes and meters it manages under
Modbus ID + 1. The integration does not read that list yet.

## Removal

1. **Settings → Devices & services → cFos Power Brain Wallbox (Modbus) → ⋮ →
   Delete.** This removes the devices and entities and closes the Modbus
   connections.
2. Installed through HACS: **HACS → cFos Power Brain Wallbox (Modbus) → ⋮ →
   Remove**, then restart Home Assistant. Installed manually: delete
   `custom_components/cfos_powerbrain` and restart.

What stays on the wallbox afterwards:

- Volatile values (charging current limit, charging enabled, phase mode,
  relay 2, the Charging Manager's total current limit and flags) keep their
  last value until the wallbox restarts. Then they fall back to their
  defaults.
- Values stored in flash stay as they were last set.
- With Home Assistant gone, nothing reads the wallbox over Modbus any more.
  If the wallbox's [Modbus fail-safe](#the-modbus-fail-safe) is on, it applies
  the fail-safe current once Modbus has been silent for the fail-safe
  timeout. Check both settings before you remove the integration.
- If you switched on the Charging Manager's SunSpec server only for this
  integration, you can switch it off again under **SunSpec address settings**.

## Home Assistant control and the cFos Charging Manager

The cFos Power Brain Wallbox has the cFos Charging Manager built in. What
happens to values that Home Assistant writes depends on whether that Charging
Manager manages the wallbox's own charging point.

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

In this setup, steer charging through the Charging Manager instead. With the
[Charging Manager device](#setting-up-the-charging-manager) enabled,
Home Assistant can do that over Modbus:

- **Total current limit** lowers the total current the Charging Manager
  shares out among its charging points.
- **Flags** and **variables** feed the Charging Manager's charging rules and
  formulas, such as a rule that charges only while `CM._flag1` is set.

### When Home Assistant controls the wallbox

To make Home Assistant (or an automation such as solar surplus charging) the
one that decides, keep the built-in Charging Manager from managing the
wallbox's own charging point. This is the same configuration cFos describes
for running the wallbox under an *external* charging manager. The exact
setting depends on your firmware; see the [cFos documentation][cfos-docs].
Then:

- Charging current limit, Charging enabled, Phase mode and Relay 2 can be
  written as often as needed. After a reboot they fall back to their
  defaults; see [The volatile values](#the-volatile-values).

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

This only works when Home Assistant controls the wallbox; see
[above](#home-assistant-control-and-the-cfos-charging-manager).

## Compared with the HTTP API integration

The wallbox registers cover the charging point; the Charging Manager's
SunSpec server covers its values, parameters, flags and variables. Some
features of the [HTTP-API integration][rest-integration] have no Modbus
counterpart:

| Feature | This integration |
| --- | --- |
| Charging state, power, energy, currents | ✅ |
| Charging current limit, charging enable | ✅ (register writes, see above) |
| 1/3-phase switching | ✅ |
| Session energy | ✅ (derived from the meter) |
| Used phases | ✅ (derived from the phase currents) |
| Charging Manager variables (`set_variable`) | ✅ (action, Charging Manager device) |
| Charging Manager parameters (`set_params`) | ✅ for the parameters of model 60000 |
| Grid, consumer, generator, PV surplus and wallbox power | ✅ (Charging Manager device) |
| Charging rules (get/set/update), user rules switch | ❌ no Modbus counterpart; flags can feed existing rules |
| Enter RFID/PIN | ❌ no Modbus counterpart |
| HTTP input meters (`set_meter`) | ❌ no Modbus counterpart |
| Pause reason, pause time | ❌ no Modbus counterpart |
| Other devices managed by the Charging Manager | ❌ not yet; available under Modbus ID + 1 |

## Reporting problems

1. Download diagnostics: **Settings → Devices & services → cFos Power Brain
   Wallbox (Modbus) → ⋮ → Download diagnostics**. It contains the raw value of
   every register the integration reads, with the serial numbers and RFID tag
   redacted. For the Charging Manager it also lists the SunSpec models found
   and their addresses.
2. Or, without Home Assistant, run
   `uv run script/dump_registers.py <host> --raw`, adding
   `--charging-manager` to include the Charging Manager. Without
   [uv][uv], `pip install "modbus-connection[tmodbus]>=4.12.3"` first and
   use `python` instead of `uv run`.
3. Open an [issue][issues] with the file and what you expected to see.

The firmware version decoding (`product_version` / `product_build`, registers
8004–8005) is the part most likely to need adjusting; the register
documentation is ambiguous there. The same goes for the Charging Manager
variables (model 60002): the cFos documentation gives two layouts, and the
integration picks the one that matches the names it reads. If variable names
look wrong, please include the diagnostics.

## How it is built

Following Home Assistant's [Modbus integration guide][ha-modbus], the
integration has two layers:

- `custom_components/cfos_powerbrain/cfos_modbus/`: a device library built
  on [`modbus-connection`][modbus-connection], with no Home Assistant imports.
  It maps the register map to typed components (identity, status, meter,
  settings, health, S0 meters), reads only documented register ranges and
  validates values before writing. For the Charging Manager it scans the
  SunSpec model chain and places components at the models it finds. It is
  vendored here so HACS can install it, and can move to its own PyPI package
  unchanged.
- `custom_components/cfos_powerbrain/`: the Home Assistant integration. It
  has the config flow, the coordinators and the entities, and gets its Modbus
  units from the `modbus` integration.

### Development

With [uv][uv] installed:

```bash
uv sync   # creates .venv with the versions pinned in uv.lock
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest
```

The tests run the device library against `modbus-connection`'s in-memory mock,
and run the integration against Home Assistant with only the Modbus transport
mocked. [AGENTS.md](AGENTS.md) has the conventions for changes: code style,
commit messages and the quality scale target.

## Disclaimer

Not affiliated with or endorsed by cFos Software GmbH. "cFos", "Power Brain"
and the cFos eMobility logo are their trademarks. The logo identifies the
product here, as it does for the HTTP API integration in Home Assistant's
[brands repository](https://github.com/home-assistant/brands). Writing to a
wallbox controls real hardware; use at your own risk.

[hacs]: https://hacs.xyz
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-orange.svg
[ci]: https://github.com/TimoFriedri/ha-cfos-powerbrain-modbus/actions/workflows/ci.yml
[ci-badge]: https://github.com/TimoFriedri/ha-cfos-powerbrain-modbus/actions/workflows/ci.yml/badge.svg
[issues]: https://github.com/TimoFriedri/ha-cfos-powerbrain-modbus/issues
[ha-modbus]: https://developers.home-assistant.io/docs/modbus/introduction
[modbus-connection]: https://github.com/home-assistant-libs/modbus-connection
[cfos-registers]: https://www.cfos-emobility.de/en/cfos-power-brain/modbus-registers.htm
[cfos-docs]: https://www.cfos-emobility.de/en/cfos-charging-manager/documentation/power-brain-configuration.htm
[rest-integration]: https://github.com/guibrazlima/homeassistant-powerbrain
[uv]: https://docs.astral.sh/uv/
