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
import textwrap
from glob import glob

from atom.api import (
    Tuple, Unicode, Int, Instance, List, Bool, Enum, Dict,
    ContainerList, ForwardSubclass, observe
)

from micropyde.core import Plugin, Model
from enaml.layout.api import InsertTab, RemoveItem
from enaml.application import timed_call

from . import inspection
from .views.themes import THEMES

from twisted.protocols.basic import LineReceiver
from twisted.internet.defer import inlineCallbacks, Deferred


def EditorItem(*args, **kwargs):
    with enaml.imports():
        from micropyde.plugins.editor.views.dock import DockEditorItem
    return DockEditorItem(*args, **kwargs)


def get_settings_page():
    with enaml.imports():
        from micropyde.plugins.editor.views.settings import (
            EditorSettingsPage)

    return EditorSettingsPage


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
        from micropyde.workbench import MicropydeWorkbench
        workbench = MicropydeWorkbench.instance()
        plugin = workbench.get_plugin('micropyde.editor')
        self.suggestions = plugin.autocomplete(self.source, self.cursor)


class EditorPlugin(Plugin):
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

    #: Editor settings
    theme = Enum('friendly', *THEMES.keys())
    zoom = Int(0)  #: Relative to default

    #: TODO: Detect from upy_path
    upy_board = Enum('esp8266', 'pyb', 'stm32', 'teensy', 'unix',
                     'windows', 'cc3200', 'zephyr', 'pic16bit',
                     'minimal')
    upy_path = Unicode(os.path.abspath('../micropython/micropython/'))
    upy_lib_path = Unicode(os.path.abspath('../micropython/micropython-lib/'))
    project_path = Unicode(os.path.abspath('.'))
    sys_path = List().tag(persist=False)

    #: Settings pages
    settings_title = Unicode("Editor")
    settings_pages = Dict().tag(persist=False)
    settings_page = ForwardSubclass(get_settings_page).tag(persist=False)
    settings_items = List().tag(persist=False)

    #: Dock area layout
    _area_saves_pending = Int().tag(persist=False)

    # -------------------------------------------------------------------------
    # Plugin API
    # -------------------------------------------------------------------------
    def _default_settings_pages(self):
        """ Available settings pages """
        return {EditorPlugin: self.settings_page}

    def _default_settings_items(self):
        return [self]

    # -------------------------------------------------------------------------
    # Device API
    # -------------------------------------------------------------------------
    # def open_port(self, protocol):
    #     try:
    #         if self.com_mode == 'serial':
    #             self.com_port = SerialPort(protocol, self.port, reactor,
    #                                    baudrate=self.com_baud)
    #         else:
    #             self.com_ws =
    #         return True
    #     except Exception as e:
    #         print(e)
    #         return False
    #
    # def close_port(self):
    #     if self.com_port:
    #         self.com_port.connectionLost(connectionDone)
    #         self.com_port = None
    #
    # def write_message(self, message):
    #     """ Send a message to the device """

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
    def _default_sys_path(self):
        """ Determine the micropython SDK sys path"""
        results = [self.project_path, self.upy_lib_path, self.upy_path]

        #: Add from module ports
        paths = glob('{}/ports/{}/modules/*.py'.format(self.upy_path,
                                                          self.upy_board),
                     recursive=True)
        print(paths)
        results += [os.path.dirname(s) for s in paths]

        #: Add modules from libs
        paths = glob('{}/**/setup.py'.format(self.upy_lib_path),
                     recursive=True)
        results += [os.path.dirname(s) for s in paths]
        return list(set(results))

    @observe('upy_path', 'upy_lib_path', 'project_path', 'upy_board')
    def _refresh_sys_path(self, change):
        if change['type'] == 'update':
            self.sys_path = self._default_sys_path()

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
            script = jedi.Script(source, line+1, column,
                                 sys_path=self.sys_path)

            #: Get suggestions
            results = []
            for c in script.completions():
                results.append(c.name)

                #: Try to get a signature if the docstring matches
                #: something Scintilla will use (ex "func(..." or "Class(...")
                #: Scintilla ignores docstrings without a comma in the args
                if c.type in ['function', 'class', 'instance']:
                    docstring = c.docstring()

                    #: Remove self arg
                    docstring = docstring.replace("(self,", "(")

                    if docstring.startswith("{}(".format(c.name)):
                        results.append(docstring)
                        continue

            return results
        except Exception:
            #: Autocompletion may fail for random reasons so catch all errors
            #: as we don't want the editor to exit because of this
            return []




