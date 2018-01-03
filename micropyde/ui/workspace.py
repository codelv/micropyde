"""
Copyright (c) 2017, Jairus Martin.

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

Created on Jan 1, 2018

@author: jrm
"""
from __future__ import print_function

import jsonpickle as pickle

from atom.api import Unicode

from enaml.widgets.api import Container
from enaml.workbench.ui.api import Workspace

import enaml
with enaml.imports():
    from .manifest import UIManifest


class MicropydeWorkspace(Workspace):
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
        manifest = UIManifest()
        self._manifest_id = manifest.id
        try:
            self.workbench.register(manifest)
        except ValueError:
            #: Already registered
            pass
        self.workbench.get_plugin('micropyde.ui')
        self.load_area()

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
        area = self.content.find('dock_area')
        try:
            with open('micropyde.workspace.db', 'w') as f:
                f.write(pickle.dumps(area))
        except Exception as e:
            print("Error saving dock area: {}".format(e))
            return e

    def load_area(self):
        """ Load the dock area into the workspace content.

        """
        area = None
        plugin = self.workbench.get_plugin("micropyde.ui")
        try:
            #with open('inkcut.workspace.db', 'r') as f:
            #    area = pickle.loads(f.read())
            pass  #: TODO:
        except Exception as e:
            print(e)
        if area is None:
            print("Creating new area")
            area = plugin.create_new_area()
        else:
            print("Loading existing doc area")
        area.set_parent(self.content)
