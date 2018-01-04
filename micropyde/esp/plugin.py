"""
Copyright (c) 2017, Jairus Martin.

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

@author: jrm
"""
import os
import esptool

from atom.api import Unicode, Int, Bool, Enum
from micropyde.core.api import Plugin


class EspPlugin(Plugin):
    #: Flash setup
    port = Unicode('/dev/ttyUSB0')
    flash_chip = Enum('auto', 'esp8266', 'esp32')
    flash_baud = Int(460800) #, 230400, 921600, 1500000, 115200, 74880)
    flash_freq = Enum('keep', '40m', '26m', '20m', '80m')
    flash_mode = Enum('keep', 'qio', 'qout', 'dio', 'dout')
    flash_size = Enum('detect', '1MB', '2MB', '4MB', '8MB', '16M',
                      '256KB', '512KB', '2MB-c1', '4MB-c1')
    flash_address = Int()
    flash_spi_connection = Unicode()
    flash_compress = Bool()
    flash_verify = Bool()
    flash_filename = Unicode()

    last_path = Unicode(os.path.expanduser('~/'))

    def erase_flash(self, protocol):
        #: TODO: Get port from event
        cmd = ['python', esptool.__file__, '--port', self.port, 'erase_flash']
        return self.run_command(protocol, *cmd)

    def update_firmware(self, protocol):
        cmd = [
            'python', esptool.__file__,
            '--port', self.port,
            '--baud', str(self.flash_baud),
            '--chip', self.flash_chip,
            'write_flash',
            '--flash_size', self.flash_size,
            '--flash_freq', self.flash_freq,
            '--flash_mode', self.flash_mode
        ]
        if self.flash_verify:
            cmd.append('--verify')
        if self.flash_compress:
            cmd.append('--compress')
        if self.flash_spi_connection:
            cmd.append(self.flash_spi_connection)
        cmd.append(str(self.flash_address))
        cmd.append(self.flash_filename)
        return self.run_command(protocol, *cmd)

    def get_flash_info(self, protocol):
        cmd = ['python', esptool.__file__, '--port', self.port, 'flash_id']
        self.run_command(protocol, *cmd)

    def get_chip_info(self, protocol):
        cmd = ['python', esptool.__file__, '--port', self.port, 'chip_id']
        self.run_command(protocol, *cmd)


