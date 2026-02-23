import machine
import uasyncio as asyncio
import time
from lib import usyslog
from lib import ntp
from lib import WiFi
from lib.WiFi import Network
from lib.simple import MQTTClient
from lib.ota import OTAUpdater
import mqtt
from mqtt import config, WatchDogData, ping, mqttServer, RemoteButtonPress
from motor import Garagedoor, UpdatePosition, MotorDirection, TurnAround, Encoder

StartUp = True
TimeArray = [ 2025, 1, 1, 0, 0, 0, 0, 0 ] 

# I/O points Pico W
button     = machine.Pin(2 , machine.Pin.IN)
doorsensor = machine.Pin(3 , machine.Pin.IN)
hormann    = machine.Pin(16, machine.Pin.OUT, value=1)
led        = machine.Pin("LED", machine.Pin.OUT)

# MQTT Client Initialisation
client = MQTTClient(client_id=config.MQTT_CLIENT_ID,
                       server=config.MQTT_SERVER,
                         port=config.MQTT_PORT,
                         user=config.MQTT_USER,
                     password=config.MQTT_PASSWORD,
                    keepalive=config.MQTT_KEEPALIVE,
                          ssl=config.MQTT_SSL,
                   ssl_params=config.MQTT_SSL_PARAMS)

# Initialise connection to syslog server
logger = usyslog.UDPClient(ip=config.SYSLOG_SERVER_IP, facility=usyslog.F_LOCAL4)

#CoRoutine: Watchdog with Domoticz
async def WatchDog():
    while True:
        try:
            await asyncio.sleep(60) # Watchdog interval = 1 minute
            if WatchDogData.Read == WatchDogData.Send:
                if WatchDogData.FaultCounter > 0:
                    msg = "Watchdog connection is alive"
                    logger.info('LOCAL4:' + msg)
                    WatchDogData.FaultCounter = 0
                
                WatchDogData.Send = WatchDogData.Read + 1
                msg = mqtt.CreateDomoticzValue(1955, WatchDogData.Send)
                client.publish(mqtt.MQTT_TOPIC_IN, msg)
            else:
                WatchDogData.FaultCounter = WatchDogData.FaultCounter + 1
                msg = "Watchdog Fault Counter = " + str(WatchDogData.FaultCounter)
                print(msg)
                logger.info('LOCAL4:' + msg)
                msg = mqtt.CreateDomoticzValue(1955, WatchDogData.Send)
                client.publish(mqtt.MQTT_TOPIC_IN, msg)
            if WatchDogData.FaultCounter > 4:
                logger.info('LOCAL4:Reboot caused by WatchDog error')
                await asyncio.sleep(1)
                machine.reset()
        
        except Exception as e:
            msg = "WatchDog loop error: {str(e)}"
            logger.error('LOCAL4:' + msg)
            await asyncio.sleep(1)
        
#CoRoutine: Waiting for Button 
async def ButtonPress():
    while True:
        Garagedoor.MemPushButton = bool(button.value())
        while (Garagedoor.MemPushButton == bool(button.value()) or StartUp):
            await asyncio.sleep(0.05)
        Garagedoor.MemPushButton = bool(button.value())
        if not bool(button.value()):
            Garagedoor.StartMotor = True
            print("Button Pressed")
        await asyncio.sleep(0.1)

#coroutine: Waiting for DoorSensor
async def DoorSensorChange():
    while True:
        try:
            while ((Garagedoor.ClosedSensor == doorsensor.value()) or StartUp):
                await asyncio.sleep(0.05)
            Garagedoor.ClosedSensor = bool(doorsensor.value())
                
            logmsg = "GarageDoor closed = " + str(Garagedoor.ClosedSensor)
            print(logmsg)
            logger.info('LOCAL4:' + logmsg)
            if Garagedoor.ClosedSensor:
                msg = mqtt.CreateDomoticzString(1742, 1)
                await asyncio.sleep(1)
            else:
                msg = mqtt.CreateDomoticzString(1742, 0)
                while Garagedoor.Direction != 'stil':
                    await asyncio.sleep(0.1)
                Garagedoor.Position = 0
            client.publish(mqtt.MQTT_TOPIC_IN, msg)
            print("Publish: ", msg)
            await asyncio.sleep(1)
        except Exception as e:
            msg = "DoorSensorChange loop error: {str(e)}"
            logger.error('LOCAL4:' + msg)
            await asyncio.sleep(1)
        
