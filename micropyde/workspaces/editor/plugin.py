#------------------------------------------------------------------------------
# Copyright (c) 2017 Jairus Martin
#
# Distributed under the terms of the GPL v3 License.
#
# The full license is in the file LICENSE, distributed with this software.
#------------------------------------------------------------------------------
import os
import jedi
import enaml
import jsonpickle as pickle
import hashlib
import esptool
import textwrap
import traceback

from atom.api import (Tuple, Unicode, Int, Instance, List, Bool, Enum, Dict,
                      ContainerList, observe)

from enaml.workbench.api import Plugin
from enaml.layout.api import (
    AreaLayout, TabLayout, DockBarLayout, InsertTab, InsertItem, RemoveItem
)
from enaml.application import timed_call, deferred_call

from micropyde.utils import Model
from micropyde.workspaces.editor import inspection
from micropyde.workspaces.editor.utils import async_sleep
from micropyde.workspaces.editor.views.themes import THEMES

from twisted.internet import reactor
from twisted.internet.protocol import connectionDone
from twisted.internet.serialport import SerialPort
from twisted.protocols.basic import LineReceiver
from twisted.internet.defer import inlineCallbacks, Deferred


def EditorItem(*args, **kwargs):
    with enaml.imports():
        from micropyde.workspaces.editor.views.dock import DockEditorItem
    return DockEditorItem(*args, **kwargs)


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


class Document(Model):
    #: Name of the current document
    name = Unicode()

    #: Source code
    source = Unicode().tag(persist=False)
    cursor = Tuple(default=(0, 0)).tag(persist=False)

    #: Any unsaved changes
    unsaved = Bool(True)

    #: Any linting errors
    errors = List()

    #: Any autocomplete suggestions
    suggestions = List()

    #: Checker instance
    checker = Instance(inspection.Checker).tag(persist=False)

    def _default_source(self):
        """ Load the document from the path given by `name`.
        If it fails to load, nothing will be returned and an error
        will be set.
        """
        try:
            print("Loading '{}' from disk.".format(self.name))
            with open(self.name) as f:
                return f.read()
        except Exception as e:
            self.errors = [str(e)]
        return ""

    def _observe_source(self, change):
        self._update_errors(change)
        self._update_suggestions(change)
        if change['type'] == 'update':
            try:
                with open(self.name) as f:
                    self.unsaved = f.read() != self.source
            except:
                pass

    def _update_errors(self, change):
        """ Parse the source and try to detect any errors
         
        """
        if self.errors and change['type'] == 'create':
            #: Don't squash load errors
            return
        checker, reporter = inspection.run(self.source, self.name)
        warnings = [l for l in reporter._stdout.getvalue().split("\n") if l]
        errors = [l for l in reporter._stderr.getvalue().split("\n") if l]
        self.errors = warnings + errors
        self.checker = checker

    def _update_suggestions(self, change):
        """ Determine code completion suggestions for the current cursor
        position in the document.
        """
        plugin = EditorPlugin.instance()
        self.suggestions = plugin.autocomplete(self.source, self.cursor)


