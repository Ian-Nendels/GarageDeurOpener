import uasyncio as asyncio
import network
from time import sleep
from CONF import NetWorkConfig

class Network():
    wlan = network.WLAN()
    FirstRunDone = False
    Connected = False
    
#coroutine: Connect to WiFi
async def Connect_Wifi():
    while True:
        while Network.wlan.isconnected() and Network.Connected and Network.FirstRunDone:
            await asyncio.sleep(5)
        Network.Connected = False
        if Network.FirstRunDone:
            print("Reconnecting...")
        status = await initialize_wifi(NetWorkConfig.wifi_ssid, NetWorkConfig.wifi_password)
        if not status:
            print('Error connecting to the network... Retry in 10 seconds.')
            await asyncio.sleep(10)
        else:
            await asyncio.sleep(1)
        Network.FirstRunDone = status


async def initialize_wifi(ssid, password):
    Network.wlan.active(False)
    asyncio.sleep(1)
    Network.wlan = network.WLAN(network.STA_IF)
    Network.wlan.active(True)
    Network.wlan.config(pm = 0xa11140) # Disable power-save mode

    # Connect to the network
    Network.wlan.connect(ssid, password)

    # Wait for Wi-Fi connection
    connection_timeout = 10
    while connection_timeout > 0:
        if Network.wlan.status() < 0 or Network.wlan.status() >= 3:
            break
        connection_timeout -= 1
        print('Waiting for Wi-Fi connection...')
        await asyncio.sleep(1)

    # Check if connection is successful
    if not Network.wlan.isconnected():
        return False
    else:
        print('Connection successful!')
        network_info = Network.wlan.ifconfig()
        print('IP address :', network_info[0])
        print('NetMask    :', network_info[1])
        print('Gateway    :', network_info[2])
        print('DNS address:', network_info[3])
        Network.Connected = True
        await asyncio.sleep(1)
        return True