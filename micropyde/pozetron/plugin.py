"""
Copyright (c) 2017, Jairus Martin.

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

@author: jrm
"""
import os
import json
from atom.api import Unicode, Dict
from enaml.workbench.api import Plugin
from twisted.internet import utils
from twisted.internet.defer import inlineCallbacks


class PozetronPlugin(Plugin):

    device_id = Unicode()

    #: All provisioned devices
    devices = Dict()

    def _default_devices(self):
        """ Load devices from state 
         
        """
        try:
            with open('~/.pozetron/devices.json') as f:
                return json.loads(f)
        except Exception as e:
            print("Failed to load devices: {}".format(e))
            return {}

    def _observe_devices(self, change):
        """ Save devices to state 
         
        """
        if change['type'] == 'update':
            try:
                devices = json.dumps(self.devices, indent=4)
                with open('~/.pozetron/devices.json', 'w') as f:
                    f.write(devices)
            except Exception as e:
                print("Failed to save devices: {}".format(e))

    def start(self):
        pass

    @inlineCallbacks
    def provision_device(self):
        args = "device provision -k {}"
        output = yield utils.getProcessOutput('poze.py',
                                              args.format('NONE').split())
        key = None
        for line in output.split("\n"):
            if "we suggest" in line:
                key = line.split(":")[-1].strip()
                break
        output = yield utils.getProcessOutput('poze.py',
                                              args.format(key).split())
        lines = output.split("\n")
        device = {
            'key': key,
            'address': lines[0],
            'id': lines[1]
        }

        #: Save it
        devices = self.devices
        devices[str(len(devices))] = device
        self.devices = devices

    def tag_module(self):
        tag = "main:v1"
        mod_id = "some-hash"
        cmd = "poze.py tag add {} {}".format(mod_id, tag)

    def deploy_module(self):
        cmd = "poze.py script deploy -s hello:v1 -d tutorial"

    def upload_module(self):
        mod = "main"
        cmd = "poze.py script upload -f {}.py -m {}".format(mod)

    @inlineCallbacks
    def download_firmware(self, device):
        """ Download and flash the pozetron firmware 
        
        """
        cmd = "poze.py"
        args = "device firmware esp8266 -d {}".format(device['address'])
        output = yield utils.getProcessOutput(cmd, args.split())

    def device_reboot(self, device):
        cmd = "poze.py device reboot -d {}".format(device)

    def register(self, key, secret):
        """ Create the Pozetron ID file
        
        """
        path = os.path.expanduser('~/.pozetron/id_pozetron')

        config_dir = os.path.dirname(path)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)

        with open(path, 'w') as f:
            f.write('{} {}\n'.format(key, secret))


