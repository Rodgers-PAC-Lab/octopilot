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


## LOADING PARAMETERS FOR THE PI 
params = load_params.load_params_file(verbose=False)
pins = load_params.load_pins(verbose=False)


## Handle daemons
# Kill any pre-existing pigpiod and jackd
daemons.kill_pigpiod(verbose=True)
daemons.kill_jackd(verbose=True)

# Start pigpiod and jackd
daemons.start_pigpiod(verbose=True)
jackd_proc = daemons.start_jackd(verbose=True)


## Start the main loop
hc = hardware.HardwareController(pins=pins, params=params)
hc.main_loop()



## Terminate daemons
# TODO: move this to HardwareController? Should it be in charge of its own
# daemons?

# A good test is to comment out the rest of this script, which is essentially
# what happens if the script fails
# It should still be able to run next time
# Or try killing pigpiod or jackd outside of this process

# Terminate pigpiod
daemons.kill_pigpiod(verbose=True)

# Terminate jackd
jackd_proc.terminate()

# Pull out stdout and stderr
stdout, stderr = jackd_proc.communicate()

if jackd_proc.returncode == 0:
    print('jackd successfully killed')
else:
    print('could not kill jackd; dump follows:')
    print(f'returncode: {jackd_proc.returncode}')
    print(f'stdout: {stdout}')
    print(f'stderr: {stderr}')
    