import machine
import _thread
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

WatchDogData.Read = 0
WatchDogData.Send = 0

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
    ErrorReset = 5
    while True:
        try:
            while not Network.wlan.isconnected() or not Network.Connected:
                await asyncio.sleep(1)
            if (WatchDogData.FaultCounter == ErrorReset):
                Network.Connected = False
                msg = "Network Reset by WatchDog error"
                print(msg)
                logger.info('LOCAL4:' + msg)
                WatchDogData.FaultCounter = 0
                WatchDogData.Read = WatchDogData.Send
                
            await asyncio.sleep(60) # Watchdog interval = 1 minute
            #logmsg = f'WatchDogData.Send: {WatchDogData.Send} WatchDogData.Read: {WatchDogData.Read}'    
            #print(logmsg)
            #logger.info('LOCAL4:' + logmsg)
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
                    
        except Exception as e:
            msg = "WatchDog loop error: " + str(e)
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
            TimeOut = 0    
            logmsg = "GarageDoor closed = " + str(Garagedoor.ClosedSensor)
            print(logmsg)
            logger.info('LOCAL4:' + logmsg)
            if Garagedoor.ClosedSensor:
                msg = mqtt.CreateDomoticzString(1742, 1)
                await asyncio.sleep(1)
            else:
                msg = mqtt.CreateDomoticzString(1742, 0)
                while Garagedoor.Direction != 'stopped' or TimeOut > 100:
                    TimeOut += 1
                    await asyncio.sleep(0.1)
                if TimeOut > 100:
                    logmsg = "TimeOut reached because Garagedoor direction = " + Garagedoor.Direction
                    logger.warning('LOCAL4:' + logmsg)
                Garagedoor.Position = 0
            client.publish(mqtt.MQTT_TOPIC_IN, msg)
            print("Publish: ", msg)
            await asyncio.sleep(1)
        except Exception as e:
            msg = "DoorSensorChange loop error: " + str(e)
            logger.error('LOCAL4:' + msg)
            await asyncio.sleep(1)
        
async def StartHormann():
    while True:
        while not Garagedoor.StartMotor:
            await asyncio.sleep(0.05)
        if not StartUp:
            hormann.value(0)
            await asyncio.sleep(1) # Door is started and stopped by a puls command
            hormann.value(1)
            logger.info('LOCAL4:DoorCommand activated')
        Garagedoor.StartMotor = False
        await asyncio.sleep(0.1)

async def SyncTime():
    # Sync Hardware Clock with NTP
    ntp.set_time()
    TimeArray = time.localtime()
    LocalTime = '{:02d}'.format(TimeArray[3]) + ":" + '{:02d}'.format(TimeArray[4]) + ":" + '{:02d}'.format(TimeArray[5])
    print('Local time = ' + LocalTime)
    logger.info('LOCAL4:Local time = ' + LocalTime)

def OtaUpdate():
    try:
        logger.info('LOCAL4:OTA Update Started.')
        # Check for OTA updates
        repo_name = "GarageDeurOpener"
        branch = "main"
        firmware_url = f"https://github.com/Ian-Nendels/{repo_name}/{branch}/"
        ota_updater = OTAUpdater(firmware_url, "main.py", "motor.py", "mqtt.py")
        ota_updater.download_and_install_update_if_available(logger)
    except Exception as e:
        msg = "OtaUpdate error: " + str(e)
        logger.error('LOCAL4:' + msg)

def core1_task():
    while not Network.wlan.isconnected() or not Network.Connected:
        time.sleep(1)
    OtaUpdate()

# Start the thread
_thread.start_new_thread(core1_task, ())

#CoRoutine: entry point for asyncio program
async def main():
    ping.FirstRun = False
    Network.FirstRunDone = False
    print("Program Start")
        
    # Start coroutine Connect WiFi and immediatly return
    asyncio.create_task(WiFi.Connect_Wifi())
    while not Network.wlan.isconnected() or not Network.Connected:
        await asyncio.sleep(1)
    SyncTime()
        
    logger.info('LOCAL4:Garagedoor opener Started.')
    
    # Connect to MQTT broker, start MQTT client
    client.set_callback(mqtt.my_callback)
    asyncio.create_task(mqtt.connect_mqtt(logger, Network, client))
    asyncio.create_task(mqtt.ping_mqtt(logger, Network, client))
    asyncio.create_task(mqtt.subscribeButton(logger, client, mqtt.MQTT_TOPIC_BUTTON))
    asyncio.create_task(mqtt.subscribeWatchdog(logger, client, mqtt.MQTT_TOPIC_WATCHDOG))
   
    await asyncio.sleep(2)
    
    if Network.wlan.isconnected() and Network.Connected:
        asyncio.create_task(mqtt.check_mqtt_msg(logger, Network, client))
        asyncio.create_task(WatchDog())
        asyncio.create_task(DoorSensorChange())
        asyncio.create_task(ButtonPress())
        asyncio.create_task(RemoteButtonPress(Garagedoor))
        asyncio.create_task(StartHormann())
        asyncio.create_task(TurnAround(logger))
        asyncio.create_task(MotorDirection(logger, mqtt, client, mqtt.MQTT_TOPIC_IN))
        asyncio.create_task(UpdatePosition(logger, mqtt, client, mqtt.MQTT_TOPIC_IN))
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

            # Every 10 minutes check OTA
            OtaTrigger = TimeArray[4] % 10
            if OtaTrigger == 0 and TimeArray[5] == 0:
                logger.info('LOCAL4:periodic OTA update is handled now')
                await asyncio.sleep(2)
                OtaUpdate()

            # daily at 0:05 sync time
            if  TimeArray[3] == 0 and TimeArray[4] == 5  and TimeArray[5] == 0:
                SyncTime()
                await asyncio.sleep(1)

        await asyncio.sleep(0.1)
        
# Start event loop and run entry point coroutine
#try:
asyncio.run(main())
#finally:
#    asyncio.new_event_loop()
