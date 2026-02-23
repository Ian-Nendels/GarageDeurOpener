import uasyncio as asyncio
from lib.WiFi import Network
import json
from time import sleep
import usyslog
import motor

# Constants for MQTT Topics
MQTT_TOPIC_BUTTON = 'domoticz/out/GarageDeurOpener'
MQTT_TOPIC_WATCHDOG = 'domoticz/out/GarageDeurWatchDogIn'
MQTT_TOPIC_IN = 'domoticz/in'

class WatchDogData():
    Read = 0
    Send = 0
    FaultCounter = 0

class mqttServer():
    isConnected = False
    Subscribe = False
    SubscribeWD = False

class ping():
    FirstRun = False
    started  = False
    response = False
    counter = 0
    
class config():
    # MQTT Parameters
    MQTT_SERVER = b'192.168.178.20'
    MQTT_PORT = 1883
    MQTT_USER = b'domoticz'
    MQTT_PASSWORD = b'd0mot!cz'
    MQTT_CLIENT_ID = b"pico_garage"
    MQTT_KEEPALIVE = 120
    MQTT_SSL = False   # set to False if using local Mosquitto MQTT broker
    MQTT_SSL_PARAMS = {'server_hostname': MQTT_SERVER}
    MQTT_PING_INTERVAL = 60
    SYSLOG_SERVER_IP = '192.168.178.20'

logger = usyslog.UDPClient(ip=config.SYSLOG_SERVER_IP, facility=usyslog.F_LOCAL4)

def CreateDomoticzString(idx, data):
    message = '{ "idx" : ' + str(idx) + ', "nvalue" : '+ str(data) + ' }'
    return message

def CreateDomoticzValue(idx, data):
    message = '{ "command":"udevice","idx":' + str(idx) + ',"nvalue":0,"svalue":"'+ str(data) + '" }'
    return message

async def subscribeButton(client, topic):
    while True:
        while not mqttServer.Subscribe:
            await asyncio.sleep(0.1)
        client.subscribe(topic)
        msg = 'Subscribe to topic:' + topic
        print(msg)
        logger.info('LOCAL4:' + msg)
        mqttServer.Subscribe = False
        mqttServer.isConnected = True
        await asyncio.sleep(1)

async def subscribeWatchdog(client, topic):
    while True:
        while not mqttServer.SubscribeWD:
            await asyncio.sleep(0.1)
        client.subscribe(topic)
        msg = 'Subscribe to topic:' + topic
        print(msg)
        logger.info('LOCAL4:' + msg)
        mqttServer.SubscribeWD = False
        await asyncio.sleep(1)

def my_callback(topic, message):
    # Perform desired actions based on the subscribed topic and response
    print('Received message on topic:', str(topic))
    parsed = json.loads(message)
    name = parsed["name"]
    if name == 'GarageDeurOpener':
        value = int(parsed["nvalue"])
        if value == 1:
            motor.Garagedeur.RemoteDrukKnop = 'Open'
        if value == 0:
            motor.Garagedeur.RemoteDrukKnop = 'Dicht'
        msg = "Remote Drukknop = " + str(motor.Garagedeur.RemoteDrukKnop)
        print(msg)
        logger.info('LOCAL4:' + msg)
    if name == 'GarageDeurWatchDogIn':
        value = int(parsed["svalue1"])
        WatchDogData.Read = value
    sleep(0.1)

async def connect_mqtt(client):
    while True:
        try:
            while mqttServer.isConnected:
                await asyncio.sleep(0.1)
            if Network.wlan.isconnected():
                print("Connect to MQTT Server")
                logger.info('LOCAL4:Connect to MQTT Server')
                res = client.connect()
                mqttServer.Subscribe = True
                mqttServer.SubscribeWD = True
            await asyncio.sleep(1)
        except Exception as e:
            msg = "connect_mqtt loop error: {str(e)}"
            logger.error('LOCAL4:' + msg)
            await asyncio.sleep(1)

async def ping_mqtt(client):
    while True:
        try:
            if ping.FirstRun:
                ping.response = False
            if (ping.counter > 0):
                interval = 5
                msg = "ping interval op 5 sec, ping counter = " + str(ping.counter)
                logger.warn('LOCAL4:' + msg)
            else:
                interval = config.MQTT_PING_INTERVAL
            if Network.wlan.isconnected():
                if ping.FirstRun:
                    #print("Sending Ping Request")
                    client.ping()
                    ping.started = True
                    ping.counter += 1
                else:
                    ping.FirstRun = True
                    ping.response = True
            await asyncio.sleep(interval)
        except Exception as e:
            msg = "ping_mqtt loop error: {str(e)}"
            logger.error('LOCAL4:' + msg)
            await asyncio.sleep(2)


async def check_mqtt_msg(client):
    while True:
        try:
            if Network.wlan.isconnected() and mqttServer.isConnected:
                msg = client.check_msg()
                if(msg == b"PINGRESP"):
                    ping.counter = 0
                    ping.response = True
                    #print("Ping Responce Recieved")
                if ping.started:
                    ping.started = False
                    if (ping.counter > 5):
                        mqttServer.isConnected = False
                        logger.warn('LOCAL4:5x geen ping response, mqttServer disconnected')
            await asyncio.sleep(0.1)
        except Exception as e:
            msg = "check_mqtt_msg loop error: {str(e)}"
            logger.error('LOCAL4:' + msg)
            await asyncio.sleep(2)


        
#CoRoutine: Waiting for RemoteButton coming from mqtt
async def RemoteButtonPress():
    while True:
        while (motor.Garagedeur.RemoteDrukKnop == 'Neutraal'):
            await asyncio.sleep(0.1)
        if motor.Garagedeur.Richting != 'stil':
            if (motor.Garagedeur.RemoteDrukKnop == 'Dicht' and motor.Garagedeur.Richting == 'omlaag') or (motor.Garagedeur.RemoteDrukKnop == 'Open' and motor.Garagedeur.Richting == 'omhoog'):
                motor.Garagedeur.StartMotor = True
                print("Remote Button Pressed to stop Motor")
                await asyncio.sleep(1)
        else:
            if (motor.Garagedeur.RemoteDrukKnop == 'Dicht' and motor.Garagedeur.DichtSensor == True) or (motor.Garagedeur.RemoteDrukKnop == 'Open' and not motor.Garagedeur.Positie > 870):
                motor.Garagedeur.StartMotor = True
                print("Remote Button Pressed")
                await asyncio.sleep(1)
            else:
                motor.Garagedeur.RemoteDrukKnop = 'Neutraal'
        while motor.Garagedeur.RemoteDrukKnop != 'Neutraal':
            await asyncio.sleep(1)
        await asyncio.sleep(0.1)
