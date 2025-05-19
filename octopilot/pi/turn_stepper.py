# First run this:
#   source ~/.venv/py3/bin/activate
#
# Then run this script in ipython

import pigpio
import time
import datetime
import jack
import numpy as np
import os
import itertools
import importlib
from . import hardware

## Killing previous pigpiod and jackd background processes
os.system('sudo killall pigpiod')
os.system('sudo killall jackd')

# Wait long enough to make sure they are killed
time.sleep(1)



import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(26, GPIO.OUT)



## Starting pigpiod and jackd background processes
# Start pigpiod
# -t 0 : use PWM clock (otherwise messes with audio)
# -l : disable remote socket interface (not sure why)
# -x : mask the GPIO which can be updated (not sure why; taken from autopilot)
# Runs in background by default (no need for &)
os.system('sudo pigpiod -t 0 -l -x 1111110000111111111111110000')
time.sleep(1)


## Keep track of pigpio.pi
pi = pigpio.pi()


## Run
while True:
    pig.write(26, 1)
    time.sleep(.01)
    pig.write(26, 0)
    time.sleep(.01)

