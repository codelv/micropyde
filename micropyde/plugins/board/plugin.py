#------------------------------------------------------------------------------
# Copyright (c) 2017 Jairus Martin
#
# Distributed under the terms of the GPL v3 License.
#
# The full license is in the file LICENSE, distributed with this software.
#------------------------------------------------------------------------------
import socket
import hashlib
import textwrap
from atom.api import Enum, Int, Instance, Unicode, List, Bool, observe
from autobahn.twisted.websocket import (
    WebSocketClientFactory, WebSocketClientProtocol
)
from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.serialport import SerialPort
from serial.tools.list_ports import comports
from enaml.application import deferred_call
from micropyde.core import Plugin, Model, async_sleep
from future.builtins import str


class Connection(Model):
    """ The abstract connection protocol 
    
    """

    #: The connection name
    name = Unicode().tag(persist=False)

    def is_available(self):
        raise NotImplementedError

    def configure(self):
        """ Open the configuration dialog for this connection """
        raise NotImplementedError

    def connect(self, protocol):
        """ Must return a deferred that resolves when connected """
        raise NotImplementedError

    def write(self, message):
        raise NotImplementedError

    def disconnect(self):
        raise NotImplementedError


class SerialConnection(Connection):
    #: Connection settings
    port = Unicode('/dev/ttyUSB0')
    ports = List().tag(persit=False)
    baudrate = Int(115200)

    #: Actual connection
    serial_port = Instance(SerialPort).tag(persist=False)

    def is_available(self):
        self.ports = comports()
        self.name = self._default_name()
        return bool(self.ports)

    def _default_name(self):
        for port in self.ports:
            if port.device == self.port:
                return str(port)
        return self.port

    @observe('port')
    def _refresh_name(self, change):
        self.name = self._default_name()

    def connect(self, protocol):
        d = Deferred()

        def do_connect():
            try:
                self.serial_port = SerialPort(
                    protocol, self.port, reactor,
                    baudrate=self.baudrate)
                d.callback(True)
            except Exception as e:
                d.callback(e)
        deferred_call(do_connect)
        return d

    def write(self, message):
        if self.serial_port is None:
            return 0
        return self.serial_port.write(message)

    def disconnect(self):
        """ """
        s = self.serial_port
        if s:
            s.loseConnection()
            self.serial_port = None


class WebsocketConnection(Connection):

    #: ws address
    address = Unicode('192.168.41.147')

    #: Ws port
    port = Int(8266)

    #:
    connection = Instance(WebSocketClientProtocol)

    #:
    connector = Instance(object).tag(persist=False)

    def _default_name(self):
        return "ws://{}:{}".format(self.address, self.port)

    @observe('address', 'port')
    def _refresh_name(self, change):
        self.name = self._default_name()

    def is_available(self):
        try:
            s = socket.create_connection((self.address, self.port), 0.2)
            s.close()
            return True
        except:
            return False

    def connect(self, protocol):
        d = Deferred()

        factory = WebSocketClientFactory(
                    'ws://{}:{}'.format(self.address, self.port))

        this = self
        class DelegateProtocol(WebSocketClientProtocol):
            """ Delegates the calls to the given protcocol """
            delegate = protocol
            connector = self

            def onConnect(self, response):
                this.connection = self
                self.delegate.connectionMade()


            def onMessage(self, payload, isBinary):
                self.delegate.dataReceived(payload)


            def onClose(self, wasClean, code, reason):
                self.delegate.connectionLost(reason)

        factory.protocol = DelegateProtocol

        self.connector = reactor.connectTCP(self.address, self.port, factory)
        return d

    def write(self, message):
        if self.connection:
            self.connection.sendMessage(message)

    def disconnect(self):
        c = self.connector
        if c:
            c.disconnect()
            self.connector = None
            self.connection = None


class Board(Model):
    """ Abstraction layer over a device that allows connections via
    websocket or serial using the same interface
    
    """

    #: List of connections configured
    configured_connections = List(Connection)

    #: Connections that are currently available
    available_connections = List(Connection).tag(persist=False)

    #: Current connection for this device
    connection = Instance(Connection)

    def _default_connections(self):
        """ """
        return [SerialConnection(), WebsocketConnection()]

    def _default_available_connections(self):
        available = []
        if not self.configured_connections:
            self.configured_connections = self._default_connections()
        for connection in self.configured_connections:
            if connection.is_available():
                available.append(connection)
        return available

    def _default_connection(self):
        if not self.configured_connections:
            self.configured_connections = self._default_connections()
        return self.configured_connections[0]

    def configure(self):
        """ Open the configuration dialog for this connection """
        self.connection.configure()

    @observe('configured_connections')
    def refresh_connections(self, change=None):
        """ Refresh available connections """
        self.available_connections = self._default_available_connections()

    def connect(self, protocol):
        """ Delegate to the current connection """
        return self.connection.connect(protocol)

    def write(self, message):
        return self.connection.write(message)

    def disconnect(self):
        return self.connection.disconnect()


class BoardPlugin(Plugin):

    #: Active device
    board = Instance(Board, ())

    @inlineCallbacks
    def upload_file(self, event):
        if not self.device.connected:
            self.get_terminal().toggle_port()
        source = self.get_editor().get_text().encode()
        path = self.active_document.name
        device = self.device
        device.write(b'\n\x05'+textwrap.dedent("""
                def __uploader__():
                    import sys
                    import uhashlib
                    import ubinascii
                    print("Uploading file...")
                    f = open('{file}','wb')
                    try:
                        i = {len}
                        n = 0
                        chunk = 64
                        while n < i:
                            chunk = min(i-n, chunk)
                            #print("Reading %i..."%chunk)
                            n += f.write(sys.stdin.read(chunk))
                            print('Uploaded %i of %i'%(n,i))
                    except Exception as e:
                        print(e)
                    finally:
                        f.close()
                    #: Verify
                    try:
                        print("Verifying...")
                        f = open('{file}', 'rb')
                        hash = uhashlib.sha256()
                        while True:
                            data = f.read(64)
                            #print(data)
                            if not data:
                                break
                            hash.update(data)
                        print("Upload finished sha256={{}}.".format(
                            ubinascii.hexlify(hash.digest())
                        ))
                    except Exception as e:
                        print(e)
                    finally:
                        f.close()   
                    
                        
                __uploader__()""".format(
            file=path,
            len=len(source)  #: Test...
        )).encode()+b'\n\x04')

        #: Have to write to the port slowly... not sure why?
        i = len(source)
        n = 0
        chunk = 64
        #: Sleep
        yield async_sleep(100)

        while True:
            wrote = min(i-n, chunk)
            data = source[n:n+wrote]
            if not data:
                break
            device.write(data)
            n += wrote

            #: Sleep
            yield async_sleep(100)

        hash = hashlib.sha256()
        hash.update(source)
        print("Expected Hash: {}".format(hash.hexdigest()))

    def run_script(self, event):
        #: Open the port and let it read
        if not self.device.connected:
            terminal = self.get_terminal()
            terminal.toggle_port()

        editor = self.get_editor()
        text = editor.get_text()
        return self.device.write(b'\n\x05'+text.encode()+b'\x04')