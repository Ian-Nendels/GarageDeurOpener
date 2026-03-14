import urequests
import os
import json
import machine
from time import sleep
from lib import usyslog
from mqtt import config

class OTAUpdater:
    """ This class handles OTA updates. It checks for updates (using version number),
        then downloads and installs multiple filenames, separated by commas."""

    def __init__(self, repo_url, *filenames):
        
        # Initialise connection to syslog server
        logger = usyslog.UDPClient(ip=config.SYSLOG_SERVER_IP, facility=usyslog.F_LOCAL4)
        
        if "www.github.com" in repo_url :
            #print(f"Updating {repo_url} to raw.githubusercontent")
            self.repo_url = repo_url.replace("www.github","raw.githubusercontent")
        elif "github.com" in repo_url:
            #print(f"Updating {repo_url} to raw.githubusercontent'")
            self.repo_url = repo_url.replace("github","raw.githubusercontent")            
        self.version_url = self.repo_url + 'version.json'
        #print(f"version url is: {self.version_url}")
        self.filename_list = [filename for filename in filenames]

        # get the current version (stored in version.json)
        if 'version.json' in os.listdir():    
            with open('version.json') as f:
                self.current_version = int(json.load(f)['version'])
            #print(f"Current version is '{self.current_version}'")

        else:
            self.current_version = 0
            # save the current version
            with open('version.json', 'w') as f:
                json.dump({'version': self.current_version}, f)

    def fetch_new_code(self, filename):
        """ Fetch the code from the repo, returns False if not found."""
    
        # Fetch the latest code from the repo.
        self.firmware_url = self.repo_url + filename
        response = urequests.get(self.firmware_url, timeout = 1)
        if response.status_code == 200:
            print(f'Fetched file {filename}, status: {response.status_code}')
    
            # Save the fetched code to file (with prepended '_')
            new_code = response.text
            with open(f'_{filename}', 'w') as f:
                f.write(new_code)
            print(f'Saved as _{filename}')
            response.close()
            return True
        
        elif response.status_code == 404:
            print(f'Firmware not found - {self.firmware_url}.')
            response.close()
            return False

    def check_for_updates(self, logger):
        """ Check if updates are available. (Note: GitHub caches values for 5 min.)"""
        
        logmsg = f'Checking for latest version... on {self.version_url}'
        print(logmsg)
        logger.info('LOCAL4:' + logmsg)
 
        response = urequests.get(self.version_url, parse_headers=False)
        
        data = json.loads(response.text)
        
        response.close()
        
        #print(f"data is: {data}, url is: {self.version_url}")
        #print(f"data version is: {data['version']}")
        
        self.latest_version = int(data['version'])

        logmsg = f'latest version is: {self.latest_version}'
        print(logmsg)
        logger.info('LOCAL4:' + logmsg)
        
        # compare versions
        newer_version_available = True if self.current_version < self.latest_version else False
        
        logmsg = f'Newer version available: {newer_version_available}'    
        print(logmsg)
        logger.info('LOCAL4:' + logmsg)
        return newer_version_available
    
    def download_and_install_update_if_available(self, logger):
        """ Check for updates, download and install them."""
        if self.check_for_updates(logger):

            # Fetch new code
            for filename in self.filename_list:
                self.fetch_new_code(filename)

            # Overwrite current code with new
            for filename in self.filename_list:
                newfile = f"_{filename}"
                os.rename(newfile, filename)
                logmsg = f'Renamed _{filename} to {filename}, overwriting existing file'
                print(logmsg)
                logger.info('LOCAL4:' + logmsg)

            # save the current version
            with open('version.json', 'w') as f:
                json.dump({'version': self.latest_version}, f)
            logmsg = 'Update version from {self.current_version} to {self.latest_version}'
            print(logmsg)
            logger.info('LOCAL4:' + logmsg)

            # Restart the device to run the new code.
            logmsg = 'Restarting device...'
            print(logmsg)
            logger.info('LOCAL4:' + logmsg)
            sleep(0.3)
            machine.reset() 
        else:
            logmsg = 'No new updates available.'
            print(logmsg)
            logger.info('LOCAL4:' + logmsg)
