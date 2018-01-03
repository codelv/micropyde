"""
Copyright (c) 2017, Jairus Martin.

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

@author: jrm
"""
import socket
import hashlib
import textwrap
from atom.api import Dict, Int, Instance, Unicode, List, observe
from autobahn.twisted.websocket import (
    WebSocketClientFactory, WebSocketClientProtocol
)
from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.serialport import SerialPort
from twisted.protocols.basic import LineReceiver
from serial.tools.list_ports import comports
from enaml.application import deferred_call, timed_call
from micropyde.core.api import Plugin, Model
from micropyde.core.utils import async_sleep
from future.builtins import str


class Connection(Model):
    """ The abstract connection protocol 
    
    """

    #: The connection name
    name = Unicode()

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
    port = Unicode('/dev/ttyUSB0').tag(config=True)
    ports = List()
    baudrate = Int(115200).tag(config=True)

    #: Actual connection
    serial_port = Instance(SerialPort)

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
    #: TODO: Config this
    address = Unicode('192.168.41.144').tag(config=True)

    #: Ws port
    port = Int(8266).tag(config=True)

    #:
    connection = Instance(WebSocketClientProtocol)

    #:
    connector = Instance(object)

    def _default_name(self):
        return "ws://{}:{}".format(self.address, self.port)

    @observe('address', 'port')
    def _refresh_name(self, change):
        self.name = self._default_name()

    def is_available(self):
        try:
            print("Testing connection to: {}:{}".format(self.address,
                                                        self.port))
            s = socket.create_connection((self.address, self.port), 0.2)
            s.close()
            print("ws REPL available!")
            return True
        except Exception as e:
            print("ws REPL unavailable: {}".format(e))
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
    """ Abstraction layer over a board that allows connections via
    websocket or serial using the same interface
    
    """

    #: List of connections configured
    configured_connections = List(Connection).tag(config=True)

    #: Connections that are currently available
    available_connections = List(Connection)

    #: Current connection for this board
    connection = Instance(Connection).tag(config=True)

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

    def _observe_connection(self, change):
        """ Whenever the connection changes, disconnect  """
        if change['type'] == 'update':
            oldvalue = change['oldvalue']
            if oldvalue:
                oldvalue.disconnect()

    def connect(self, protocol):
        """ Delegate to the current connection """
        return self.connection.connect(protocol)

    def write(self, message):
        return self.connection.write(message)

    def disconnect(self):
        return self.connection.disconnect()


class QueryProtocol(LineReceiver):
    """ Handles inspecting the modules on a micropython device
    using help(module) calls.
    
    """
    timeout = 0.1

    def __init__(self):
        self.connect_event = Deferred()
        self.request = None

    def ready(self):
        return self.connect_event

    def connectionMade(self):
        self.lines = []
        self.connect_event.callback(True)

    def lineReceived(self, line):
        self.lines.append(line.decode())
        print(line)
        if self.request:
            self.pending += 1
            timed_call(self.timeout, self.finish)

    def finish(self):
        self.pending -= 1
        if self.pending == 0:
            lines = self.lines[:]
            self.lines = []
            d = self.request
            self.request = None
            d.callback(lines)

    def query(self, msg, raw=False, timeout=None):
        """ Send a command and wait for it to reply
        :param msg: 
        :param timeout: 
        :return: 
        """
        if self.request is not None:
            #: Only allow one at a time
            raise RuntimeError("An request is pending!")
        if timeout:
            self.timeout = timeout
        self.pending = 0
        self.lines = []
        self.request = Deferred()
        #: Add a cancel timeout
        # def cancel():
        #     d = self.request
        #     if d:
        #         self.request = None
        #         d.errback(IOError("Timeout"))
        # reactor.callLater(10, cancel)

        if not raw and not msg.endswith(b'\r\n'):
            msg += b'\r\n'
        self.transport.write(msg)
        return self.request


