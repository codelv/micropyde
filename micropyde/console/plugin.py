# -*- coding: utf-8 -*-
"""
Copyright (c) 2017, Jairus Martin.

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

@author: jrm
"""
import logging
from micropyde.core.api import Plugin


class ConsolePlugin(Plugin):
    def start(self):
        """ Set the log level for IPython stuff to warn """
        for name in ['ipykernel.inprocess.ipkernel', 'traitlets']:
            log = logging.getLogger(name)
            log.setLevel(logging.WARNING)