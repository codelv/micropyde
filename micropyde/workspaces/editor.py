#------------------------------------------------------------------------------
# Copyright (c) 2013, Nucleic Development Team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
#------------------------------------------------------------------------------
from __future__ import print_function

import jsonpickle as pickle

from atom.api import Unicode

from enaml.widgets.api import Container
from enaml.workbench.ui.api import Workspace

import enaml
with enaml.imports():
    from micropyde.plugins.editor.manifest import (
        EditorManifest, create_new_area
    )


class EditorWorkspace(Workspace):
    """ A custom Workspace class for the crash course example.

    """
    #: Storage for the plugin manifest's id.
    _manifest_id = Unicode()

    def start(self):
        """ Start the workspace instance.

        This method will create the container content and register the
        provided plugin with the workbench.

        """
        self.content = Container(padding=0)
        manifest = EditorManifest()
        self._manifest_id = manifest.id
        self.workbench.register(manifest)
        self.workbench.get_plugin('micropyde.editor')
        self.load_area()
        self.load_plugins()

    def load_plugins(self):
        """ Load any editor plugins from the micropyde.plugins package """
        plugins = []
        with enaml.imports():
            #: TODO autodiscover these
            from micropyde.plugins.board.manifest import BoardManifest
            from micropyde.plugins.esp.manifest import EspManifest
            from micropyde.plugins.pozetron.manifest import PozetronManifest
            plugins.append(BoardManifest)
            plugins.append(EspManifest)
            plugins.append(PozetronManifest)

        for Manifest in plugins:
            self.workbench.register(Manifest())

    def stop(self):
        """ Stop the workspace instance.

        This method will unregister the workspace's plugin that was
        registered on start.

        """
        self.save_area()
        self.workbench.unregister(self._manifest_id)

    def save_area(self):
        """ Save the dock area for the workspace.

        """
        print("Saving dock area")
        area = self.content.find('dock_area')
        try:
            with open('editor.area.db', 'w') as f:
                f.write(pickle.dumps(area))
        except Exception as e:
            print("Error saving dock area: {}".format(e))
            return e

    def load_area(self):
        """ Load the dock area into the workspace content.

        """
        area = None
        try:
            #with open('editor.area.db', 'r') as f:
            #    area = pickle.loads(f.read())
            pass #: TODO:
        except Exception as e:
            print(e)
        if area is None:
            print("Creating new area")
            area = create_new_area()
        else:
            print("Loading existing doc area")
        area.set_parent(self.content)
        area.workbench = self.workbench
        area.plugin = self.workbench.get_plugin('micropyde.editor')
