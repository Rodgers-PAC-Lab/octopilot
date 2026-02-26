# Introduction
`octopilot` controls the sound-seeking behavior used in the Rodgers PAC Lab. 

To use this software, `octopilot` must be running on a desktop PC and also on Rasperry Pis on the same wifi network. Each physical arena is controlled by four Raspberry Pis, and there can be multiple such arenas on the network. For each arena, the desktop PC instantiates an object called a `Dispatcher` which is controlled by either a GUI or a CLI. Each Pi instantiates an object called an `Agent` which is controlled by a CLI. The `Dispatcher` and each of the `Agent`s communicate over the wireless network to control the task for that arena. 

`octopilot` is heavily inspired by the precursor `autopilot`: https://github.com/auto-pi-lot/autopilot and we are presently using some code from `autopilot`

# Organization of the repository
## Top-level files
These are the files at the top level of this repository:
* config/ - JSON configuration files for each box, mouse, pi, task, etc. These are described further below in the section "Config files". Eventually these may be moved out of the repository and moved into a local directory.
* doc/ - Documentation
* octopilot/ - The source files, described further below under "Source files".
* README.md - This file
* requirements.txt - Required dependencies. See "Installation" for more information.
* setup.py - The setup script. See "Installation".
* .gitignore - Filenames that git should ignore.

## Source files
These are the source files. These are located within the directory "octopilot/". The prefix "octopilot/" is omitted below.
* desktop/ - Code to run the `Dispatcher` on the desktop PC. TODO: rename to "dispatcher".
* pi/ - Code to run the `Agent` on each Pi. TODO: rename to "agent".
* shared/ - Code that is used by both `Dispatcher` and `Agent`
* tests/ - Code to test individual components

For further documentation on the files within these directories, see the `__init__.py` within each directory.

## Config files
To run an experiment, you must specify the box, mouse, and task. In addition, the box specifies the four individual Pis that are connected.

* The config file for the box named BOXNAME is located in `config/box/BOXNAME.json`. Briefly, this file specifies parameters of the computer running the `Dispatcher` and how to connect to the individual `Agents` running on each connected Pi.
* The config file for the mouse named MOUSENAME is located in `config/mouse/MOUSENAME.json`. Presently the only mouse-specific parameters is "reward_value", but eventually this should also include the task performed by each mouse.
* The config file for the Pi named PINAME is located in `config/pi/PINAME.json`. Briefly, this includes the box to which this Pi connects, and the pin numbers. Note that the box name in the pi config must be aligned with the pi name in the box config.
* The config file for the task named TASKNAME is located in `config/task/TASKNAME.json`. These specify the parameters of the task, such as what sounds are played and what ports are rewarded.

Detailed documentation for all parameters in each of these files may be found in octopilot/shared/load_params.py

# Installation
`octopilot` must be installed separately on the desktop and on each Pi.

## Requirements for GUI

    conda create --name octopilot
    conda activate octopilot
    conda install pyqt==5.15.10 pyzmq pyqtgraph==0.13.1 numpy pandas ipython urllib3 requests
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
    pip install RPi.GPIO # new

Reboot after install jackd. For more info about installing jack: https://jackclient-python.readthedocs.io/en/0.5.4/installation.html#requirements

## Installing octopilot

    cd ~/dev/octopilot
    pip install -e .

## Setting up log location before first use 

    mkdir ~/octopilot
    mdkir ~/octopilot/logs

# Running `octopilot`
On the desktop:

    conda activate octopilot
    python3 -m octopilot.desktop.start_launcher

The present version will automatically connect to each Pi and start `octopilot` on each Pi. Alternatively you can start it on the Pi like this:

    source ~/.venv/py3/bin/activate
    python3 -m octopilot.pi.start_cli