class BoardPlugin(Plugin):

    #: Active board
    board = Instance(Board, ()).tag(config=True)

    #: Module index
    modules = Dict().tag(config=True)
    indexing_progress = Int()
    indexing_status = Unicode()

    #: Files on device
    files = Dict().tag(config=True)
    scanning_progress = Int()
    scanning_status = Unicode()

    # -------------------------------------------------------------------------
    # Board API
    # -------------------------------------------------------------------------
    @inlineCallbacks
    def upload_file(self, event):
        editor = self.workbench.get_plugin("micropyde.editor")
        terminal = editor.get_terminal()
        if not terminal.opened:
            terminal.toggle_port()
        source = editor.get_editor().get_text().encode()
        path = editor.active_document.name
        board = self.board
        board.write(b'\n\x05'+textwrap.dedent("""
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
            board.write(data)
            n += wrote

            #: Sleep
            yield async_sleep(100)

        hash = hashlib.sha256()
        hash.update(source)
        print("Expected Hash: {}".format(hash.hexdigest()))

    def run_script(self, event):
        #: Open the port and let it read
        editor = self.workbench.get_plugin("micropyde.editor")
        terminal = editor.get_terminal()
        if not terminal.opened:
            terminal.toggle_port()

        editor = editor.get_editor()
        text = editor.get_text()
        return self.board.write(b'\n\x05'+text.encode()+b'\x04')

    # -------------------------------------------------------------------------
    # Modules API
    # -------------------------------------------------------------------------
    @inlineCallbacks
    def build_index(self, event):
        print("build index")
        excluded = ['http_server', 'http_server_ssl']
        board = self.board

        board.disconnect()
        device = QueryProtocol()

        board.connect(device)

        self.indexing_progress = 0
        self.indexing_status = "Connecting...."
        yield device.ready()
        result = yield device.query(b"\r\nhelp('modules')")
        print(result)
        modules = []
        for line in result:
            if 'help(' not in line and 'on the filesystem' not in line:
                modules.extend([m.replace('/', '.') for m in line.split()])
        if not modules:
            return
        index = {}
        for i, module in enumerate(modules):
            self.indexing_progress = max(0,
                                         min(100, int(100*i/len(modules))), 0)
            if module.startswith("_") or module in excluded:  #: Auto starts!
                continue
            index[module] = {}
            self.indexing_status = "Inspecting {}".format(module)
            result = yield device.query(
                b'\r\n\x05'+'import {}\r\nhelp({})\r\n'.format(
                    module, module).encode()+b'\x04',
                raw=True)
            for line in result:
                if ' -- ' not in line: # Nothing fancy haha
                    continue
                key, val = [a.strip() for a in line.split(" -- ")]
                info = {'name': key}
                index[module][key] = info
                if "<" in val and ">" in val: #: TOOD: Use re
                    info['type'] = val
                else:
                    info['value'] = val

                if '<class' in val:
                    lines = yield device.query(
                        'help({}.{})'.format(module, key).encode())
                    attrs = {}
                    for line in lines:
                        if ' -- ' not in line:
                            continue
                        key, val = [a.strip() for a in line.split(" -- ")]
                        attrs[key] = val
                    info['attrs'] = attrs
        self.indexing_progress = 100
        self.indexing_status = "Done!"
        self.modules = index

    # def _default_modules(self):
    #     """ Try to load module index from the cache """
    #     try:
    #         with open('modules.json') as f:
    #             return json.load(f)
    #     except Exception as e:
    #         return {}
    #
    # def _observe_modules(self, change):
    #     """ Try to save module index to the cache """
    #     if change['type'] == 'update':
    #         try:
    #             index = json.dumps(self.modules, indent=2)
    #             with open('modules.json', 'w') as f:
    #                 f.write(index)
    #         except Exception as e:
    #             print("Failed to save module index: {}".format(e))

    # -------------------------------------------------------------------------
    # File Browser API
    # -------------------------------------------------------------------------
    @inlineCallbacks
    def scan_files(self, event):
        excluded = ['http_server',
                    'http_server_ssl']

        board = self.board
        board.disconnect()
        device = QueryProtocol()
        board.connect(device)
        self.scanning_progress = 0
        self.scanning_status = "Connecting...."
        yield device.ready()

        result = yield device.query(b'\n\x05'+textwrap.dedent("""
        def __scanfiles__(path):
            import os
            files = {}
            try:
                for f in os.listdir(path):
                    files[f] = {
                        'info':os.stat(f),
                        'files':__scanfiles__("{}/{}".format(path,f)),
                        'name':f
                    }
            except OSError:
                pass
            return files
        __scanfiles__('.')
        """).encode()+b'\n\x04', raw=True, timeout=1)

        contents = {}
        for line in result:
            try:
                contents = eval(line)
                break
            except:
                pass
        #: TODO: Walk...
        if not contents:
            return
        self.files = contents