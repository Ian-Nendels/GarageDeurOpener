import machine
import uasyncio as asyncio
import time
from lib import usyslog
from lib import queue
from lib import WiFi
from lib.WiFi import Network
from lib.simple import MQTTClient
from lib.ota import OTAUpdater
import mqtt
from mqtt import config, WatchDogData, ping, mqttServer, RemoteButtonPress
from motor import Garagedeur, UpdatePosition, MotorDirection, OmDraaien, Encoder
import ntp

TimeArray = [ 2025, 1, 1, 0, 0, 0, 0, 0 ] 
# I/O punten Pico W
button     = machine.Pin(2 , machine.Pin.IN)
deursensor = machine.Pin(3 , machine.Pin.IN)
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

#logger = Logger("debug", "logfile.log")
logger = usyslog.UDPClient(ip=config.SYSLOG_SERVER_IP, facility=usyslog.F_LOCAL4)

StartUp = True

#CoRoutine: blink LED on a timer
async def blink():
    delay_ms = 100
    while True:
        if (False):    
            # Toggle Led State
            led.toggle()
        else:
            led.off()
        await asyncio.sleep_ms(delay_ms)

#CoRoutine: Watchdog with Domoticz
async def WatchDog():
    while True:
        try:
            await asyncio.sleep(60)
            if WatchDogData.Read == WatchDogData.Send:
                if WatchDogData.FaultCounter > 0:
                    msg = "Watchdog weer OKE"
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
                logger.info('LOCAL4:Reboot door WatchDog error')
                await asyncio.sleep(1)
                machine.reset()
        
            #print("Read: ", WatchDogData.Read, " Send: ", WatchDogData.Send)
        except Exception as e:
            msg = "WatchDog loop error: {str(e)}"
            logger.error('LOCAL4:' + msg)
            await asyncio.sleep(1)
        
#CoRoutine: Waiting for Button 
async def ButtonPress():
    while True:
        Garagedeur.MemDrukknop = bool(button.value())
        while (Garagedeur.MemDrukknop == bool(button.value()) or StartUp):
            await asyncio.sleep(0.05)
        Garagedeur.MemDrukknop = bool(button.value())
        if not bool(button.value()):
            Garagedeur.StartMotor = True
            print("Button Pressed")
        await asyncio.sleep(0.1)

#coroutine: Waiting for DeurSensor
async def DeurSensorChange():
    while True:
        try:
            while ((Garagedeur.DichtSensor == deursensor.value()) or StartUp):
                await asyncio.sleep(0.05)
            Garagedeur.DichtSensor = deursensor.value()
                
            logmsg = "GarageDeur dicht = " + str(Garagedeur.DichtSensor)
            print(logmsg)
            logger.info('LOCAL4:' + logmsg)
            if Garagedeur.DichtSensor:
                msg = mqtt.CreateDomoticzString(1742, 1)
                await asyncio.sleep(1)
            else:
                msg = mqtt.CreateDomoticzString(1742, 0)
                while Garagedeur.Richting != 'stil':
                    await asyncio.sleep(0.1)
                Garagedeur.Positie = 0
            client.publish(mqtt.MQTT_TOPIC_IN, msg)
            print("Publish: ", msg)
            await asyncio.sleep(1)
        except Exception as e:
            msg = "DeurSensorChange loop error: {str(e)}"
            logger.error('LOCAL4:' + msg)
            await asyncio.sleep(1)
        
async def StartHormann():
    while True:
        while not Garagedeur.StartMotor or not Network.wlan.isconnected():
            await asyncio.sleep(0.05)
        if not StartUp:
            hormann.value(0)
            #MotorData.StartPuls = True
            await asyncio.sleep(1)
            hormann.value(1)
            logger.info('LOCAL4:DeurCommando geschakeld')
        Garagedeur.StartMotor = False
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
        
    logger.info('LOCAL4:Garagdeur opener wordt opgestart.')
    # Sync Hardware Clock with NTP
    ntp.set_time()
    TimeArray = time.localtime()
    LocalTime = '{:02d}'.format(TimeArray[3]) + ":" + '{:02d}'.format(TimeArray[4]) + ":" + '{:02d}'.format(TimeArray[5])
    print('Lokale tijd = ' + LocalTime)
    logger.info('LOCAL4:Lokale tijd = ' + LocalTime)
   
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
        asyncio.create_task(DeurSensorChange())
        asyncio.create_task(ButtonPress())
        asyncio.create_task(RemoteButtonPress())
        asyncio.create_task(StartHormann())
        asyncio.create_task(OmDraaien(logger))
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
            if (Garagedeur.Richting =='omhoog' and Garagedeur.RemoteDrukKnop == 'Open') or (Garagedeur.Richting =='omlaag' and Garagedeur.RemoteDrukKnop == 'Dicht'):
                await asyncio.sleep(1)
                Garagedeur.RemoteDrukKnop = 'Neutraal'
                print('DeurCommando weer Neutraal')

            # Dagelijkse reboot om 02:30:00 uur
            if TimeArray[3] == 2 and TimeArray[4] == 30 and TimeArray[5] == 0:
                logger.info('LOCAL4:Dagelijkse Reboot wordt nu uitgevoerd')
                await asyncio.sleep(1)
                machine.reset()
            
        await asyncio.sleep(0.1)
        
# Start event loop and run entry point coroutine
try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()
