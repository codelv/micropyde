"""
Copyright (c) 2017, Jairus Martin.

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

@author: jrm
"""
import os
import enaml
import socket
import hashlib
import textwrap
from base64 import b64decode
from atom.api import Dict, Int, Instance, Str, List, observe
from autobahn.twisted.websocket import (
    WebSocketClientFactory, WebSocketClientProtocol
)
from twisted.internet import reactor
from twisted.internet.defer import Deferred, DeferredList, inlineCallbacks
from twisted.internet.serialport import SerialPort
from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import Protocol
from twisted.internet.endpoints import TCP4ClientEndpoint, connectProtocol
from serial.tools.list_ports import comports
from enaml.application import deferred_call, timed_call
from micropyde.core.api import Plugin, Model
from micropyde.core.utils import async_sleep, log


class Connection(Model):
    """ The abstract connection protocol

    """

    #: The connection name
    name = Str()

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
    port = Str('/dev/ttyUSB0').tag(config=True)
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
                log.debug("{} connected!".format(self.port))
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
            log.debug("{} disconnected!".format(self.port))
            s.loseConnection()
            self.serial_port = None


class WebsocketConnection(Connection):

    #: ws address
    #: TODO: Config this
    addresses = List().tag(config=True)
    address = Str('192.168.41.144').tag(config=True)

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
            log.info("Testing connection to: {}:{}".format(self.address,
                                                        self.port))
            s = socket.create_connection((self.address, self.port), 0.2)
            s.close()
            log.info("ws REPL available!")
            return True
        except Exception as e:
            log.info("ws REPL unavailable: {}".format(e))
            return False

    def scan_subnet(self):
        """ Scan to find any ws clients on the port"""
        subnet = self.address.split('.')[0:3]
        addrs = []

        def on_connect(p, addr):
            log.debug("scan | {}:{} is up!".format(addr,
                                                   self.port))
            addrs.append(addr)
            p.transport.loseConnection()

        #: Scan for everything in the subnet
        #: timeout after 1 second
        ds = []
        for i in range(256):
            addr = ".".join(subnet+[str(i)])
            point = TCP4ClientEndpoint(reactor, addr, self.port)
            d = connectProtocol(point, Protocol())
            d.addCallback(lambda p, addr=addr: on_connect(p, addr))
            d.addErrback(lambda e, addr=addr: log.debug(
                "scan | {} is down".format(addr)))
            reactor.callLater(1, d.cancel)
            ds.append(d)

        #: When they all finish update the addresses property
        done = DeferredList(ds)
        done.addCallback(lambda r: setattr(self, 'addresses', addrs))

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
                self.delegate.transport = self.transport
                d.callback(self)
                log.debug("ws://{}:{} connected!".format(this.address,
                                                 this.port))
                self.delegate.connectionMade()

            def onMessage(self, payload, isBinary):
                self.delegate.dataReceived(payload)

            def onClose(self, wasClean, code, reason):
                log.debug("ws://{}:{} disconnected: "
                          "clean={} code={} reason={}!".format(
                    this.address, this.port, wasClean, code, reason))
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
    timeout = 100

    def __init__(self, plugin):
        self.plugin = plugin
        self.connect_event = Deferred()
        self.logged_in = Deferred()
        self.request = None

    def ready(self):
        return self.connect_event

    def connectionMade(self):
        self.lines = []
        #: If websocket we have to wait for the password first
        self.connect_event.callback(True)

    @inlineCallbacks
    def login(self):
        """ Wait a little for a password prompt

        """
        #: Wait for it to connect
        yield self.ready()

        #: Then wait for the password prompt
        yield async_sleep(300)
        log.debug(self._buffer)
        if 'Password:' in self._buffer.decode():
            #: Hack
            yield self.plugin.show_password_prompt()

    def lineReceived(self, line):
        log.debug(line)
        self.lines.append(line.decode())
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
    indexing_status = Str()

    #: Files on device
    files = Dict().tag(config=True)
    scanning_progress = Int()
    scanning_status = Str()

    upload_progress = Int()
    upload_status = Str()

    #: Passwords
    passwords = Dict().tag(config=True)

    # -------------------------------------------------------------------------
    # Board API
    # -------------------------------------------------------------------------
    @inlineCallbacks
    def download_file(self, event):
        """ Download a file from tne board

        """
        path = event.parameters['path']
        editor = self.workbench.get_plugin("micropyde.editor")

        log.info("Download file from device '%s'..." % path)

        # Connect
        board = self.board
        board.disconnect()
        device = QueryProtocol(self)
        yield board.connect(device)
        yield device.login()
        log.info("Downloading...")
        result = yield device.query(b'\n\x05' + textwrap.dedent("""
            def __downloader__():
                import sys
                from ubinascii import b2a_base64
                f = open('{path}', 'rb')
                while True:
                    d = f.read(256)
                    if not d:
                        break
                    sys.stdout.write(b2a_base64(d))
                f.close()
            __downloader__()""".format(
                path=path
        )).encode() + b'\x04', timeout=1000)

        log.info(result)
        source = []
        start, end = 0, -1
        for i, line in enumerate(result):
            if "__downloader__" in line:
                start = i+1
            elif line.startswith(">>>"):
                end = i
        source = result[start:end]

        if not source:
            log.warning("Failed to download file: '%s'" % result)
            return
        download_path = os.path.join(editor.project_path, path)
        with open(download_path, 'wb') as f:
            for chunk in source:
                log.info(chunk)
                data = b64decode(chunk)
                f.write(data)

        core = self.workbench.get_plugin('enaml.workbench.core')
        core.invoke_command("micropyde.editor.open_file",
                            parameters={'path': download_path})

    @inlineCallbacks
    def upload_file(self, event):
        editor = self.workbench.get_plugin("micropyde.editor")
        path = editor.active_document.name
        with open(path, 'rb') as f:
            source = f.read()
        log.info("Uploading {} to board...".format(path))

        board = self.board
        board.disconnect()
        device = QueryProtocol(self)
        yield board.connect(device)
        yield device.login()

        hash = hashlib.sha256()
        hash.update(source)
        expected_hash = hash.hexdigest()
        log.info("Expected Hash: {}".format(expected_hash))

        #: TODO: Apparently this is to big to send over the websocket...
        board.write(b'\n\x05'+textwrap.dedent("""
            def __uploader__():
                import sys
                import uhashlib
                import ubinascii
                filename = '{file}'
                print("Uploading %s..." % filename)
                f = open(filename,'wb')
                try:
                    i = {len}
                    n = 0
                    chunk = 64
                    while n < i:
                        chunk = min(i-n, chunk)
                        n += f.write(sys.stdin.read(chunk))
                        print('Uploaded: %i of %i'%(n,i))
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
                        if not data:
                            break
                        hash.update(data)
                    upload_hash = ubinascii.hexlify(hash.digest())
                    expected_hash = b'{expected_hash}'
                    print("Expected hash: {{}}".format(
                        expected_hash
                    ))
                    print("Actual hash:   {{}}".format(
                        upload_hash
                    ))
                    if upload_hash == expected_hash:
                        print("Upload success!")
                    else:
                        print("Upload failed (hash mismatch)!")
                except Exception as e:
                    print(e)
                finally:
                    f.close()
            __uploader__()""".format(
            file=os.path.split(path)[-1],
            expected_hash=expected_hash,
            len=len(source) #: Test...
        )).encode()+b'\n\x04')

        #: Have to write to the port slowly... not sure why?
        i = len(source)
        n = 0
        chunk = 64
        #: Sleep
        yield async_sleep(1000)

        self.upload_progress = 0
        while True:
            wrote = min(i-n, chunk)
            data = source[n:n+wrote]
            if not data:
                break
            board.write(data)
            n += wrote

            if i:
                self.upload_progress = min(100, max(0, int(100*n/i)))

            #: Sleep
            yield async_sleep(100)
            if device.lines:
                self.upload_status = device.lines[-1]

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
        log.info("build index")
        excluded = ['http_server', 'http_server_ssl']
        board = self.board

        #: Reconnect with a different protocol
        board.disconnect()
        device = QueryProtocol(self)
        yield board.connect(device)
        self.indexing_progress = 0
        self.indexing_status = "Connecting...."
        yield device.login()

        #: Now query
        result = yield device.query(b"\r\nhelp('modules')")
        log.info(result)
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
    #             log.info("Failed to save module index: {}".format(e))

    # -------------------------------------------------------------------------
    # File Browser API
    # -------------------------------------------------------------------------
    @inlineCallbacks
    def scan_files(self, event):
        excluded = ['http_server',
                    'http_server_ssl']

        board = self.board
        board.disconnect()
        device = QueryProtocol(self)
        yield board.connect(device)
        self.scanning_progress = 0
        self.scanning_status = "Connecting...."
        yield device.login()

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
        """).encode()+b'\n\x04', raw=True, timeout=200)
        log.debug("Scan complete!")
        contents = {}
        for line in result:
            try:
                contents = eval(line)
                log.debug("Loaded!")
                break
            except Exception as e:
                log.debug(e)
        #: TODO: Walk...
        if not contents:
            return
        self.files = contents

    def save_password(self, pwd):
        """ Save the password for the current connection """
        self.passwords[self.board.connection.name] = pwd
        self.save()

    def show_password_prompt(self):
        """ Probably shouldn't go here but whatever """
        d = Deferred()
        ui = self.workbench.get_plugin('micropyde.ui')
        with enaml.imports():
            from .dialogs import PasswordDialog

        board = self.board

        #: Check for a saved password
        pwd = self.passwords.get(board.connection.name)

        if pwd:
            txt = pwd+"\r\n"
            self.board.write(txt.encode())
            d.callback(txt)
        else:
            PasswordDialog(ui.get_dock_area(),
                           plugin=self,
                           callback=d.callback).exec_()
        return d
