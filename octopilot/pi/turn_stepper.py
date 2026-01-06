# First run this:
#   source ~/.venv/octopilot/bin/activate
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
# about 0.4 ms of overhead, so fastest is 3000 steps/s
# For some reason the overhead increases over time
# With RPi.GPIO, the overhead is slightly less, about 0.15 ms of overhead
meth = 'pigpio'
if meth == 'pigpio':
    correction_factor = 0.0004
elif meth == 'rpi':
    correction_factor = 0.00015
else:
    1/0

# How long to make the pulse, essentially the minimum possible
pulse_time = 1e-6 # min

# Use the isi to set the period
desired_frequency = 3000
isi = 1 / desired_frequency

# Apply the correction factor to the ISI
corrected_isi = isi - correction_factor

# Floor the ISI
if corrected_isi < 1e-8:
    corrected_isi = 1e-8

print(f'will wait {corrected_isi} s')

# Run
now = datetime.datetime.now()
n_steps = 0
while True:
    
    if meth == 'pigpio':
        pig.write(26, 1)
        time.sleep(pulse_time)
        pig.write(26, 0)
        time.sleep(corrected_isi)
    elif meth == 'rpi':
        GPIO.output(26, 1)
        time.sleep(pulse_time)
        GPIO.output(26, 0)
        time.sleep(corrected_isi)
    else:
        1/0
    
    n_steps += 1
    if np.mod(n_steps, desired_frequency) == 0:
        time_taken = (datetime.datetime.now() - now).total_seconds()
        print(f'{n_steps} in {time_taken} = {n_steps / time_taken}')

