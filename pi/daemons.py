"""Killing and starting daemons for pigpio and jack

Methods
-------
kill_old_daemons : kill existing pigpiod and jackd
start_pigpiod : start a new pigpiod
start_jackd : start a new jackd
"""


import os
import time
import subprocess

def kill_pigpiod(verbose=True):
    """Kill existing pigpiod"""
    # Try to kill
    took_too_long = False
    try:
        proc = subprocess.run(
            ['sudo', 'killall', 'pigpiod'], capture_output=True, timeout=2)
    except subprocess.TimeoutExpired:
        # When this happens, proc will be killed and waited for
        took_too_long = True
    
    # Log what happened
    if verbose:
        if took_too_long:
            print('killing pigpiod led to a timeout: ' + str(proc))
        elif proc.returncode == 0:
            print('pigpiod successfully killed')
        elif proc.returncode == 1 and proc.stderr == b'pigpiod: no process found\n':
            print('no pigpiod to kill')
        else:
            print('while killing pigpiod, unexpected result: ' + str(proc))

def kill_jackd(sleep_time=1, verbose=True):
    """Kill existing jackd"""
    # Try to kill
    took_too_long = False
    try:
        proc = subprocess.run(
            ['killall', 'jackd'], capture_output=True, timeout=2)
    except subprocess.TimeoutExpired:
        # When this happens, proc will be killed and waited for
        took_too_long = True

    if took_too_long:
        if verbose:
            print('killing jackd led to a timeout: ' + str(proc))

    elif proc.returncode == 0:
        if verbose:
            print('jackd successfully killed')

        # For whatever reason, sometimes have to wait after killing jackd
        time.sleep(sleep_time)

    elif proc.returncode == 1 and proc.stderr == b'jackd: no process found\n':
        if verbose:
            print('no jackd to kill')

    else:
        if verbose:
            print('while killing jackd, unexpected result: ' + str(proc))


def start_pigpiod(sleep_time=1, verbose=False):
    """ 
    Daemon Parameters:    
        -t 0 : use PWM clock (otherwise messes with audio)
        -l : disable remote socket interface (not sure why)
        -x : mask the GPIO which can be updated (not sure why; taken from autopilot)
    Runs in background by default (no need for &)
    """
    took_too_long = False
    try:
        proc = subprocess.run(
            ['sudo', 'pigpiod', '-t', '0', '-l', '-x', 
            '1111110000111111111111110000'], capture_output=True, timeout=0.5)
    except subprocess.TimeoutExpired:
        # When this happens, proc will be killed and waited for
        took_too_long = True

    # Log what happened
    if took_too_long:
        raise IOError('starting pigpiod led to a timeout: ' + str(proc))
    elif proc.returncode == 0:
        if verbose:
            print('successfully started pigpiod')
    else:
        raise IOError('failed to start pigpiod: ' + str(proc))
    
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
    # Not sure why this doesn't work with subprocess.run
    proc = subprocess.Popen([
        'jackd', 
        '-P75', 
        '-p16', 
        '-t2000', 
        '-dalsa', 
        '-dhw:sndrpihifiberry', 
        '-P', 
        '-r192000', 
        '-n3', 
        '-s',
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Give jackd enough time to actually start
    time.sleep(sleep_time)
    
    return proc