"""
Copyright (c) 2017, Jairus Martin.

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

@author: jrm
"""
import faulthandler
from micropyde.app import main

if __name__ == '__main__':
    faulthandler.enable()
    main()
