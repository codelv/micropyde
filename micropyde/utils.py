#------------------------------------------------------------------------------
# Copyright (c) 2017 Jairus Martin
#
# Distributed under the terms of the GPL v3 License.
#
# The full license is in the file LICENSE, distributed with this software.
#------------------------------------------------------------------------------
import os
import sys
from atom.api import Atom
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


class Model(Atom):
    """ An atom object that can exclude members from it's state
    by tagging the member with .tag(persist=False)
    
    """

    def __getstate__(self):
        """ Exclude any members from the state that are
        tagged with `persist=False`. 
        
        """
        state = super(Model, self).__getstate__()
        for name, member in self.members().items():
            metadata = member.metadata
            if name in state and metadata and \
                    not metadata.get('persist', True):
                del state[name]
        return state

    def __setstate__(self, state):
        """  Set the state ignoring any fields that fail to set which
        may occur due to version changes.
        
        """
        for key, value in state.items():
            try:
                setattr(self, key, value)
            except Exception as e:
                #: Shorten any long values
                v = str(value)
                if len(v) > 100:
                    v[:100]+"..."

                print("Failed to restore state '{}.{} = {}'".format(
                    self, key, v
                ))
