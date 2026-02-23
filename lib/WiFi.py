import uasyncio as asyncio
import network
from time import sleep
from CONFIG import NetWorkConfig

class Network():
    wlan = network.WLAN()
    FirstRun = False

#coroutine: Connect to WiFi
async def Connect_Wifi():
    while True:
        while Network.wlan.isconnected() and Network.FirstRun:
            await asyncio.sleep(5)
        if Network.FirstRun:
            print("Reconnecting...")
        status = await initialize_wifi(NetWorkConfig.wifi_ssid, NetWorkConfig.wifi_password)
        if not status:
            print('Error connecting to the network... Retry in 10 seconds.')
            await asyncio.sleep(10)
        else:
            await asyncio.sleep(1)
        Network.FirstRun = status


async def initialize_wifi(ssid, password):
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
        print('IP address:', network_info[0])
        await asyncio.sleep(1)
        return True