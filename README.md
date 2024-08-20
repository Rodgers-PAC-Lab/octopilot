# Introduction
This software controls the sound-seeking behavior used in the Rodgers PAC Lab. The user runs a GUI on the desktop computer to start the task and monitor progress. Each behavior box has four raspberry pis. The GUI connects to these pis over a wireless network. Generally, the GUI specifies the overall task parameters and logs the experimental results, while the individual pis control the task hardware.

These are the main scripts that run the task
* gui.py - Runs the GUI on the desktop computer
* pi.py - Runs the task on each individual pi
* gui/configs - Configuration files specifying the parameters of each box
* pi/configs/pis - Configuration files for each pi
* pi/configs/tasks - Configuration files for each task
* pi/pokes, pi/sound - TODO Sukrith what are these files? - These were old toy example scripts that I left in the wrong directory. I shifted them to the old directory and made a separate branch that will have them in case we need them
* pi/*.py - Old pi.py copy that I used for doc before making this branch. The one outside the directory in main is more recent. Merged some of the changes I made while docing in main 
* old/ - TODO remove this (Done)
* logs/ - Experimental logs TODO move these out of the repository
* pi2/ - chris' version of scripts to run on pi, work in progress

# Installation
TODO add more detail here

## Requirements for Pi and GUI
conda install pyqt pyzmq pyqtgraph pyqt-toast-notification numpy pandas

## Requirements for Pi Only
PiGPIO: pip install pigpio\

Jack Installation: https://jackclient-python.readthedocs.io/en/0.5.4/installation.html#requirements

