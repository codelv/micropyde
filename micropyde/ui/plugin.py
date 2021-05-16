"""
Copyright (c) 2017, Jairus Martin.

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

Created on Dec 12, 2017

@author: jrm
"""
import enaml
from atom.api import Atom, List, Str, Instance, Dict
from micropyde.core.api import Plugin, DockItem, log
from enaml.layout.api import AreaLayout, DockBarLayout, HSplitLayout, TabLayout
from . import extensions


class MicropydePlugin(Plugin):
    #: Project site
    wiki_page = Str("https;//www.codelv.com/projects/micropyde")

    #: Dock items to add
    dock_items = List(DockItem)
    dock_layout = Instance(AreaLayout)

    #: Settings pages to add
    settings_pages = List(extensions.SettingsPage)

    #: Current settings page
    settings_page = Instance(extensions.SettingsPage)

    #: Internal settings models
    settings_typemap = Dict()
    settings_model = Instance(Atom)

    def start(self):
        """ Load all the plugins micropyde is dependent on """
        w = self.workbench
        super(MicropydePlugin, self).start()
        self._refresh_dock_items()
        self._refresh_settings_pages()

    def start_default_workspace(self):
        ui = self.workbench.get_plugin('enaml.workbench.ui')
        ui.select_workspace('micropyde.workspace')

    def _bind_observers(self):
        """ Setup the observers for the plugin.
        """
        super(MicropydePlugin, self)._bind_observers()
        workbench = self.workbench
        point = workbench.get_extension_point(extensions.DOCK_ITEM_POINT)
        point.observe('extensions', self._refresh_dock_items)

        point = workbench.get_extension_point(extensions.SETTINGS_PAGE_POINT)
        point.observe('extensions', self._refresh_settings_pages)

    def _unbind_observers(self):
        """ Remove the observers for the plugin.
        """
        super(MicropydePlugin, self)._unbind_observers()
        workbench = self.workbench
        point = workbench.get_extension_point(extensions.DOCK_ITEM_POINT)
        point.unobserve('extensions', self._refresh_dock_items)

        point = workbench.get_extension_point(extensions.SETTINGS_PAGE_POINT)
        point.unobserve('extensions', self._refresh_settings_pages)

    # -------------------------------------------------------------------------
    # Dock API
    # -------------------------------------------------------------------------
    def create_new_area(self):
        """ Create the dock area
        """
        with enaml.imports():
            from .dock import DockView
        area = DockView(
            workbench=self.workbench,
            plugin=self
        )
        return area

    def get_dock_area(self):
        """ Get the dock area

        Returns
        -------
            area: DockArea
        """
        ui = self.workbench.get_plugin('enaml.workbench.ui')
        if not ui.workspace or not ui.workspace.content:
            ui.select_workspace('micropyde.workspace')
        return ui.workspace.content.find('dock_area')

    def _refresh_dock_items(self, change=None):
        """ Reload all DockItems registered by any Plugins

        Any plugin can add to this list by providing a DockItem
        extension in their PluginManifest.

        """
        workbench = self.workbench
        point = workbench.get_extension_point(extensions.DOCK_ITEM_POINT)

        #: Layout spec
        layout = {
            'main': [],
            'left': [],
            'right': [],
            'bottom': [],
            'top': []
        }

        dock_items = []
        for extension in sorted(point.extensions, key=lambda ext: ext.rank):
            for declaration in extension.get_children(extensions.DockItem):
                #: Create the item
                DockItem = declaration.factory()
                item = DockItem(
                    plugin=workbench.get_plugin(declaration.plugin_id),
                )

                #: Add to our layout
                layout[declaration.layout].append(item.name)

                #: Save it
                dock_items.append(item)

        #: Update items
        log.debug("Updating dock items: {}".format(dock_items))
        self.dock_items = dock_items
        self._refresh_layout(layout)

    def _refresh_layout(self, layout):
        """ Create the layout for all the plugins


        """
        if not self.dock_items:
            return AreaLayout()
        items = layout.pop('main')
        if not items:
            raise EnvironmentError("At least one main layout item must be "
                                   "defined!")
        main = (HSplitLayout(TabLayout(*items[1:]), items[0])
                if len(items) > 1 else items[0])

        dockbars = [DockBarLayout(*items, position=side)
                    for side, items in layout.items() if items]

        #: Update layout
        self.dock_layout = AreaLayout(
            main,
            dock_bars=dockbars
        )

    # -------------------------------------------------------------------------
    # Settings API
    # -------------------------------------------------------------------------
    def _default_settings_page(self):
        return self.settings_pages[0]

    def _observe_settings_page(self, change):
        log.debug("Settings page: {}".format(change))

    def _refresh_settings_pages(self, change=None):
        """ Reload all SettingsPages registered by any Plugins

        Any plugin can add to this list by providing a SettingsPage
        extension in their PluginManifest.

        """
        workbench = self.workbench
        point = workbench.get_extension_point(extensions.SETTINGS_PAGE_POINT)

        settings_pages = []
        typemap = {}
        for extension in sorted(point.extensions, key=lambda ext: ext.rank):
            for d in extension.get_children(extensions.SettingsPage):
                #: Save it
                settings_pages.append(d)

                #: Update the type map
                plugin = self.workbench.get_plugin(d.plugin_id)
                t = type(getattr(plugin, d.model) if d.model else plugin)
                typemap[t] = d.factory()

        #: Update items
        log.debug("Updating settings pages: {}".format(settings_pages))

        self.settings_typemap = typemap
        self.settings_pages = settings_pages
