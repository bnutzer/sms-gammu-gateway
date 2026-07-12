# REST API SMS Gateway using gammu

Simple SMS REST API gateway for sending and receiving SMS from gammu-supported devices. Gammu speaks the standard AT commands used by most USB GSM modems.

This repository contains a fork of [Pavel Sklenář's sms-gammu-gateway](https://github.com/pajikos/sms-gammu-gateway). Thank you very much for your code! It is much appreciated.
This repo contains a number of new configuration options, mostly related to running sms-gammu-gateway in docker containers.

![Docker image build](https://img.shields.io/github/actions/workflow/status/bnutzer/sms-gammu-gateway/docker_image.yml?logo=github&label=docker%20image)
![Docker pulls](https://img.shields.io/docker/pulls/bnutzer/sms-gammu-gateway.svg?logo=docker)
![Docker image size](https://img.shields.io/docker/image-size/bnutzer/sms-gammu-gateway.svg?logo=docker)
![License](https://img.shields.io/github/license/bnutzer/sms-gammu-gateway.svg)


## Quick start

If your GSM modem speaks AT commands (most USB sticks do), the fastest way to
try the gateway is Docker. Credentials are mandatory — there are no built-in
defaults:

```bash
docker run -d -p 5000:5000 \
  -e AUTH_USERNAME=admin -e AUTH_PASSWORD=changeme \
  --device=/dev/ttyUSB0:/dev/mobile bnutzer/sms-gammu-gateway
```

Then send your first SMS:

```bash
AUTH=$(echo -ne "admin:changeme" | base64 --wrap 0)
curl -H 'Content-Type: application/json' -H "Authorization: Basic $AUTH" \
  -X POST --data '{"text":"Hello, how are you?", "number":"+420xxxxxxxxx"}' \
  http://localhost:5000/sms
```

See [Usage](#usage) for standalone installation, docker-compose, credentials
and HTTPS, and the [REST API reference](#rest-api-endpoints) for all endpoints.


## Table of contents

- [Quick start](#quick-start)
- [Usage](#usage)
  - [Credentials are required](#credentials-are-required)
  - [Prerequisites](#prerequisites)
  - [Standalone installation](#standalone-installation)
  - [Running in Docker](#running-in-docker)
  - [Verbosity and dry runs](#verbosity-and-dry-runs)
- [REST API endpoints](#rest-api-endpoints)
- [Integration with Home Assistant](#integration-with-home-assistant)
- [FAQ](#faq)


# Usage

There are two ways to run this REST API SMS gateway:
* Standalone installation
* Running in Docker

## Credentials are required

All SMS endpoints (and `/reset`) are protected by HTTP Basic authentication,
and **the gateway refuses to start until you configure credentials** — there
are no built-in defaults. Set them in either of two ways:

* **Environment variables** (recommended, especially for Docker): set
  `AUTH_USERNAME` and `AUTH_PASSWORD`.
* **Credentials file**: provide a `credentials.txt` in the working directory
  (`/sms-gw/credentials.txt` in the container) with one `user:password` per
  line. This file is deliberately not part of the image.

Both sources can be combined; environment variables take precedence. Because
HTTP Basic transmits the password in clear text, enable HTTPS (`SSL=True`,
see the FAQ) whenever the gateway is reachable over an untrusted network.

## Prerequisites
Whether you use Docker or a standalone installation, your GSM modem must be visible to the system.
When you plug a USB stick into your system, a new USB device should appear:
```
dmesg | grep ttyUSB
```
or by running:
```
lsusb
```
```
...
Bus 001 Device 009: ID 12d1:1406 Huawei Technologies Co., Ltd. E1750
...
```
If only a CD-ROM device appears, install [usb-modeswitch](http://www.draisberghof.de/usb_modeswitch) so the modem shows up as well:
```
apt-get install usb-modeswitch
```

By default, sms-gammu-gateway will listen on all interfaces and IPv4
addresses (or, more precisely, on 0.0.0.0). You can listen on local
(or other sets of) addresses only by setting the BINDHOST environment
variable, e.g. either using appropriate docker settings, or in/from the
executing shell.

## Standalone installation
This guide does not cover installing Python 3.x (including pip), which is required as well.
#### Install system dependencies (using apt):
```
apt-get update && apt-get install -y pkg-config gammu libgammu-dev libffi-dev
```
#### Clone repository
```
git clone https://github.com/bnutzer/sms-gammu-gateway
cd sms-gammu-gateway
```
#### Install python dependencies
```
pip install -r requirements.txt
```
#### Edit gammu configuration
You usually only need to edit the device property in the [gammu.config](https://wammu.eu/docs/manual/config/index.html) file, e.g.:
```
[gammu]
device = /dev/ttyUSB1
connection = at
```
#### Run application (it will start to listen on port 5000):
Credentials are mandatory (see [above](#credentials-are-required)); provide
them via a `credentials.txt` or environment variables:
```
AUTH_USERNAME=admin AUTH_PASSWORD=changeme python run.py
``` 

## Running in Docker
If your GSM device supports AT commands, you can simply run the
container. Credentials are mandatory (see
[above](#credentials-are-required)) — pass them as environment variables:
```
docker run -d -p 5000:5000 \
  -e AUTH_USERNAME=admin -e AUTH_PASSWORD=changeme \
  --device=/dev/ttyUSB0:/dev/mobile bnutzer/sms-gammu-gateway
```
#### Docker compose:
```
version: '3'
services:
  sms-gammu-gateway:
    container_name: sms-gammu-gateway
    restart: always
    image: bnutzer/sms-gammu-gateway
    environment:
      - PIN="1234"
      - AUTH_USERNAME=admin
      - AUTH_PASSWORD=changeme
    ports:
      - "5000:5000"
    devices:
      - /dev/ttyUSB1:/dev/mobile
```

Inside the container gammu always talks to the fixed device path
`/dev/mobile`. Map your host modem onto it via the `--device` flag (or the
`devices:` entry in docker-compose), as shown above.

## Verbosity and dry runs

By passing the flag `--verbose` to the program, logging of sent and received
messages can be enabled. Please be aware that this information can include
sensitive data. Only activate the flag after restricting access to the data
using an appropriate setup.

The flag `--dry` can be used to prevent sending and deleting actual SMS. This
can be handy for testing and debugging purposes.

Simply append the flags to your command line; this works well for the docker
setup as well. In case of a docker compose setup, add a configuration statement
`command: --verbose`.


# REST API endpoints

- ##### Send a SMS :lock:
  ```
  POST http://xxx.xxx.xxx.xxx:5000/sms
  Content-Type: application/json
  Authorization: Basic admin password
  {
    "text": "Hello, how are you?",
    "number": "+420xxxxxxxxx"
  }
  ```
  Example:
  ```bash
  AUTH=$(echo -ne "admin:password" | base64 --wrap 0)
  curl -H 'Content-Type: application/json' -H "Authorization: Basic $AUTH" -X POST --data '{"text":"Hello, how are you?", "number":"+420xxxxxxxxx"}' http://localhost:5000/sms
  1
  ```
  If you need to customize the smsc number:
  ```bash
  curl -H 'Content-Type: application/json' -H "Authorization: Basic $AUTH" -X POST --data '{"text":"Hello, how are you?", "number":"+420xxxxxxxxx","smsc": "+33695000695"}' http://localhost:5000/sms
  ```
- ##### Retrieve all the SMS stored on the modem/SIM Card :lock:
  ```
  GET http://xxx.xxx.xxx.xxx:5000/sms
  ```
  ```json
  [
    {
      "Date": "2021-02-17 15:20:20",
      "Number": "+xxxxxxxxxxx",
      "State": "UnRead",
      "Text": "Hello"
    },
    ...
  ]
  ```

- ##### Retrieve {n}th message stored on the modem/SIM Card :lock:
  ```
  GET http://xxx.xxx.xxx.xxx:5000/sms/{n}
  ```
  ```json
  {
    "Date": "2021-02-17 15:20:20",
    "Number": "+xxxxxxxxxxx",
    "State": "UnRead",
    "Text": "Hello"
  }
  ```

- ##### Delete {n}th message stored on the modem/SIM Card :lock:
  ```
  DELETE http://xxx.xxx.xxx.xxx:5000/sms/{n}
  ```

- ##### Retrieve 1st message stored on the modem/SIM Card and delete it :lock:
  ```
  GET http://xxx.xxx.xxx.xxx:5000/getsms
  ```
  ```json
  {
    "Date": "2021-02-17 15:20:20",
    "Number": "+xxxxxxxxxxx",
    "State": "UnRead",
    "Text": "Hello"
  }
  ```

- ##### Get the current signal strength :unlock: 
  ```
  GET http://xxx.xxx.xxx.xxx:5000/signal
  ```
  ```json
  {
    "SignalStrength": -83, 
    "SignalPercent": 45, 
    "BitErrorRate": -1
  }
  ```

- ##### Get the current network details :unlock: 
  ```
  GET http://xxx.xxx.xxx.xxx:5000/network
  ```
  ```json
  {
    "NetworkName": "DiGi",
    "State": "RoamingNetwork",
    "PacketState": "RoamingNetwork",
    "NetworkCode": "502 16",
    "CID": "00A18B30",
    "PacketCID": "00A18B30",
    "GPRS": "Attached",
    "PacketLAC": "7987",
    "LAC": "7987"
  }
  ```

- ##### Reset the modem (see FAQ for more info) :lock:
  ```
  GET http://xxx.xxx.xxx.xxx:5000/reset
  ```
  ```json
  {
    "Status": 200,
    "Message": "Reset done"
  }
  ```


# Integration with Home Assistant

The gateway exposes plain REST endpoints, so Home Assistant can talk to it
with its built-in `rest` integrations — no custom component required. The
snippets below add a signal-strength sensor, an SMS `notify` service, a sensor
that polls for incoming messages, and a couple of example automations.

You can paste each block straight into your `configuration.yaml`, but keeping
all of the gateway's configuration together in its own
[package](https://www.home-assistant.io/docs/configuration/packages/) is
cleaner and easier to maintain. To use a package, enable package loading once
in `configuration.yaml`:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

then create `packages/sms-gammu-gateway.yaml` and put the blocks below into it.
A few things to keep in mind:

* Replace `xxx.xxx.xxx.xxx` with the host and port of your gateway.
* Store the credentials as `sms_gateway_username` and `sms_gateway_password`
  in your `secrets.yaml`, so they are not spread across your configuration.
* Home Assistant allows each domain key (`sensor:`, `notify:`, …) only once
  per file. When you combine several blocks below, merge their entries under a
  single key — e.g. put both the signal-strength and the incoming-message
  sensor into one `sensor:` list.

#### Signal Strength sensor
```yaml
sensor:
  - platform: rest
    resource: http://xxx.xxx.xxx.xxx:5000/signal
    name: GSM Signal
    scan_interval: 30
    value_template: '{{ value_json.SignalPercent }}'
    unit_of_measurement: '%'
```

#### SMS notification
```yaml
notify:
  - name: SMS GW
    platform: rest
    resource: http://xxx.xxx.xxx.xxx:5000/sms
    method: POST_JSON
    authentication: basic
    username: !secret sms_gateway_username
    password: !secret sms_gateway_password
    target_param_name: number
    message_param_name: text
```

#### Using in Automation
```yaml
- alias: Alarm Entry Alert - Garage Door
  trigger:
    platform: state
    entity_id: binary_sensor.garage_door
    state: 'on'
  condition:
    - platform: state
      entity_id: alarm_control_panel.alarm
      state: 'armed_home'
  action:
    service: notify.sms_gw
    data:
      message: 'alert, entry detected at garage door'
      target: '+xxxxxxxxxxxx'
```

#### Receiving SMS and sending notification

```yaml
sensor:
  - platform: rest
    resource: http://127.0.0.1:5000/getsms
    name: sms
    scan_interval: 20
    username: !secret sms_gateway_username
    password: !secret sms_gateway_password
    json_attributes:
      - Date
      - Number
      - Text
      - State

automation sms_automations:
  - alias: Notify on received SMS
    trigger:
      - platform: template
        value_template: "{{state_attr('sensor.sms', 'Text') != ''}}"
    action:
      - service: notify.mobile_app_[DEVICE]
        data:
          title: SMS from {{ state_attr('sensor.sms', 'Number') }}
          message: "{{ state_attr('sensor.sms', 'Text') }}"
          data:
            sticky: "true"
      - service: persistent_notification.create
        data:
          title: SMS from {{ state_attr('sensor.sms', 'Number') }}
          message: "{{ state_attr('sensor.sms', 'Text') }}"
```


# FAQ
#### PIN configuration
The PIN to unlock the SIM card can be set via the PIN environment variable, e.g. PIN=1234.
#### Authentication
The SMS endpoints and `/reset` require HTTP Basic authentication. See
[Credentials are required](#credentials-are-required) for how to configure
username and password.
#### How to use HTTPS?
For production, the recommended way to serve the gateway over HTTPS is to put a
reverse proxy (nginx, Traefik, Caddy, …) in front of it and let the proxy
terminate TLS and manage certificates. Leave `SSL` disabled in that setup: the
gateway is then served by [waitress](https://github.com/Pylons/waitress), a
production-grade WSGI server, over plain HTTP behind the proxy.

For small setups without a reverse proxy you can still let the gateway
terminate TLS itself by setting the environment variable `SSL=True`. In that
mode it falls back to Flask's built-in Werkzeug server (waitress cannot
terminate TLS) and expects an RSA private key and certificate. The expected
file paths (which you can change in run.py or override by mounting your own
key/cert in Docker) are:
```
/ssl/key.pem
/ssl/cert.pem
```
#### Change default port
Set the port via the PORT environment variable, e.g. PORT=5002. Don't forget to adjust the port exposure of your container accordingly.

#### No more modem response?
If your modem regularly runs into problems and you don't want to physically disconnect and reconnect it to reset it, you can call the reset function on a schedule.
(For example with my Huawei modem the reset function is used every 24 hours to maintain the stability of the system)

#### It does not work...
Try to check [gammu configuration file site](https://wammu.eu/docs/manual/config/index.html)
