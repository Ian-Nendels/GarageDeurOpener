import machine
import uasyncio as asyncio
import mqtt

#logger = usyslog.UDPClient(ip=mqtt.config.SYSLOG_SERVER_IP, facility=usyslog.F_LOCAL4)

encoderA = machine.Pin(4 , machine.Pin.IN)
encoderB = machine.Pin(5 , machine.Pin.IN)

class Garagedeur():
    Richting       = 'stil'
    RemoteDrukKnop = 'Neutraal'
    MemDrukknop    = False
    DichtSensor    = False
    StartMotor     = False
    Positie        = 0
    VorigePositie  = 0

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
                Garagedeur.Positie += 1
            else:
                Garagedeur.Positie -= 1
            await asyncio.sleep(0.001)
        else:
            await asyncio.sleep(0.001)
        MemPuls = bool(encoderA.value())

async def MotorDirection(client, Topic):
    lasttime = True
    while True:
        while Garagedeur.VorigePositie == Garagedeur.Positie and lasttime:
            await asyncio.sleep(0.1)
            
        lasttime = False  
        if Garagedeur.Positie > Garagedeur.VorigePositie:
            Garagedeur.Richting = 'omhoog'
        elif Garagedeur.Positie < Garagedeur.VorigePositie:
            Garagedeur.Richting = 'omlaag'
        else:
            Garagedeur.Richting = 'stil'
            
        msg = mqtt.CreateDomoticzValue(1956, ScaleOpening(Garagedeur.Positie))
        client.publish(Topic, msg)
        if Garagedeur.VorigePositie == Garagedeur.Positie:
            lasttime = True
            
        Garagedeur.VorigePositie = Garagedeur.Positie
        await asyncio.sleep(1)

# Send periodic the doorposition to Domoticz
async def UpdatePosition(client, Topic):
    while True:
        await asyncio.sleep(300)
        msg = mqtt.CreateDomoticzValue(1956, ScaleOpening(Garagedeur.Positie))
        client.publish(Topic, msg)


async def OmDraaien(logger):
    while True:
        while Garagedeur.Richting == 'stil':
            await asyncio.sleep(0.5)
        if (Garagedeur.Richting == 'omhoog' and Garagedeur.RemoteDrukKnop == 'Dicht') or (Garagedeur.Richting == 'omlaag' and Garagedeur.RemoteDrukKnop == 'Open'):
            # only wait when the first puls is given
            while Garagedeur.StartMotor:
                #wait for first startpuls to finish then 2 and 3
                await asyncio.sleep(2)
            Garagedeur.StartMotor = True
            await asyncio.sleep(4)
            Garagedeur.StartMotor = True
            logger.info('LOCAL4:DeurCommando Omgedraaid')
        await asyncio.sleep(0.1)


