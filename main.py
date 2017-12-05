#------------------------------------------------------------------------------
# Copyright (c) 2017 Jairus Martin
#
# Distributed under the terms of the GPL v3 License.
#
# The full license is in the file LICENSE, distributed with this software.
#------------------------------------------------------------------------------
import faulthandler
from micropyde.workbench import MicropydeWorkbench

if __name__ == '__main__':
    faulthandler.enable()
    workbench = MicropydeWorkbench()
    workbench.run()
