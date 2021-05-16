"""
Copyright (c) 2017, Jairus Martin.

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

@author: jrm
"""
import os
import jedi
import enaml
from glob import glob

from atom.api import (
    Tuple, Str, Int, Instance, List, Bool, Enum, Dict,
    ContainerList, observe
)

from micropyde.core.api import Plugin, Model, log
from enaml.layout.api import InsertItem, InsertTab, RemoveItem
from enaml.application import timed_call

from . import inspection
from enaml.scintilla.themes import THEMES
from enaml.scintilla.mono_font import MONO_FONT

def editor_item_factory():
    with enaml.imports():
        from .editor import EditorDockItem
    return EditorDockItem


def create_editor_item(*args, **kwargs):
    EditorDockItem = editor_item_factory()
    return EditorDockItem(*args, **kwargs)


class Document(Model):
    #: Name of the current document
    name = Str().tag(config=True)

    #: Source code
    source = Str()
    cursor = Tuple(default=(0, 0))

    #: Any unsaved changes
    unsaved = Bool(True).tag(config=True)

    #: Any linting errors
    errors = List()

    #: Any autocomplete suggestions
    suggestions = List()

    #: Checker instance
    checker = Instance(inspection.Checker)

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
        from micropyde.core.workbench import MicropydeWorkbench
        workbench = MicropydeWorkbench.instance()
        plugin = workbench.get_plugin('micropyde.editor')
        self.suggestions = plugin.autocomplete(self.source, self.cursor)


class EditorPlugin(Plugin):
    #: Module index
    modules = Dict().tag(config=True)
    indexing_progress = Int()
    indexing_status = Str()

    #: Files on device
    files = Dict()
    scanning_progress = Int()
    scanning_status = Str()

    #: Opened files
    documents = ContainerList(Document).tag(config=True)
    active_document = Instance(Document).tag(config=True)
    last_path = Str(os.path.expanduser('~/')).tag(config=True)

    #: Editor settings
    font_size = Int(12).tag(config=True)  #: Default is 12 pt
    font_family = Str(MONO_FONT.split()[-1]).tag(config=True)
    theme = Enum('friendly', *THEMES.keys()).tag(config=True)
    zoom = Int(0).tag(config=True)  #: Relative to default

    #: TODO: Detect from upy_path
    upy_board = Enum('esp8266', 'pyb', 'stm32', 'teensy', 'unix',
                     'windows', 'cc3200', 'zephyr', 'pic16bit',
                     'minimal').tag(config=True)
    upy_path = Str(os.path.abspath(
        '../micropython/micropython/')).tag(config=True)
    upy_lib_path = Str(os.path.abspath(
        '../micropython/micropython-lib/')).tag(config=True)
    project_path = Str(os.path.abspath('./project/')).tag(config=True)
    sys_path = List()

    #: Dock area layout
    _area_saves_pending = Int()

    def start(self):
        """ Make sure the documents all open on startup """
        super(EditorPlugin, self).start()
        self.workbench.application.deferred_call(
            self._update_area_layout, {'type': 'load'})

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
        elif change['type'] == 'load':
            removed = {item.doc for item in self.get_editor_items()}
            added = set(self.documents)

        #: Update operations to apply
        ops = []
        removed_targets = set()

        #: Remove any old items
        for doc in removed:
            for item in self.get_editor_items():
                if item.doc == doc:
                    removed_targets.add(item.name)
                    ops.append(RemoveItem(item=item.name))

        # Remove ops
        if ops:
            log.debug(ops)
            area.update_layout(ops)

        # Add each one at a time
        targets = set([item.name for item in area.dock_items()
                   if (item.name.startswith("editor-item") and
                   item.name not in removed_targets)])

        log.info(
            "Editor added=%s removed=%s targets=%s",
            added, removed, targets)


        # Sort documents so active is last so it's on top when we restore
        # from a previous state
        for doc in sorted(added, key=lambda d: int(d == self.active_document)):
            item = create_editor_item(area, plugin=self, doc=doc)
            if targets:
                op = InsertTab(item=item.name, target=list(targets)[-1])
                try:
                    area.update_layout(op)
                except Exception as e:
                    # If it fails to add as a tab just insert it
                    log.exception(e)
                    op = InsertItem(item=item.name)
                    area.update_layout(op)
            else:
                op = InsertItem(item=item.name)
                area.update_layout(op)
            targets.add(item.name)

        # Now save it
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
        ui = self.workbench.get_plugin('micropyde.ui')
        return ui.get_dock_area()

    def get_editor_items(self):
        dock = self.get_dock_area()
        EditorDockItem = editor_item_factory()
        for item in dock.dock_items():
            if isinstance(item, EditorDockItem):
                yield item

    def get_editor(self):
        """ Get the editor item for the currently active document

        """
        item = 'editor-item-{}'.format(self.active_document.name)
        dock_item = self.get_dock_area().find(item)
        if not dock_item:
            return None
        return dock_item.children[0].editor

    def get_terminal(self):
        return self.get_dock_area().find('monitor-item')

    # -------------------------------------------------------------------------
    # Document API
    # -------------------------------------------------------------------------
    def _default_documents(self):
        return [Document()]

    def _default_active_document(self):
        if not self.documents:
            self.documents = self._default_documents()
        return self.documents[0]

    def new_file(self, event):
        """ Create a new file with the given path

        """
        path = event.parameters.get('path')
        if not path:
            return
        doc = Document(name=os.path.join(self.project_path, path))
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
        file_dir = os.path.dirname(doc.name)
        if not os.path.exists(file_dir):
            os.makedirs(file_dir)
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
