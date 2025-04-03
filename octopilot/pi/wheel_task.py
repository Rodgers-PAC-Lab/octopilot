# First run this:
#   source ~/.venv/py3/bin/activate
#
# Then run this script in ipython
#
# To install jack the autopilot way:
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
#
# To set up hifiberry
# sudo adduser pi i2c
# sudo sed -i 's/^dtparam=audio=on/#dtparam=audio=on/g' /boot/config.txt
# sudo sed -i '$s/$/\ndtoverlay=hifiberry-dacplus\ndtoverlay=i2s-mmap\ndtoverlay=i2c-mmap\ndtparam=i2c1=on\ndtparam=i2c_arm=on/' /boot/config.txt
# echo -e 'pcm.!default {\n type hw card 0\n}\nctl.!default {\n type hw card 0\n}' | sudo tee /etc/asound.conf
#
# The first sed doesn't seem to do anything
# The second adds these lines
# dtoverlay=hifiberry-dacplus
# dtoverlay=i2s-mmap
# dtoverlay=i2c-mmap
# dtparam=i2c1=on
# dtparam=i2c_arm=on
# The final one echoes to asound.conf, which didn't formerly exist
#
# For jack realtime config https://jackaudio.org/faq/linux_rt_config.html

import pigpio
import time
import datetime
import jack
import numpy as np
#~ import shared
import os
import itertools
import importlib
#~ importlib.reload(shared)
from . import hardware

## Killing previous pigpiod and jackd background processes
os.system('sudo killall pigpiod')
os.system('sudo killall jackd')

# Wait long enough to make sure they are killed
time.sleep(1)



import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(13, GPIO.OUT)



## Starting pigpiod and jackd background processes
# Start pigpiod
# -t 0 : use PWM clock (otherwise messes with audio)
# -l : disable remote socket interface (not sure why)
# -x : mask the GPIO which can be updated (not sure why; taken from autopilot)
# Runs in background by default (no need for &)
os.system('sudo pigpiod -t 0 -l -x 1111110000111111111111110000')
time.sleep(1)

# Period size
# Default is 1024, or 5.33ms at 192kHz

# Start jackd
# https://linux.die.net/man/1/jackd
# From trial and error: options before -dalsa go to jack, options after go
# to the backend, even though some have the same abbrevation
#
# -P75 : set realtime priority to 75 (why?)
# -p16 : --port-max, this seems unnecessary
# -t2000 : client timeout limit in milliseconds
# -dalsa : driver ALSA
#
# ALSA backend options:
# -dhw:sndrpihifiberry : device to use
# -P : provide only playback ports (which suppresses a warning otherwise)
# -r192000 : set sample rate to 192000
# -n3 : set the number of periods of playback latency to 3
# -s : softmode, ignore xruns reported by the ALSA driver
# -p : size of period in frames (e.g., number of samples per chunk)
#      Must be power of 2.
#      Lower values will lower latency but increase probability of xruns.
# & : run in background
# TODO: Use subprocess to keep track of these background processes
#~ os.system(
    #~ 'jackd -P75 -p16 -t2000 -dalsa -dhw:sndrpihifiberry -P -r192000 -n3 -s &')
    
os.system(
    'jackd '
    '--realtime-priority 75 '
    '--timeout 2000 '
    '-d alsa '
    '--device hw:sndrpihifiberry ' 
    '--playback '
    '--rate 192000 '
    '--nperiods 3 '
    '--period 1024 '
    '--softmode '
    '& '
    )
time.sleep(1)


## Define audio to play
click = np.zeros((1024, 2))
click[0] = 1
click[1] = -1
audio_cycle = itertools.cycle([
    0.001 * (np.random.uniform(-1, 1, (1024, 2))),
    click,
    00 * (np.random.uniform(-1, 1, (1024, 2))),
    00 * (np.random.uniform(-1, 1, (1024, 2))),
    00 * (np.random.uniform(-1, 1, (1024, 2))),
    00 * (np.random.uniform(-1, 1, (1024, 2))),
    00 * (np.random.uniform(-1, 1, (1024, 2))),
    00 * (np.random.uniform(-1, 1, (1024, 2))),
    00 * (np.random.uniform(-1, 1, (1024, 2))),
    00 * (np.random.uniform(-1, 1, (1024, 2))),
    00 * (np.random.uniform(-1, 1, (1024, 2))),
    00 * (np.random.uniform(-1, 1, (1024, 2))),
    00 * (np.random.uniform(-1, 1, (1024, 2))),
    00 * (np.random.uniform(-1, 1, (1024, 2))),
    00 * (np.random.uniform(-1, 1, (1024, 2))),
    00 * (np.random.uniform(-1, 1, (1024, 2))),
    ])


## Keep track of pigpio.pi
pi = pigpio.pi()

# Define object for listening to wheel
wl = hardware.WheelListener(pi)

# Define object for listening to touches
#~ tl = shared.TouchListener(pi, debug_print=True)

# Define a client to play sounds
#~ sound_player = shared.SoundPlayer(audio_cycle=audio_cycle)

# Solenoid
pi.set_mode(26, pigpio.OUTPUT)
pi.write(26, 0)

def reward(duration=0.05):
    # Activate solenoid
    pi.write(26, 1)
    time.sleep(duration)
    pi.write(26, 0)    

#~ tl.touch_trigger = reward

## Loop forever
wheel_reward_thresh = 150
last_rewarded_position = 0
last_reported_time = datetime.datetime.now()
last_reward_time = datetime.datetime.now()
report_interval = 5

# Loop forever
try:
    while True:
        # Get the current time
        current_time = datetime.datetime.now()
        
        # Report if it's been long enough
        if current_time - last_reported_time > datetime.timedelta(seconds=report_interval):
            # Print out the wheel status
            #~ wl.report()

            # Print out the touch status
            #~ tl.report()
            
            last_reported_time = current_time
        
        # See how far the wheel has moved
        current_wheel_position = wl.position
        if np.abs(current_wheel_position - last_rewarded_position) > wheel_reward_thresh:
            # Set last rewarded position to current position
            last_rewarded_position = current_wheel_position
            
            # Reward
            time_since_last_reward = (current_time - last_reward_time).total_seconds()
            
            # As time_since_last_reward increases, reward gets exponentially smaller
            # When time_since_last_reward == reward_decay, the reward size
            # is 63.7% of full. 
            # As reward_decay increases, mouse has to wait longer 
            reward_decay = 0.5
            max_reward = .05
            reward_size = max_reward * (
                1 - np.exp(-time_since_last_reward / reward_decay))
            reward(reward_size)
            last_reward_time = datetime.datetime.now()
        
        #~ GPIO.output(13, True)
        #~ time.sleep(0.001)
        #~ GPIO.output(13, False)
        #~ time.sleep(0.001)
        
        print('wheel movement {} / {}'.format(
            current_wheel_position - last_rewarded_position,
            wheel_reward_thresh))
        time.sleep(.1)

except KeyboardInterrupt:
    print('shutting down')

finally:
    # Deactivate jack client
    # This stops it from playing sound
    # Could also unregister ports, etc, but this doesn't seem necessary
    # https://jackclient-python.readthedocs.io/en/0.4.5/
    #~ sound_player.client.deactivate()
    #~ sound_player.client.close()
    
    # Some stuff gets printed to the output later, this sleep gives it time
    time.sleep(1)
    
    # final message
    print('shutdown finished')