"""
Copyright (c) 2017, Jairus Martin.

Distributed under the terms of the GPL v3 License.

The full license is in the file COPYING.txt, distributed with this software.

Created on Dec 5, 2017

@author
"""
from setuptools import setup, find_packages

setup(
  name='micropyde',
  author="CodeLV",
  author_email="frmdstryr@gmail.com",
  license='GPL',
  url='https://github.com/codelv/micropyde/',
  description="An IDE for micropython",
  long_description=open("README.md").read(),
  packages=find_packages(),
  include_package_data=True,
  version='1.0',
  install_requires=[
      'PyQt5', 'enaml', 'enamlx', 'QScintilla', 'twisted', 'autobahn',
      'qt5reactor', 'qtconsole', 'jsonpickle', 'pozetron-cli', 'jedi',
      'pyserial', 'pyflakes', 'esptool',
  ],
)
