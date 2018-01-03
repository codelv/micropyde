"""
Copyright (c) 2017, Jairus Martin.

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

Created on Jul 12, 2015

@author: jrm
"""
import enamlx
enamlx.install()

import enaml
from atom.api import Unicode
from enaml.qt import QtWidgets
from enaml.workbench.ui.api import UIWorkbench


class MicropydeWorkbench(UIWorkbench):
    #: Singleton instance
    _instance = None

    #: For error messages
    app_name = Unicode('Micropython IDE')

    @classmethod
    def instance(cls):
        return cls._instance

    @property
    def application(self):
        ui = self.get_plugin('enaml.workbench.ui')
        return ui._application

    @property
    def window(self):
        """ Return the main UI window or a dialog if it wasn't made yet 
        (during loading) 
        
        """
        try:
            ui = self.get_plugin('enaml.workbench.ui')
            return ui.window.proxy.widget
        except:
            return QtGui.QDialog()

    # -------------------------------------------------------------------------
    # Message API
    # -------------------------------------------------------------------------
    def message_critical(self, title, message, *args, **kwargs):
        """ Shortcut to display a critical popup dialog.
        
        """
        return QtWidgets.QMessageBox.critical(self.window, "{0} - {1}".format(
            self.app_name, title), message, *args, **kwargs)

    def message_warning(self, title, message, *args, **kwargs):
        """ Shortcut to display a warning popup dialog.
        
        """
        return QtWidgets.QMessageBox.warning(self.window, "{0} - {1}".format(
            self.app_name, title), message, *args, **kwargs)

    def message_information(self, title, message, *args, **kwargs):
        """ Shortcut to display an info popup dialog.
        
        """
        return QtWidgets.QMessageBox.information(self.window, "{0} - {1}".format(
            self.app_name, title), message, *args, **kwargs)

    def message_about(self, title, message, *args, **kwargs):
        """ Shortcut to display an about popup dialog.
        
        """
        return QtWidgets.QMessageBox.about(self.window, "{0} - {1}".format(
            self.app_name, title), message, *args, **kwargs)

    def message_question(self, title, message, *args, **kwargs):
        """ Shortcut to display a question popup dialog.
        
        """
        return QtWidgets.QMessageBox.question(self.window, "{0} - {1}".format(
            self.app_name, title), message, *args, **kwargs)

    # -------------------------------------------------------------------------
    # Workbench API
    # -------------------------------------------------------------------------
    def run(self):
        """ Run the UI workbench application.
    
        This method will load the core and ui plugins and start the
        main application event loop. This is a blocking call which
        will return when the application event loop exits.
    
        """
        MicropydeWorkbench._instance = self

        with enaml.imports():
            from enaml.workbench.core.core_manifest import CoreManifest
            from enaml.workbench.ui.ui_manifest import UIManifest

        self.register(CoreManifest())
        self.register(UIManifest())

        #: Init the ui
        ui = self.get_plugin('enaml.workbench.ui')
        ui.show_window()

        #: Start the core plugin
        plugin = self.get_plugin('micropyde.core')
        ui.start_application()
        #self.unregister('enaml.workbench.ui')
