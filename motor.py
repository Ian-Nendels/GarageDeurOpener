import machine
import uasyncio as asyncio
from lib import usyslog
import mqtt

logger = usyslog.UDPClient(ip=mqtt.config.SYSLOG_SERVER_IP, facility=usyslog.F_LOCAL4)

encoderA = machine.Pin(4 , machine.Pin.IN)
encoderB = machine.Pin(5 , machine.Pin.IN)

class Garagedoor():
    Direction        : str  = 'stopped'
    RemotePushButton : str  = 'Neutral'
    MemPushButton    : bool = False
    ClosedSensor     : bool = False
    StartMotor       : bool = False
    Position         : int  = 0
    LastPosition     : int  = 0

def ScaleOpening(input):
    factor = 210 / 878
    return '%.1f' % (input * factor)

async def Encoder():
    MemPuls = False
    while True:
        while bool(encoderA.value()) == MemPuls:
            await asyncio.sleep(0.001)
        if bool(encoderA.value()):
            if not bool(encoderB.value()):
                Garagedoor.Position += 1
            else:
                Garagedoor.Position -= 1
            await asyncio.sleep(0.001)
        else:
            await asyncio.sleep(0.001)
        MemPuls = bool(encoderA.value())

async def MotorDirection(client, Topic):
    lasttime = True
    while True:
        try:
            while Garagedoor.LastPosition == Garagedoor.Position and lasttime:
                await asyncio.sleep(0.1)
            
            lasttime = False  
            if Garagedoor.Position > Garagedoor.LastPosition:
                Garagedoor.Direction = 'up'
            elif Garagedoor.Position < Garagedoor.LastPosition:
                Garagedoor.Direction = 'down'
            else:
                Garagedoor.Direction = 'stopped'
            
            msg = mqtt.CreateDomoticzValue(1956, ScaleOpening(Garagedoor.Position))
            client.publish(Topic, msg)
            if Garagedoor.LastPosition == Garagedoor.Position:
                lasttime = True
            
            Garagedoor.LastPosition = Garagedoor.Position
            await asyncio.sleep(1)
        except Exception as e:
            msg = "MotorDirection loop error: {str(e)}"
            logger.error('LOCAL4:' + msg)
            await asyncio.sleep(1)


# Send periodic the doorposition to Domoticz
async def UpdatePosition(client, Topic):
    while True:
        try:
            await asyncio.sleep(300)
            msg = mqtt.CreateDomoticzValue(1956, ScaleOpening(Garagedoor.Position))
            client.publish(Topic, msg)
        except Exception as e:
            msg = "UpdatePosition loop error: {str(e)}"
            logger.error('LOCAL4:' + msg)


async def TurnAround(logger):
    while True:
        while Garagedoor.Direction == 'stopped':
            await asyncio.sleep(0.5)
        if (Garagedoor.Direction == 'up' and Garagedoor.RemotePushButton == 'Close') or (Garagedoor.Direction == 'down' and Garagedoor.RemotePushButton == 'Open'):
            # only wait when the first puls is given
            while Garagedoor.StartMotor:
                #wait for first startpuls to finish then 2 and 3
                await asyncio.sleep(2)
            Garagedoor.StartMotor = True
            await asyncio.sleep(4)
            Garagedoor.StartMotor = True
            logger.info('LOCAL4:DoorCommand Turned')
        await asyncio.sleep(0.1)


