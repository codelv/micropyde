"""
Copyright (c) 2020, Jairus Martin.

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

@author: jrm
"""
import os
import sys
import pyocd

from atom.api import (
    Atom, List, Instance, ForwardInstance, Unicode, Bool, Int, Value
)
from micropyde.core.api import Plugin, log
from twisted.internet import utils

from twisted.internet.protocol import ProcessProtocol


class GDBServerProtocol(Atom, ProcessProtocol):
    plugin = ForwardInstance(lambda: OpenChipDebuggerPlugin)
    stream = Value()
    running = Bool(True)

    def terminate(self):
        self.transport.signalProcess('KILL')

    def connectionMade(self):
        super().connectionMade()
        self.write("Started")
        self.running = True

    def outReceived(self, data):
        self.write(data.decode())

    def errReceived(self, data):
        self.write(data.decode())

    def write(self, data):
        if self.stream:
            self.stream.append(data)

    def processExited(self, reason):
        self.write("Exited: %s" % reason)
        self.running = False


class Probe(Atom):
    index = Int()
    name = Unicode()
    uuid = Unicode()


class OpenChipDebuggerPlugin(Plugin):
    #: GDB server handle
    gdb_server = Instance(GDBServerProtocol)

    available_probes = List(Probe)

    def build_cmd(self, *args):
        return [sys.executable, '-m', 'pyocd'] + list(args)

    def erase_flash(self, protocol):
        #: TODO: Get port from event
        cmd = self.build_cmd('--port', self.port, 'erase')
        return self.run_command(protocol, *cmd)

    def update_firmware(self, protocol):
        cmd = self.build_cmd(
            '--port', self.port,
            '--baud', str(self.flash_baud),
            '--chip', self.flash_chip,
            'write_flash',
            '--flash_size', self.flash_size,
            '--flash_freq', self.flash_freq,
            '--flash_mode', self.flash_mode
        )
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
        cmd = self.build_cmd('--port', self.port, 'flash_id')
        self.run_command(protocol, *cmd)

    def get_chip_info(self, protocol):
        cmd = self.build_cmd('--port', self.port, 'chip_id')
        self.run_command(protocol, *cmd)

    def list_probes(self):
        cmd = self.build_cmd('list', '-p')
        utils.getProcessValue(cmd)

        def process_response(val):
            lines = val.split("\n")
            results = []
            if len(lines) >= 2:
                for line in lines:
                    index, name, uuid = line.strip().split()
                    results.append(Probe(index=index, namme=name, uuid=uuid))
            self.available_probes = results

        utils.addCallback(process_response)

    def start_server(self, stream=None):
        log.info("Starting GDB server...")
        self.stop_server()
        protocol = GDBServerProtocol(plugin=self, stream=stream)
        cmd = self.build_cmd('gdbserver',
                             '--persist')
        self.gdb_server = protocol
        self.run_command(protocol, *cmd)

    def stop_server(self):
        protocol = self.gdb_server
        if not protocol:
            return

        if protocol.running:
            log.info("Stopping GDB server...")
            protocol.terminate()
        self.gdb_server = None

