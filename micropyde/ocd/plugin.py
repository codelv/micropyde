"""
Copyright (c) 2020, Jairus Martin.

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

@author: jrm
"""
import os
import sys
import json

from atom.api import (
    Atom, List, Instance, ForwardInstance, Str, Bool, Int, Value, Enum
)
from micropyde.core.api import Plugin, log
from pyocd.tools.lists import ListGenerator
from twisted.internet import utils
from twisted.internet.protocol import ProcessProtocol

from enaml.qt.QtGui import QTextCursor


class StreamProtocol(Atom, ProcessProtocol):
    stream = Value()

    def write(self, data):
        stream = self.stream
        if stream:
            stream.moveCursor(QTextCursor.End)
            stream.insertPlainText(data)
            stream.moveCursor(QTextCursor.End)


class GDBServerProtocol(StreamProtocol):
    plugin = ForwardInstance(lambda: OpenChipDebuggerPlugin)
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

    def processEnded(self, reason):
        self.write("Exited: %s" % reason)
        self.running = False


class Base(Atom):
    """ Makes comparisons and hashing work properly """
    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.__getstate__())


class Probe(Base):
    unique_id = Str()
    info = Str()
    board_name = Str()
    target = Str()
    vendor_name = Str()
    product_name = Str()

    def __eq__(self, other):
        if not isinstance(other, Probe):
            return False
        return other.unique_id == self.unique_id


class Board(Base):
    id = Str()
    name = Str()
    target = Str()
    binary = Instance(str)
    is_target_builtin = Bool()
    is_target_supported = Bool()

    def __eq__(self, other):
        if not isinstance(other, Board):
            return False
        return other.id == self.id


class Target(Base):
    name = Str()
    source = Str()
    vendor = Str()
    part_families = List(str)
    part_number = Str()

    def __eq__(self, other):
        if not isinstance(other, Target):
            return False
        return other.name == self.name


class OpenChipDebuggerPlugin(Plugin):
    #: GDB server handle
    gdb_server = Instance(GDBServerProtocol)

    available_probes = List(Probe)
    available_targets = List(Target)
    available_boards = List(Board)

    target = Instance(Target).tag(config=True)
    probe = Instance(Probe).tag(config=True)
    board = Instance(Board).tag(config=True)

    # -------------------------------------------------------------------------
    # Erase params
    # -------------------------------------------------------------------------
    erase_mode = Enum('chip', 'mass', 'sector').tag(config=True)
    erase_sectors = Str().tag(config=True)

    # -------------------------------------------------------------------------
    # Flash params
    # -------------------------------------------------------------------------
    flash_connect_mode = Enum(
        '', 'halt', 'pre-reset', 'under-reset', 'attach').tag(config=True)
    flash_frequency = Str().tag(config=True)
    flash_address = Int().tag(config=True)
    flash_skip = Int().tag(config=True)
    flash_trust_crc = Bool().tag(config=True)
    flash_no_wait = Bool().tag(config=True)
    flash_filename = Str().tag(config=True)
    flash_erase_mode = Enum('', 'sector', 'auto', 'chip').tag(config=True)
    flash_format = Enum('auto', 'bin', 'hex', 'elf').tag(config=True)

    def _default_available_probes(self):
        return [Probe(**d) for d in ListGenerator.list_probes()['boards']]

    def _default_available_targets(self):
        targets = [Target(**d) for d in ListGenerator.list_targets()['targets']]
        targets.sort(key=lambda it: it.name)
        return targets

    def _default_available_boards(self):
        return [Board(**d) for d in ListGenerator.list_boards()['boards']]

    # -------------------------------------------------------------------------
    # Plugin API
    # -------------------------------------------------------------------------
    def start(self):
        super(OpenChipDebuggerPlugin, self).start()
        self.refresh()

    def refresh(self):
        """ Refresh pyocd targets, probes, and boards

        """
        self.available_targets = self._default_available_targets()
        self.available_probes = self._default_available_probes()
        self.available_boards = self._default_available_boards()

    def find_target(self, name):
        for t in self.targets:
            if t.name == name:
                return t

    def build_cmd(self, *args):
        return [sys.executable, '-m', 'pyocd'] + list(args)

    def erase_flash(self, protocol):
        if not self.probe:
            log.info("Please choose a debug probe")
            return
        if not self.target:
            log.info("Please choose a target")
            return
        probe = self.probe.unique_id
        target = self.target.name
        cmd = self.build_cmd('erase', '--uid', probe, '--target', target)

        if self.erase_mode == 'chip':
            cmd.append('--chip')
        elif self.erase_mode == 'mass':
            cmd.append('--mass')
        elif self.erase_sectors:
            cmd.extend(['--sector', self.erase_sectors])

        return self.run_command(protocol, *cmd)

    def update_firmware(self, protocol):
        if not self.probe:
            log.info("Please choose a debug probe")
            return
        if not self.target:
            log.info("Please choose a target")
            return
        if not self.flash_filename:
            log.info("Please choose a flash filename")
            return
        probe = self.probe.unique_id
        target = self.target.name
        cmd = self.build_cmd('flash', '--uid', probe, '--target', target)
        if self.flash_connect_mode:
            cmd.extend(['--connect', self.flash_connect_mode])
        if self.flash_frequency:
            cmd.extend(['--frequency', self.flash_frequency])
        if self.flash_erase_mode:
            cmd.extend(['-e', self.flash_erase_mode])
        if self.flash_address:
            cmd.extend('--base-address', str(self.flash_address))
        if self.flash_skip:
            cmd.extend(['--skip', str(self.flash_skip)])
        if self.flash_format != 'auto':
            cmd.extend(['--format', self.flash_format])
        if self.flash_trust_crc:
            cmd.append('--trust-crc')
        if self.flash_no_wait:
            cmd.append('--no-wait')
        cmd.append(self.flash_filename)
        return self.run_command(protocol, *cmd)

    def start_server(self, stream=None):
        if not self.probe:
            log.info("Please choose a debug probe")
            return
        if not self.target:
            log.info("Please choose a target")
            return
        probe = self.probe.unique_id
        target = self.target.name
        log.info("Starting GDB server for probe %s and target %s...",
                 probe, target)
        self.stop_server()
        protocol = GDBServerProtocol(plugin=self, stream=stream)
        cmd = self.build_cmd(
            'gdbserver',  '--uid', probe, '--target', target, '--persist')
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

