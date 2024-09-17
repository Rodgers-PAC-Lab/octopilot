# Introduction
`octopilot` controls the sound-seeking behavior used in the Rodgers PAC Lab. 

To use this software, `octopilot` must be running on a desktop PC and also on Rasperry Pis on the same wifi network. Each physical arena is controlled by four Raspberry Pis, and there can be multiple such arenas on the network. For each arena, the desktop PC instantiates an object called a `Dispatcher` which is controlled by either a GUI or a CLI. Each Pi instantiates an object called an `Agent` which is controlled by a CLI. The `Dispatcher` and `Agent` communicate over the wireless network to control the task for that arena. 

# Structure of the repository
These are the files within this repository.
* gui/ - Python scripts to run the `Dispatcher` on the desktop PC. TODO: Rename this dispatcher, or similar.
* pi/ - Python scripts to run the `Agent` on each Pi. TODO: rename this agent, or similar.
* shared/ - Python scripts that are used by both `Dispatcher` and `Agent`
* tests/ - Python scripts that test individual components
* configs/ - JSON configuration files
* logs/ - Log files for each session. TODO: move these out of the repository

For further documentation on the files within these directories, see the `__init__.py` within each directory.

For further documentation on the config files, see below.

# Installation
`octopilot` must be installed separately on the desktop and on each Pi.

## Requirements for GUI

    conda create --name octopilot
    conda activate octopilot
    conda install pyqt pyzmq pyqtgraph numpy pandas ipython
    pip install pyqt-toast-notification

## Requirements for Pi

Create a virtual environment called `octopilot`.

    mkdir ~/.venv
    virtualenv ~/.venv/octopilot

Activate that venv.

    source ~/.venv/octopilot/bin/activate 

Install dependencies

    sudo apt install jackd # say yes if it asks about real-time priority
    pip install pyzmq pigpio numpy pandas ipython scipy JACK-Client

Reboot after install jackd. For more info about installing jack: https://jackclient-python.readthedocs.io/en/0.5.4/installation.html#requirements

Install octopilot

    cd ~/dev/octopilot
    pip install -e .

# Running `octopilot`
On the desktop:

    conda activate octopilot
    python3 -m octopilot.gui.start_gui

The present version will automatically connect to each Pi and start `octopilot` on each Pi. Alternatively you can start it on the Pi like this:

    source ~/.venv/py3/bin/activate
    python3 -m octopilot.pi.start_cli

# Documentation for config files

To run an experiment, you must specify the box, mouse, and task. In addition, the box specifies the four individual Pis that are connected.

* The config file for the box named BOXNAME is located in `config/box/BOXNAME.json`. Example: the identity of the connected Pis and their orientation.
* The config file for the mouse named MOUSENAME is located in `config/mouse/MOUSENAME.json`. Example: reward duration. 
* The config file for the Pi named PINAME is located in `config/pi/PINAME.json`. Example: pin numbers and hardware parameters.
* The config file for the task named TASKNAME is located in `config/task/TASKNAME.json`. Example: the range of possible sounds.

The params in each of these files are documented in octopilot/shared/load_params.py
