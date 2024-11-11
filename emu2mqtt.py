import paho.mqtt.client as mqtt
import serial
import time
import logging
import xml.etree.ElementTree as ETree
import sys
import signal
import json
import argparse
import re

# Runtime globals
device_id = None
currently_online = False
initial_discovery = False

def on_sigint(sig, frame):
    logging.info("Caught a SIGINT, cleaning up and exiting")
    set_current_state(False)
    mqttc.loop_stop()
    mqttc.disconnect()
    time.sleep(4)
    sys.exit()

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action='store_true', help="enable debug logging", required=False)
    parser.add_argument("--mqtt_client_name", help="MQTT client name", required=False, type=str, default='emu2mqtt')
    parser.add_argument("--mqtt_server", help="MQTT server", required=False, type=str, default='localhost')
    parser.add_argument("--mqtt_port", help="MQTT server port", required=False, type=int, default=1883)
    parser.add_argument("--mqtt_username", help="MQTT username", required=False, type=str, default='')
    parser.add_argument("--mqtt_pw_file", help="MQTT password file", required=False, type=str, default='')
    parser.add_argument("--mqtt_disc_topic", help="MQTT discovery topic", required=False, type=str, default='homeassistant')
    parser.add_argument("--mqtt_status_topic", help="MQTT status topic", required=False, type=str, default='homeassistant/status')
    parser.add_argument("--mqtt_qos", help="MQTT QoS", required=False, type=int, choices=[0,1,2], default=0)
    parser.add_argument("serial_port", help="Rainforest EMU-2 serial port, e.g. 'ttyACM0'")
    return parser.parse_args()

def is_substr(desired: str, test: str) -> bool:
    i = 0
    while i < len(desired) and i < len(test):
        if desired[i] != test[i]:
            return False
        i += 1
    return True

def send_discovery():
    device_info = dict()
    device_info["name"] = "Rainforest EMU-2"
    device_info["manufacturer"] = "Rainforest Automation"
    device_info["model"] = "EMU-2"
    device_info["model_id"] = "EMU-2"
    device_info["identifiers"] = [device_id]

    config_info = dict()
    config_info["device_class"] = "energy"
    config_info["device"] = device_info
    #config_info["force_update"] = True
    config_info["name"] = "Cumulative Energy Delivered"
    config_info["state_class"] = "total"
    config_info["unit_of_measurement"] = "kWh"
    config_info["unique_id"] = f"{device_id}dlvr"
    config_info["value_template"] = "{{ value_json.delivered }}"
    config_info["state_topic"] = "rainforest/summationdelivered"
    config_info["availability_topic"] = "rainforest/status"

    serialized_config_info = json.dumps(config_info)
    # send discovery message for delivered power
    mqttc.publish(f"{args.mqtt_disc_topic}/sensor/emu2_delivered/config", serialized_config_info)

    config_info = dict()
    config_info["device_class"] = "energy"
    config_info["device"] = device_info
    #config_info["force_update"] = True
    config_info["name"] = "Cumulative Energy Received"
    config_info["state_class"] = "total"
    config_info["unit_of_measurement"] = "kWh"
    config_info["unique_id"] = f"{device_id}rcvd"
    config_info["value_template"] = "{{ value_json.received }}"
    config_info["state_topic"] = "rainforest/summationdelivered"
    config_info["availability_topic"] = "rainforest/status"

    serialized_config_info = json.dumps(config_info)
    # send discovery message for received power
    mqttc.publish(f"{args.mqtt_disc_topic}/sensor/emu2_received/config", serialized_config_info)

    config_info = dict()
    config_info["device_class"] = "power"
    config_info["device"] = device_info
    #config_info["force_update"] = True
    config_info["name"] = "Power"
    config_info["state_class"] = "measurement"
    config_info["unit_of_measurement"] = "kW"
    config_info["unique_id"] = f"{device_id}pwr"
    config_info["state_topic"] = "rainforest/instantaneousdemand"
    config_info["availability_topic"] = "rainforest/status"

    serialized_config_info = json.dumps(config_info)
    # send discovery message for instantaneous power
    mqttc.publish(f"{args.mqtt_disc_topic}/sensor/emu2_power/config", serialized_config_info)

def on_homeassistant_status(client, userdata, message):
    # if status changes to online, send device discovery
    if str(message.payload, encoding="utf8") == "online":
        send_discovery()

def on_connected(client, userdata, flags, reason_code):
    if reason_code == 0:
        logging.info("MQTT connected!")

