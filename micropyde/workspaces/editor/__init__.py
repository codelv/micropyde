#------------------------------------------------------------------------------
# Copyright (c) 2013, Nucleic Development Team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
#------------------------------------------------------------------------------
from __future__ import print_function

import pickle

from atom.api import Unicode

from enaml.widgets.api import Container, DockArea
from enaml.workbench.ui.api import Workspace

import enaml
with enaml.imports():
    from .manifest import EditorManifest, create_new_area


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
        self.load_area()
        manifest = EditorManifest()
        self._manifest_id = manifest.id
        self.workbench.register(manifest)
        self.load_plugins()

    def load_plugins(self):
        """ Load any editor plugins from the micropyde.plugins package """
        plugins = []
        with enaml.imports():
            #: TODO autodiscover these
            from micropyde.plugins.pozetron.manifest import Manifest
            plugins.append(Manifest)

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
        area = self.content.find('editor')
        with open('state.db', 'wb') as f:
            f.write(pickle.dumps(area))

    def load_area(self):
        """ Load the dock area into the workspace content.

        """
        area = None
        try:
            with open('state.db', 'rb') as f:
                area = pickle.loads(f.read())
        except Exception as e:
            print(e)
        if area is None:
            area = create_new_area()
        area.set_parent(self.content)
        area.workbench = self.workbench