async def StartHormann():
    while True:
        while not Garagedoor.StartMotor or not Network.wlan.isconnected():
            await asyncio.sleep(0.05)
        if not StartUp:
            hormann.value(0)
            await asyncio.sleep(1) # Door is started and stopped by a puls command
            hormann.value(1)
            logger.info('LOCAL4:DoorCommand activated')
        Garagedoor.StartMotor = False
        await asyncio.sleep(0.1)

#CoRoutine: entry point for asyncio program
async def main():
    ping.FirstRun = False
    Network.FirstRun = False
    print("Program Start")
        
    # Start coroutine Connect WiFi and immediatly return
    asyncio.create_task(WiFi.Connect_Wifi())
    while not Network.wlan.isconnected():
        await asyncio.sleep(1)
        
    logger.info('LOCAL4:Garagedoor opener Started.')
    # Sync Hardware Clock with NTP
    ntp.set_time()
    TimeArray = time.localtime()
    LocalTime = '{:02d}'.format(TimeArray[3]) + ":" + '{:02d}'.format(TimeArray[4]) + ":" + '{:02d}'.format(TimeArray[5])
    print('Local time = ' + LocalTime)
    logger.info('LOCAL4:Local time = ' + LocalTime)
   
    # Check for OTA updates
    repo_name = "GarageDeurOpener"
    branch = "main"
    firmware_url = f"https://github.com/Ian-Nendels/{repo_name}/{branch}/"
    ota_updater = OTAUpdater(firmware_url, "main.py", "motor.py", "mqtt.py")
    ota_updater.download_and_install_update_if_available()


    
    # Connect to MQTT broker, start MQTT client
    client.set_callback(mqtt.my_callback)
    asyncio.create_task(mqtt.connect_mqtt(client))
    asyncio.create_task(mqtt.ping_mqtt(client))
    asyncio.create_task(mqtt.subscribeButton(client, mqtt.MQTT_TOPIC_BUTTON))
    asyncio.create_task(mqtt.subscribeWatchdog(client, mqtt.MQTT_TOPIC_WATCHDOG))
   
    await asyncio.sleep(2)
    
    if Network.wlan.isconnected():
        asyncio.create_task(mqtt.check_mqtt_msg(client))
        asyncio.create_task(WatchDog())
        asyncio.create_task(DoorSensorChange())
        asyncio.create_task(ButtonPress())
        asyncio.create_task(RemoteButtonPress())
        asyncio.create_task(StartHormann())
        asyncio.create_task(TurnAround(logger))
        asyncio.create_task(MotorDirection(client, mqtt.MQTT_TOPIC_IN))
        asyncio.create_task(UpdatePosition(client, mqtt.MQTT_TOPIC_IN))
        asyncio.create_task(Encoder())
        
    # Main loop
    while True:
        global StartUp
        TimeArray = time.localtime()
        if StartUp:
            await asyncio.sleep(5)
            StartUp = False

        if Network.wlan.isconnected() and mqttServer.isConnected:
            if (Garagedoor.Direction =='up' and Garagedoor.RemotePushButton == 'Open') or (Garagedoor.Direction =='down' and Garagedoor.RemotePushButton == 'Close'):
                await asyncio.sleep(1)
                Garagedoor.RemotePushButton = 'Neutral'
                print('DoorCommand is Neutral')

            # Dagelijkse reboot om 02:30:00 uur
            if TimeArray[3] == 2 and TimeArray[4] == 30 and TimeArray[5] == 0:
                logger.info('LOCAL4:Daily reboot is handled now')
                await asyncio.sleep(1)
                machine.reset()
            
        await asyncio.sleep(0.1)
        
# Start event loop and run entry point coroutine
try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()
