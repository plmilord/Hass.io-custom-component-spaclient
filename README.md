<span align="center">

<a href="https://github.com/plmilord/Hass.io-custom-component-spaclient"><img src="https://raw.githubusercontent.com/plmilord/Hass.io-custom-component-spaclient/master/brand/icon.png" width="150"></a>

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/plmilord/Hass.io-custom-component-spaclient.svg)](https://GitHub.com/plmilord/Hass.io-custom-component-spaclient/releases/)
[![HA integration usage](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.spaclient.total)](https://analytics.home-assistant.io/custom_integrations.json)

# Home Assistant custom component - Spa Client

</span>

Since the event where my spa emptied when it was -30°C outside and it took me a while to find out (luckily, more fear than harm!)... I tried to find a solution to better supervise my spa! Initially, I wanted to replicate my iPhone's **Coast Spas** App in Home Assistant so that I could create notifications, track, control and automate/script some stuff. I was also looking to replicate my home automation in the **Home** App to simplify my family's access to all my different platforms. Home Assistant was the perfect fit for that!

**Spa Client** is inspired by several similar projects and the work of many people. With version 2.0 and later, several elements have been improved in order to represent the App **Coast Spas** as faithfully as possible. During installation, all the components are created according to the configuration of your spa!

## What you need

- A Hot Tub Equipped with a Balboa BP System
- bwa™ Wi-Fi Module (50350)
- Reference : http://www.balboawatergroup.com/bwa

## Installation

You can install this integration via [HACS](#hacs) or [manually](#manual).

### HACS

Search for the Spa Client integration and choose install. Reboot Home Assistant and configure the Spa Client integration via the integrations page or press the blue button below.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=spaclient)


### Manual

Copy the `custom_components/spaclient` to your custom_components folder. Reboot Home Assistant and configure the Spa Client integration via the integrations page or press the blue button below.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=spaclient)


## Preview

<span align="center">

<a href="https://github.com/plmilord/Hass.io-custom-component-spaclient"><img src="https://raw.githubusercontent.com/plmilord/Hass.io-custom-component-spaclient/master/images/preview.png" width="500"></a>

<a href="https://github.com/plmilord/Hass.io-custom-component-spaclient"><img src="https://raw.githubusercontent.com/plmilord/Hass.io-custom-component-spaclient/master/images/options.png" width="400"></a>

</span>

Several elements have already been validated (with my spa), but several remain to be validated **with your help**. The following table shows what is known to be functional: 

Entity | Type | Tested | Programmed entity attributes
------ | ---- | ------ | ----------------------------
Auxiliary 1 | Switch | ? | N/A
Auxiliary 2 | Switch | ? | N/A
Blower | Switch | ✓ | Off, On
Circulation Pump | Binary sensor | ✓ | False, True
Filter Cycle 1 Begins | Time | ✓ | N/A
Filter Cycle 1 Runs | Time | ✓ | N/A
Filter Cycle 1 Status | Binary sensor | ✓ | Begins, Runs, Ends
Filter Cycle 2 | Switch | ✓ | 0, 1
Filter Cycle 2 Begins | Time | ✓ | N/A
Filter Cycle 2 Runs | Time | ✓ | N/A
Filter Cycle 2 Status | Binary sensor | ✓ | Begins, Runs, Ends
Heat Mode | Switch | ✓ | Ready, Rest, Ready in Rest
Hold Mode | Switch | ✓ | Remaining Time
Last Known Fault | Sensor | ✓ | N/A
Light 1 | Light | ✓ | False, True
Light 2 | Light | ? | False, True
Mister | Switch | ? | Off, On
Pump 1 | Switch | ✓ | Off, Low, High
Pump 2 | Switch | ✓ | Off, Low, High
Pump 3 | Switch | ✓ | Off, Low, High
Pump 4 | Switch | ? | Off, Low, High
Pump 5 | Switch | ? | Off, Low, High
Pump 6 | Switch | ? | Off, Low, High
Spa Thermostat | Climate | ✓ | N/A
Standby Mode | Switch | ✓ | N/A
Temperature Range | Switch | ✓ | Low, High

Option | Tested
------ | ------
Entities polling rate (seconds) | Not yet implemented!
Time sync with Home Assistant | ✓

✓ = Tested and working properly  
? = Need your help to validate if this working properly (I don't have these options on my spa)

## Task List

### To do

- [ ] Bring back the ability to configure this custom component via the entries in configuration.yaml
- [ ] Change the way I update entities (from polling mode to subscribing to updates)

### Completed

- [x] Add programming capability for filter cycles
- [x] Allow the installation of this custom component through HACS
- [x] Allow the installation of this custom component through the Home Assistant integrations menu (use of config_flow.py)
- [x] Create an icon and logo for this custom component
- [x] Customize entity IDs with **Spa Client** custom name to allow multiple integrations in the same Home Assistant instance
- [x] Implement the other spa messages (fault log, gfi test, etc.)
- [x] Investigate why it takes so long to load the component on an RPi (~2s on docker; ~85s on RPi3)
- [x] Manage the availability of entities while not connected

## Inspiration / Credits

- https://github.com/jmoor3/homeassistant-components | Forked project, initial inspiration!
- https://github.com/ccutrer/balboa_worldwide_app/wiki | Detailed Wiki on bwa protocol.
- https://github.com/garbled1/pybalboa | Main program in Python to interface the bwa module. Source of the CRC function. Very well programmed and documented!
- https://github.com/garbled1/balboa_homeassistan | Balboa Spa Client integration for Home Assistant which sit on previous ```pybalboa``` main program.
- https://github.com/vincedarley/homebridge-plugin-bwaspa | Homebridge Balboa Spa Plugin.
