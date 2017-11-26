from enaml.workbench.api import Plugin


class PozetronPlugin(Plugin):

    def start(self):
        self.init_logging()
        self.workbench.application.deferred_call(self.start_default_workspace)


    def start_default_workspace(self):
        ui = self.workbench.get_plugin('enaml.workbench.ui')
        ui.select_workspace('micropyde.editor')

    def init_logging(self):
        from twisted.python import log
        log.startLogging(sys.stdout)