class EditorPlugin(Plugin):
    #: Instance valid while plugin is active
    _instance = None

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
    com_port = Instance(SerialPort).tag(persist=False)

    #: Module index
    modules = Dict()
    indexing_progress = Int().tag(persist=False)
    indexing_status = Unicode().tag(persist=False)

    #: Opened files
    documents = ContainerList(Document)
    active_document = Instance(Document)
    last_path = Unicode(os.path.expanduser('~/'))

    #: Files on device
    files = Dict()
    scanning_progress = Int().tag(persist=False)
    scanning_status = Unicode().tag(persist=False)

    #: Theme
    theme = Enum('friendly', *THEMES.keys())

    #: Dock area layout
    _area_saves_pending = Int().tag(persist=False)

    # -------------------------------------------------------------------------
    # Plugin API
    # -------------------------------------------------------------------------
    @classmethod
    def instance(cls):
        return EditorPlugin._instance

    def start(self):
        """ Load the state when the plugin starts """
        self._bind_observers()
        EditorPlugin._instance = self

    def stop(self):
        """ Unload any state observers when the plugin stops"""
        self._unbind_observers()
        EditorPlugin._instance = None

    # -------------------------------------------------------------------------
    # State API
    # -------------------------------------------------------------------------
    def _bind_observers(self):
        """ Try to load the plugin state """
        #: Init state
        try:
            with open('editor.db', 'r') as f:
                state = pickle.loads(f.read())
            self.__setstate__(state)
        except Exception as e:
            print("Failed to load state: {}".format(e))

        #: Hook up observers
        for name, member in self.members().items():
            if not member.metadata or member.metadata.get('persist', True):
                self.observe(name, self._save_state)

    def _save_state(self, change):
        """ Try to save the plugin state """
        if change['type'] in ['update', 'container']:
            try:
                print("Saving state due to change: {}".format(change))

                #: Dump first so any failure to encode doesn't wipe out the
                #: previous state
                state = self.__getstate__()
                excluded = ['manifest', 'workbench'] + [
                    m.name for m in self.members().values()
                    if m.metadata and not m.metadata.get('persist', True)
                ]
                for k in excluded:
                    if k in state:
                        del state[k]
                state = pickle.dumps(state)

                with open('editor.db', 'w') as f:
                    f.write(state)
            except Exception as e:
                print("Failed to save state:")
                traceback.print_exc()

    def _unbind_observers(self):
        """ Setup state observers """
        for name, member in self.members().items():
            if not member.metadata or member.metadata.get('persist', True):
                self.unobserve(name, self._save_state)

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
    @observe('documents')
    def _update_area_layout(self, change):
        """ When a document is opened or closed, add or remove it
        from the currently active TabLayout.
        
        The layout update is deferred so it fires after the items are
        updated by the Looper.
        
        """
        if change['type'] == 'create':
            return

        #: Get the dock area
        area = self.get_dock_area()

        #: Refresh the dock items
        #area.looper.iterable = self.documents[:]

        #: Determine what change to apply
        removed = set()
        added = set()
        if change['type'] == 'container':
            op = change['operation']
            if op in ['append', 'insert']:
                added = set([change['item']])
            elif op == 'extend':
                added = set(change['items'])
            elif op in ['pop', 'remove']:
                removed = set([change['item']])
        elif change['type'] == 'update':
            old = set(change['oldvalue'])
            new = set(change['value'])

            #: Determine which changed
            removed = old.difference(new)
            added = new.difference(old)

        #: Update operations to apply
        ops = []

        #: Remove any old items
        for doc in removed:
            ops.append(RemoveItem(
                item='editor-item-{}'.format(doc.name)
            ))

        #: Add any new items
        for doc in added:
            targets = ['editor-item-{}'.format(d.name) for d in self.documents
                       if d.name != doc.name]
            item = EditorItem(area, plugin=self, doc=doc)
            ops.append(InsertTab(
                item=item.name,
                target=targets[0] if targets else ''
            ))

        #: Now apply all layout update operations
        print("Updating dock area: {}".format(ops))
        area.update_layout(ops)
        self.save_dock_area(change)

    def save_dock_area(self, change):
        """ Save the dock area """
        self._area_saves_pending += 1

        def do_save():
            self._area_saves_pending -= 1
            if self._area_saves_pending != 0:
                return
            #: Now save it
            ui = self.workbench.get_plugin('enaml.workbench.ui')
            ui.workspace.save_area()
        timed_call(350, do_save)

    def get_dock_area(self):
        ui = self.workbench.get_plugin('enaml.workbench.ui')
        return ui.workspace.content.find('dock_area')

    def get_editor(self):
        """ Get the editor item for the currently active document 
        
        """
        item = 'editor-item-{}'.format(self.active_document.name)
        dock_item = self.get_dock_area().find(item)
        if not dock_item:
            return None
        return dock_item.children[0].editor

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
        return [Document()]

    def _default_active_document(self):
        return self.documents[0]

    def new_file(self, event):
        """ Create a new file with the given path
        
        """
        path = event.parameters.get('path')
        if not path:
            return
        doc = Document(name=path)
        self.documents.append(doc)
        self.active_document = doc

    def close_file(self, event):
        """ Close the file with the given path and remove it from
        the document list. If multiple documents with the same file
        are open this only closes the first one it finds.
        
        """
        path = event.parameters.get('path', self.active_document.name)
        docs = self.documents
        opened = [d for d in docs if d.name == path]
        if not opened:
            return
        print("Closing '{}'".format(path))
        doc = opened[0]
        self.documents.remove(doc)

        #: If we closed the active document
        if self.active_document == doc:
            self.active_document = docs[0] if docs else Document()

    def open_file(self, event):
        """ Open a file from the local filesystem 
        
        """
        path = event.parameters['path']

        #: Check if the document is already open
        for doc in self.documents:
            if doc.name == path:
                self.active_document = doc
                return
        print("Opening '{}'".format(path))

        #: Otherwise open it
        doc = Document(name=path, unsaved=False)
        with open(path) as f:
            doc.source = f.read()
        self.documents.append(doc)
        self.active_document = doc
        editor = self.get_editor()
        if editor:
            editor.set_text(doc.source)

    def save_file(self, event):
        """ Save the currently active document to disk
        
        """
        doc = self.active_document
        assert doc.name, "Can't save a document without a name"
        with open(doc.name, 'w') as f:
            f.write(doc.source)
        doc.unsaved = False

    def save_file_as(self, event):
        """ Save the currently active document as the given name
        overwriting and creating the directory path if necessary.
        
        """
        doc = self.active_document
        path = event.parameters['path']

        if not doc.name:
            doc.name = path
            doc.unsaved = False

        doc_dir = os.path.dirname(path)
        if not os.path.exists(doc_dir):
            os.makedirs(doc_dir)

        with open(path, 'w') as f:
            f.write(doc.source)

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
    def autocomplete(self, source, cursor):
        """ Return a list of autocomplete suggestions for the given text.
        Results are based on the modules loaded.
        
        Parameters
        ----------
            source: str
                Source code to autocomplete
            cursor: (line, column)
                Position of the editor
        Return
        ------
            result: list
                List of autocompletion strings
        """
        try:
            #: Use jedi to get suggestions
            line, column = cursor
            script = jedi.Script(source, line+1, column)

            #: Get suggestions
            results = []
            for c in script.completions():
                results.append(c.name)

                #: Try to get a signature if the docstring matches
                #: something Scintilla will use (ex "func(..." or "Class(...")
                #: Scintilla ignores docstrings without a comma in the args
                if c.type in ['function', 'class', 'instance']:
                    docstring = c.docstring()
                    if docstring.startswith("{}(".format(c.name)):
                        results.append(docstring)
                        continue

            return results
        except Exception:
            #: Autocompletion may fail for random reasons so catch all errors
            #: as we don't want the editor to crash because of this
            return []




