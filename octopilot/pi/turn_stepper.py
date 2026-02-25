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
#from . import hardware

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
pig = pigpio.pi()


## Run
# 200 steps/rev
# At 256x, this is 51200 steps/rev
# To do 1 rps, ISI is 1/51200 s, likely unachievable
# about 0.3 ms of overhead, so fastest is 3000 steps/s
# For some reason the overhead increases over time
pulse_time = 1e-8 # min
isi = 1/1000
corrected_isi = isi - 0.0004
if corrected_isi < 1e-8:
    corrected_isi = 1e-8
print(corrected_isi)
now = datetime.datetime.now()
n_steps = 0
while True:
    pig.write(26, 1)
    time.sleep(pulse_time)
    pig.write(26, 0)
    time.sleep(corrected_isi)
    n_steps += 1
    if np.mod(n_steps, 100) == 0:
        time_taken = (datetime.datetime.now() - now).total_seconds()
        print(f'{n_steps} in {time_taken} = {n_steps / time_taken}')

