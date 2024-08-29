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
conda create --name paclab_sukrith
conda activate paclab_sukrith
conda install pyqt pyzmq pyqtgraph numpy pandas ipython
pip install pyqt-toast-notification

## Requirements for Pi Only
pip install pigpio

Jack Installation: https://jackclient-python.readthedocs.io/en/0.5.4/installation.html#requirements

## Documentation for config files (pi/configs/pis/BOXNAME.json)
Parameters for each pi in the behavior box
* identity: The name of the pi (set according to its hostname)
* gui_ip: The IP address of the computer that runs the GUI 
* poke_port: The network port dedicated to receiving information about pokes
* config_port: The network port used to send all the task parameters for any saved mouse
  nosepoke_type (L/R): This parameter is to specify the type of nosepoke sensor. 
  Nosepoke sensors are of two types OPB901L55 and OPB903L55 - 903 has an 
  inverted rising edge/falling edge which means that the functions being 
  called back to on the triggers need to be inverted.
* nosepoke_id (L/R): The number assigned to the left and right ports of each pi 

## Documentation for pins (pi/configs/pins.json)
* TODO