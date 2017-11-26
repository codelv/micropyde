#------------------------------------------------------------------------------
# Copyright (c) 2017 Jairus Martin
#
# Distributed under the terms of the GPL v3 License.
#
# The full license is in the file LICENSE, distributed with this software.
#------------------------------------------------------------------------------
import re
import json
import hashlib
import esptool
import textwrap
from enaml.workbench.api import Plugin
from enaml.application import timed_call
from atom.api import Atom, Unicode, Int, Instance, List, Bool, Enum, Dict
from twisted.internet import reactor
from twisted.internet.protocol import connectionDone
from twisted.internet.serialport import SerialPort
from twisted.protocols.basic import LineReceiver
from twisted.internet.defer import inlineCallbacks, Deferred
from . import inspection
from .utils import async_sleep


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
            reactor.callLater(self.timeout, self.finish)

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


class Document(Atom):
    name = Unicode()
    source = Unicode()
    errors = List()
    autocompletions = List()
    checker = Instance(inspection.Checker)

    def _observe_source(self, change):
        if change['type'] == 'update':
            self._update_errors(change)
            self._update_autocompletions(change)

    def _update_errors(self, change):
        checker, reporter = inspection.run(self.source, self.name)
        warnings = reporter._stdout.getvalue().split("\n")
        errors = reporter._stderr.getvalue().split("\n")
        self.errors = warnings + errors
        self.checker = checker

    def _update_autocompletions(self, change):
        pass


class EditorPlugin(Plugin):
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

    #: Serial setup
    com_baud = Int(115200)
    com_port = Instance(SerialPort)

    #: Module index
    modules = Dict()
    indexing_progress = Int()
    indexing_status = Unicode()

    #: Opened files
    documents = List()
    active_document = Instance(Document)
    last_path = Unicode('~')

    #: Files on device
    files = Dict()
    scanning_progress = Int()
    scanning_status = Unicode()


    # -------------------------------------------------------------------------
    # Device API
    # -------------------------------------------------------------------------
    def open_port(self, protocol):
        try:
            self.com_port = SerialPort(protocol, self.port, reactor,
                                       baudrate=self.com_baud)
            return True
        except Exception as e:
            print(e)
            return False

    def close_port(self):
        if self.com_port:
            self.com_port.connectionLost(connectionDone)
            self.com_port = None

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

    @inlineCallbacks
    def upload_file(self, event):
        if not self.com_port:
            self.get_terminal().toggle_port()
        source = self.get_editor().get_text().encode()
        path = self.active_document.name
        self.com_port.write(b'\n\x05'+textwrap.dedent("""
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
            self.com_port.write(data)
            n += wrote

            #: Sleep
            yield async_sleep(100)

        hash = hashlib.sha256()
        hash.update(source)
        print("Expected Hash: {}".format(hash.hexdigest()))

    def run_script(self, event):
        #: Open the port and let it read
        if not self.com_port:
            terminal = self.get_terminal()
            terminal.toggle_port()

        editor = self.get_editor()
        text = editor.get_text()
        return self.com_port.write(b'\n\x05'+text.encode()+b'\x04')

    # -------------------------------------------------------------------------
    # Editor API
    # -------------------------------------------------------------------------
    def get_dock_area(self):
        ui = self.workbench.get_plugin('enaml.workbench.ui')
        return ui.workspace.content.find('editor')

    def get_editor(self):
        item = 'editor-item-{}'.format(self.active_document.name)
        return self.get_dock_area().find(item).children[0].editor

    def get_terminal(self):
        return self.get_dock_area().terminal

    def run_command(self, protocol,  *args, **kwargs):
        """ Run a command without blocking using twisted's spawnProcess 
        
        See https://twistedmatrix.com/documents/current/core/howto/process.html
        
        """
        print(" ".join(args))
        return reactor.spawnProcess(protocol, args[0], args, **kwargs)

    # -------------------------------------------------------------------------
    # Document API
    # -------------------------------------------------------------------------
    def _default_documents(self):
        return [
            Document(name="main.py"),
            Document(name="boot.py"),
        ]

    def _default_active_document(self):
        return self.documents[0]

    def open_file(self, event):
        doc = Document(name=event.parameters['path'])
        with open(event.parameters['path']) as f:
            doc.source = f.read()
        docs = self.documents[:]
        docs.append(doc)
        self.documents = docs
        self.active_document = doc
        editor = self.get_editor()
        editor.set_text(doc.source)

    # -------------------------------------------------------------------------
    # Modules API
    # -------------------------------------------------------------------------
    @inlineCallbacks
    def build_index(self, event):
        print("build index")
        excluded = ['http_server', 'http_server_ssl']

        self.close_port()
        device = QueryProtocol()
        if not self.open_port(device):
            return
        self.indexing_progress = 0
        self.indexing_status = "Connecting...."
        yield device.ready()

        result = yield device.query(b"\r\nhelp('modules')")
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

    def _default_modules(self):
        """ Try to load module index from the cache """
        try:
            with open('modules.json') as f:
                return json.load(f)
        except Exception as e:
            return {}

    def _observe_modules(self, change):
        """ Try to save module index to the cache """
        if change['type'] == 'update':
            try:
                index = json.dumps(self.modules, indent=2)
                with open('modules.json', 'w') as f:
                    f.write(index)
            except Exception as e:
                print("Failed to save module index: {}".format(e))

    # -------------------------------------------------------------------------
    # File Browser API
    # -------------------------------------------------------------------------
    @inlineCallbacks
    def scan_files(self, event):
        excluded = ['http_server',
                    'http_server_ssl']

        self.close_port()
        device = QueryProtocol()
        if not self.open_port(device):
            return
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

    # -------------------------------------------------------------------------
    # Code inspection API
    # -------------------------------------------------------------------------
    def autocomplete(self, text):
        """ Return a list of autocomplete suggestions for the given text.
        Results are based on the modules loaded.
        
        Parameters
        ----------
            text: str
                Source to autocomplete
        Return
        ------
            result: list
                List of autocompletion strings
        """
        suggestions = []
        try:
            lines = text.split("\n")
            line = lines[-1]
            print(line)
            if line.split()[0] in ["import", "from"]:
                suggestions = [m for m in self.modules]
            elif line.split(".")[0] in self.modules.keys():
                mod = line.split(".")[0]
                suggestions = ["{}.{}".format(mod, attr)
                               for attr in self.modules[mod]
                               if not attr.startswith("__")]
        except Exception as e:
            print("Error getting suggestions for '{}': {}".format(text, e))
        finally:
            print("Suggestions for '{}' are {}".format(text, suggestions))
            #self.active_document.autocompletions = suggestions
            return suggestions




