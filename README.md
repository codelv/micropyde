# Micropyde

An IDE for micropython. 

Please note this is currently in alpha.

### Features

1. Editor using Scintilla
2. "Serial Monitor" with com and websocket support
3. Flashing with esptool
4. Script run and upload (WIP)

### Supports

As of now the esp8266 (should work with others, haven't tested)

### Installing

Build from source

```bash

#: Clone
git clone https://github.com/codelv/micropyde
cd micropyde

#: Make venv
virtualenv -p python3 venv
source venv/bin/activate

#: Install my enaml fork
pip install git+https://github.com/frmdstryr/enaml@latest

#: Build
pip install .

#: Run
python main.py


```



### License

Released under the GPL v3.

### Donate

If you would like to support the development of this project. 
Please [donate]() 
