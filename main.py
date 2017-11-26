#------------------------------------------------------------------------------
# Copyright (c) 2017 Jairus Martin
#
# Distributed under the terms of the GPL v3 License.
#
# The full license is in the file LICENSE, distributed with this software.
#------------------------------------------------------------------------------

import enamlx
enamlx.install()
import enaml
import pickle
import faulthandler
from atom.api import Dict
from enaml.workbench.ui.api import UIWorkbench


class MicropydeWorkbench(UIWorkbench):
        #: Application config
        config = Dict()

        @property
        def application(self):
            ui = self.get_plugin('enaml.workbench.ui')
            return ui._application

        def load_config(self):
            """ Load any initial config from the previous session """
            try:
                with open('config.db') as f:
                    self.config = pickle.loads(f.read())
            except Exception as e:
                print(e)
                self.config = {}

        def save_config(self):
            """ Save any config so future sessions can use it """
            try:
                config = pickle.dumps(self.config)
                with open('config.db', 'wb') as f:
                    f.write(config)
            except Exception as e:
                print(e)

        def load_plugins(self):
            """ Load any plugins from the micropyde.plugins package """
            plugins = []
            with enaml.imports():
                #: TODO autodiscover these
                from micropyde.plugins.pozetron.manifest import Manifest
                plugins.append(Manifest)

            for Manifest in plugins:
                self.register(Manifest())

        def run(self):
            """ Run the UI workbench application.
        
            This method will load the core and ui plugins and start the
            main application event loop. This is a blocking call which
            will return when the application event loop exits.
        
            """
            with enaml.imports():
                from enaml.workbench.core.core_manifest import CoreManifest
                from enaml.workbench.ui.ui_manifest import UIManifest
                from micropyde.manifest import Manifest

            self.load_config()
            self.register(CoreManifest())
            self.register(UIManifest())
            self.register(Manifest())
            #: Init the ui
            ui = self.get_plugin('enaml.workbench.ui')
            ui.show_window()

            #: Install twisted support
            import qt5reactor
            qt5reactor.install()

            #: Start the core plugin
            micropyde = self.get_plugin('micropyde')

            #: Load other plugins
            self.load_plugins()

            ui.start_application()
            self.save_config()

            self.unregister('enaml.workbench.ui')


if __name__ == '__main__':
    faulthandler.enable()
    workbench = MicropydeWorkbench()
    workbench.run()
