#------------------------------------------------------------------------------
# Copyright (c) 2017 Jairus Martin
#
# Distributed under the terms of the GPL v3 License.
#
# The full license is in the file LICENSE, distributed with this software.
#------------------------------------------------------------------------------
import os
import sys
from enaml.image import Image
from enaml.icon import Icon, IconImage


def icon_path(name):
    path = os.path.dirname(__file__)
    return os.path.join(path, 'res', 'icons', '%s.png' % name)


def load_image(name):
    with open(icon_path(name), 'rb') as f:
        data = f.read()
    return Image(data=data)


def load_icon(name):
    img = load_image(name)
    icg = IconImage(image=img)
    return Icon(images=[icg])


def menu_icon(name):
    """ Icons don't look good on Linux/osx menu's """
    if sys.platform == 'win32':
        return load_icon(name)
    return None