def set_current_state(new_state: bool):
    global currently_online
    if currently_online != new_state:
        status = "online" if new_state else "offline"
        logging.info(f"State switching to {status}")
        mqttc.publish("rainforest/status", status, args.mqtt_qos)
        currently_online = new_state

def send_update(data: str):
    global device_id
    logging.debug("Parsing: " + data)
    try:
        xml = ETree.fromstring(data)
    except:
        logging.exception("failed to parse XML: " + data)
        return

    if xml.tag == "InstantaneousDemand":
        set_current_state(True)
        device_id = xml.find("DeviceMacId").text
        demand = int(xml.find("Demand").text, 16)
        multiplier = int(xml.find("Multiplier").text, 16)
        divisor = int(xml.find("Divisor").text, 16)
        digitsRight = int(xml.find("DigitsRight").text, 16)
        if divisor != 0:
                mqttc.publish(
                    "rainforest/instantaneousdemand",
                    str(round(demand * multiplier / divisor, digitsRight)),
                    args.mqtt_qos)
    elif xml.tag == "CurrentSummationDelivered":
        set_current_state(True)
        device_id = xml.find("DeviceMacId").text
        multiplier = int(xml.find("Multiplier").text, 16)
        divisor = int(xml.find("Divisor").text, 16)
        delivered = int(xml.find("SummationDelivered").text, 16)
        delivered *= multiplier
        delivered /= divisor

        received = int(xml.find("SummationReceived").text, 16)
        received *= multiplier
        received /= divisor
        data = {"delivered":delivered, "received":received}

        mqttc.publish("rainforest/summationdelivered", json.dumps(data), args.mqtt_qos)
    elif xml.tag == "ConnectionStatus":
        device_id = xml.find("DeviceMacId").text
        if xml.find("Status").text == "Rejoining":
            set_current_state(False)


args = parse_arguments()
logging.basicConfig(
    level=('DEBUG' if args.debug else 'INFO'),
    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logging.info("emu2mqtt loading...")
signal.signal(signal.SIGINT, on_sigint)
if args.mqtt_pw_file:
    pw_file = open(args.mqtt_pw_file, "r")
    mqtt_password = pw_file.read()
else:
    mqtt_password = ''
conn = serial.Serial(f"/dev/{args.serial_port}", 115200, timeout=1)
mqttc = mqtt.Client(args.mqtt_client_name)
mqttc.enable_logger()
mqttc.username_pw_set(args.mqtt_username, mqtt_password)
mqttc.message_callback_add(args.mqtt_status_topic, on_homeassistant_status)
mqttc.on_connect = on_connected
mqttc.will_set("rainforest/status", "offline", args.mqtt_qos)
mqttc.connect(args.mqtt_server, args.mqtt_port, 15)
logging.info("MQTT connecting...")

mqttc.loop_start()
mqttc.subscribe(args.mqtt_status_topic, args.mqtt_qos)

data = ""
tag = ""
is_parsing_message = False
while True:
    if conn.in_waiting > 0:
        try:
            data += conn.read(conn.in_waiting).decode("utf-8")
        except:
            logging.exception("failed to decode")
            continue
        message = ""
        partial_tag = ""
        for line in data.splitlines(keepends=True):
            if is_parsing_message:
                if re.match(tag, line):
                    logging.debug("tag end: " + tag)
                    is_parsing_message = False
                    message += line
                    send_update(message)
                else:
                    message += line
            else:
                m = re.match("<(?P<tag>InstantaneousDemand|CurrentSummationDelivered|ConnectionStatus)>", line)
                if m != None:
                    tag = f"</{m.group('tag')}>"
                    logging.debug("Tag start: " + line.strip())
                    is_parsing_message = True
                    message = line
                elif is_substr("<InstantaneousDemand>", line) or is_substr("<CurrentSummationDelivered>", line) or is_substr("<ConnectionStatus>", line):
                    logging.debug("Partial tag: " + line)
                    partial_tag = line
                    time.sleep(0.05)

        if is_parsing_message:
            # There's a partially collected message; save for the next iteration
            logging.debug("partial msg: " + message)
            data = message
            time.sleep(0.05)
        else:
            # If there was a partial tag at the end of the data, store it for the next iteration
            # otherwise, this will just assign empty string and clear junk from `data`
            data = partial_tag

        if not initial_discovery and device_id != None:
            send_discovery()
            initial_discovery = True
    else:
        time.sleep(0.25)
