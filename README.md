# Micropyde

An IDE for micropython.

> Please note this is currently in alpha.

### Features

1. Editor using Scintilla with code hinting
2. "Serial Monitor" with com and websocket support
3. Flashing with esptool
4. Script run and upload (WIP)

##### Flashing

![Micropython IDE - Esptool flashing](https://user-images.githubusercontent.com/380158/34588508-5e571d04-f17b-11e7-99d2-db6db8244fbd.gif)

##### Code hinting and function tips

![Micropython IDE - Code hints and function tips](https://user-images.githubusercontent.com/380158/34588552-9cdef0e2-f17b-11e7-93b0-fbd0ba570d2e.gif)

##### Websocket support

![Miroypthon IDE - Websocket repl](https://user-images.githubusercontent.com/380158/34588596-db8b240a-f17b-11e7-9cfd-da0331dc865f.gif)


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

#: Build
pip install -e .

#: Run
micropyde


```



### License

Released under the GPL v3.

### Donate

If you would like to support the development of this project.
Please [donate](https://www.codelv.com/donate/) and let me know!
