## Main script that runs on each Pi to run behavior

import zmq
import pigpio
import numpy as np
import os
import jack
import time
import threading
import random
import json
import socket as sc
import itertools
import queue
import multiprocessing as mp
import pandas as pd
import scipy.signal

from . import daemons
from . import load_params
from . import hardware


## Set up daemons
daemons.kill_old_daemons(sleep_time=0.1)
daemons.start_pigpiod(sleep_time=0.1)
daemons.start_jackd(sleep_time=0.1)


## LOADING PARAMETERS FOR THE PI 
params = load_params.load_params_file(verbose=True)
pins = load_params.load_pins(verbose=True)


## Start
hc = hardware.HardwareController(pins=pins, params=params)
hc.mainloop()