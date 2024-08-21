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


## Set up daemons
daemons.kill_old_daemons()
daemons.start_pigpiod()
daemons.start_jackd()


## LOADING PARAMETERS FOR THE PI 
params = load_params.load_params_file()
pins = load_params.load_pins()


## Start
hc = hardware.HardwareController(params, pins)
hc.mainloop()