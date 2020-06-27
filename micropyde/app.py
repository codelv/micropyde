"""
Copyright (c) 2017, Jairus Martin.

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

Created on Jan 1, 2018

@author: jrm
"""
import enaml
from micropyde.core.workbench import MicropydeWorkbench


def main():
    workbench = MicropydeWorkbench()

    with enaml.imports():
        from micropyde.core.manifest import CoreManifest
        from micropyde.ui.manifest import UIManifest
        from micropyde.console.manifest import ConsoleManifest
        from micropyde.editor.manifest import EditorManifest
        from micropyde.board.manifest import BoardManifest
        from micropyde.esp.manifest import EspManifest
        from micropyde.ocd.manifest import OpenChipDebuggerManifest

    workbench.register(CoreManifest())
    workbench.register(UIManifest())
    workbench.register(ConsoleManifest())
    workbench.register(EditorManifest())
    workbench.register(BoardManifest())
    workbench.register(EspManifest())
    workbench.register(OpenChipDebuggerManifest())
    workbench.run()
