FROM arm64v8/python:3.13

ENV MQTT_CLIENT_NAME=emu2mqtt \
    MQTT_SERVER=localhost \
    MQTT_PORT=1883 \
    MQTT_USERNAME=none \
    MQTT_PW_FILE=none \
    MQTT_DISC_TOPIC=homeassistant \
    MQTT_STATUS_TOPIC=homeassistant/status \
    MQTT_QOS=0 \
    SERIAL_PORT=ttyACM0

WORKDIR /usr/src/app

COPY requirements.txt emu2mqtt.py ./
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

CMD python emu2mqtt.py --mqtt_client_name $MQTT_CLIENT_NAME --mqtt_server $MQTT_SERVER --mqtt_port $MQTT_PORT --mqtt_username $MQTT_USERNAME \
    --mqtt_pw_file $MQTT_PW_FILE --mqtt_disc_topic $MQTT_DISC_TOPIC --mqtt_status_topic $MQTT_STATUS_TOPIC --mqtt_qos $MQTT_QOS $SERIAL_PORT
