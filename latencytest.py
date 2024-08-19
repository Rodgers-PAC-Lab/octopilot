## Script to test the latency of ZMQ messages 

import zmq
import pigpio
import numpy as np
import os
import jack
import time
from datetime import datetime
import threading
import random
import socket as sc
import itertools
import queue
import json 
import multiprocessing as mp

## Killing previous pigpiod and jackd background processes
os.system('sudo killall pigpiod')
os.system('sudo killall jackd')

# Wait long enough to make sure they are killed
time.sleep(1)

## Starting pigpiod and jackd background processes
# Start pigpiod
""" 
Daemon Parameters:    
    -t 0 : use PWM clock (otherwise messes with audio)
    -l : disable remote socket interface (not sure why)
    -x : mask the GPIO which can be updated (not sure why; taken from autopilot)
 Runs in background by default (no need for &)
 """
os.system('sudo pigpiod -t 0 -l -x 1111110000111111111111110000')
time.sleep(1)

# Start jackd
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
os.system(
    'jackd -P75 -p16 -t2000 -dalsa -dhw:sndrpihifiberry -P -r192000 -n3 -s &')
time.sleep(1)


## Load parameters for this pi
# Get the hostname of this pi and use that as its name
pi_hostname = sc.gethostname()
pi_name = str(pi_hostname)

# Load the config parameters for this pi
"""
Parameters for each pi in the behavior box
   identity: The name of the pi (set according to its hostname)
   gui_ip: The IP address of the computer that runs the GUI 
   poke_port: The network port dedicated to receiving information about pokes
   config_port: The network port used to send all the task parameters for any saved mouse
   nosepoke_type (L/R): This parameter is to specify the type of nosepoke sensor. Nosepoke sensors are of two types 
        OPB901L55 and OPB903L55 - 903 has an inverted rising edge/falling edge which means that the functions
        being called back to on the triggers need to be inverted.   
   nosepoke_id (L/R): The number assigned to the left and right ports of each pi 
"""

# Load parameters for this pi
param_directory = f"pi/configs/pis/{pi_name}.json"
with open(param_directory, "r") as p:
    params = json.load(p)

# Pigpio configuration
a_state = 0
count = 0
nosepoke_pinL = 8
nosepoke_pinR = 15
nosepokeL_id = params['nosepokeL_id']
nosepokeR_id = params['nosepokeR_id']

left_poke_detected = False
right_poke_detected = False
current_port_poked = None
timestamp = None

# Callback function for left nosepoke
def poke_inL(pin, level, tick):
    global a_state, left_poke_detected
    a_state = 0
    if left_poke_detected:
        print("Left poke detected!")
        pig.set_mode(17, pigpio.OUTPUT)
        pig.write(17, 1 if params['nosepokeL_type'] == "901" else 0)
    left_poke_detected = False

# Callback function for right nosepoke
def poke_inR(pin, level, tick):
    global a_state, right_poke_detected
    a_state = 0
    if right_poke_detected:
        print("Right poke detected!")
        pig.set_mode(10, pigpio.OUTPUT)
        pig.write(10, 1 if params['nosepokeR_type'] == "901" else 0)
    right_poke_detected = False

# Callback function when a left nosepoke is detected
def poke_detectedL(pin, level, tick):
    global a_state, count, left_poke_detected, current_port_poked
    a_state = 1
    count += 1
    left_poke_detected = True
    print("Poke Completed (Left)")
    print("Poke Count:", count)
    current_port_poked = nosepokeL_id
    pig.set_mode(17, pigpio.OUTPUT)
    pig.write(17, 0 if params['nosepokeL_type'] == "901" else 1)
    try:
        timestamp = datetime.now()
        print(f"Sending nosepoke_id = {nosepokeL_id}")
        poke_socket.send_string(str(timestamp))
    except Exception as e:
        print("Error sending nosepoke_id:", e)

# Callback function when a right nosepoke is detected
def poke_detectedR(pin, level, tick):
    global a_state, count, right_poke_detected, current_port_poked
    a_state = 1
    count += 1
    right_poke_detected = True
    print("Poke Completed (Right)")
    print("Poke Count:", count)
    current_port_poked = nosepokeR_id
    pig.set_mode(10, pigpio.OUTPUT)
    pig.write(10, 0 if params['nosepokeR_type'] == "901" else 1)
    try:
        timestamp = datetime.now()
        print(f"Sending nosepoke_id = {nosepokeR_id}")
        poke_socket.send_string(str(timestamp))
    except Exception as e:
        print("Error sending nosepoke_id:", e)

# Raspberry Pi's identity
pi_identity = params['identity']

# Creating a DEALER socket for communication
poke_context = zmq.Context()
poke_socket = poke_context.socket(zmq.DEALER)
poke_socket.identity = bytes(f"{pi_identity}", "utf-8")
router_ip = "tcp://" + f"{params['gui_ip']}:{params['poke_port']}"
poke_socket.connect(router_ip)
poke_socket.send_string(f"{pi_identity}")

# Set up pigpio and callbacks
pig = pigpio.pi()
pig.callback(nosepoke_pinL, pigpio.FALLING_EDGE, poke_inL)
pig.callback(nosepoke_pinL, pigpio.RISING_EDGE, poke_detectedL)
pig.callback(nosepoke_pinR, pigpio.FALLING_EDGE, poke_inR)
pig.callback(nosepoke_pinR, pigpio.RISING_EDGE, poke_detectedR)

# Create a Poller object
poller = zmq.Poller()
poller.register(poke_socket, zmq.POLLIN)

# Main loop to keep the program running and exit when it receives an exit command
try:
    while True:
        socks = dict(poller.poll(100))
        if poke_socket in socks and socks[poke_socket] == zmq.POLLIN:
            msg = poke_socket.recv_string()
            if msg.startswith("Latency:"):
                print(msg)
            else:
                print("Unknown message received:", msg)

except KeyboardInterrupt:
    pig.stop()

finally:
    poke_socket.close()
    poke_context.term()
