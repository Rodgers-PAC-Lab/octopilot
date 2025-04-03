# First run this:
#   source ~/.venv/py3/bin/activate
#
# Then run this script in ipython
#
# Ensure jack is installed -- autopilot installs from source, can we install from apt?
# git clone https://github.com/jackaudio/jack2 --depth 1
# cd jack2
# ./waf configure --alsa=yes --libdir=/usr/lib/arm-linux-gnueabihf/
# ./waf build -j6
# sudo ./waf install
# sudo ldconfig
# sudo sh -c "echo @audio - memlock 256000 >> /etc/security/limits.conf"
# sudo sh -c "echo @audio - rtprio 75 >> /etc/security/limits.conf"
# cd ..
# rm -rf ./jack2

import pigpio
import time
import datetime
import jack
import numpy as np
import shared
import os
import itertools
from . import hardware

## Killing previous pigpiod and jackd background processes
os.system('sudo killall pigpiod')
os.system('sudo killall jackd')

# Wait long enough to make sure they are killed
time.sleep(1)


## Starting pigpiod and jackd background processes
# Start pigpiod
# -t 0 : use PWM clock (otherwise messes with audio)
# -l : disable remote socket interface (not sure why)
# -x : mask the GPIO which can be updated (not sure why; taken from autopilot)
# Runs in background by default (no need for &)
os.system('sudo pigpiod -t 0 -l -x 1111110000111111111111110000')
time.sleep(1)

# Start jackd
# https://linux.die.net/man/1/jackd
# -P75 : set realtime priority to 75 (why?)
# -p16 : Set the number of frames between process() calls. Must be power of 2.
#   Lower values will lower latency but increase probability of xruns.
#   Or is this --port-max?
# -t2000 : client timeout limit in milliseconds
# -dalsa : driver ALSA
#
# ALSA backend options:
# -dhw:sndrpihifiberry : device to use
# -P : provide only playback ports (why?)
# -r192000 : set sample rate to 192000
# -n3 : set the number of periods of playback latency to 3
# -s : softmode, ignore xruns reported by the ALSA driver
# & : run in background
# TODO: document these parameters
# TODO: Use subprocess to keep track of these background processes
os.system(
    'jackd -P75 -p16 -t2000 -dalsa -dhw:sndrpihifiberry -P -r192000 -n3 -s &')
time.sleep(1)


## Define audio to play
audio_cycle = itertools.cycle([
    0.01 * np.random.uniform(-1, 1, (1024, 2)),
    0.00 * np.random.uniform(-1, 1, (1024, 2)),
    ])


## Keep track of pigpio.pi
pi = pigpio.pi()

# Define object for listening to wheel
wl = hardware.WheelListener(pi)

# Define object for listening to touches
#~ tl = shared.TouchListener(pi)

# Define a client to play sounds
#~ sound_player = shared.SoundPlayer(audio_cycle=audio_cycle)

# Solenoid
pi.set_mode(26, pigpio.OUTPUT)
pi.write(26, 0)


## Loop forever
while True:
    # Print out the wheel status
    wl.do_nothing()

    # Print out the touch status
    #~ tl.report()

    time.sleep(1)