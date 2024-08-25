"""Killing and starting daemons for pigpio and jack

Methods
-------
kill_old_daemons : kill existing pigpiod and jackd
start_pigpiod : start a new pigpiod
start_jackd : start a new jackd
"""


import os
import time

def kill_old_daemons(sleep_time=1, verbose=False):
    """Kill existing pigpiod and jackd"""
    if verbose:
        print('killing pigpiod')
    os.system('sudo killall pigpiod')
    if verbose:
        print('killing jackd')
    os.system('sudo killall jackd')

    # Wait long enough to make sure they are killed
    # TODO: try lower values and find the lowest one that reliably works
    # TODO: probe to make sure pigpiod and jackd actually got killed
    if verbose:
        print('sleeping for {}'.format(sleep_time))
    time.sleep(sleep_time)
    if verbose:
        print('done sleeping')

def start_pigpiod(sleep_time=1, verbose=False):
    """ 
    Daemon Parameters:    
        -t 0 : use PWM clock (otherwise messes with audio)
        -l : disable remote socket interface (not sure why)
        -x : mask the GPIO which can be updated (not sure why; taken from autopilot)
    Runs in background by default (no need for &)
    """
    if verbose:
        print('starting pigpiod')
    os.system('sudo pigpiod -t 0 -l -x 1111110000111111111111110000')
    if verbose:
        print('sleeping')
    time.sleep(sleep_time)
    if verbose:
        print('done sleeping')
    
def start_jackd(sleep_time=1, verbose=False):
    """
    Daemon Parameters:
     -P75 : set realtime priority to 75 
     -p16 : --port-max, this seems unnecessary
     -t2000 : client timeout limit in milliseconds
     -dalsa : driver ALSA

    ALSA backend options:
     -dhw:sndrpihifiberry : device to use
     -P : provide only playback ports (which suppresses a warning otherwise)
     -r192000 : set sample rate to 192000
     -n3 : set the number of periods of playback latency to 3
     -s : softmode, ignore xruns reported by the ALSA driver
     -p : size of period in frames (e.g., number of samples per chunk)
          Must be power of 2.
          Lower values will lower latency but increase probability of xruns.
      & : run in background
    """
    # TODO: Use subprocess to keep track of these background processes
    if verbose:
        print('starting jackd')
    os.system(
        'jackd -P75 -p16 -t2000 -dalsa -dhw:sndrpihifiberry -P -r192000 -n3 -s &')
    if verbose:
        print('sleeping')
    time.sleep(sleep_time)
    if verbose:
        print('done sleeping')
