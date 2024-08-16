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
# TODO: document everything in params
param_directory = f"pi/configs/pis/{pi_name}.json"
with open(param_directory, "r") as p:
    params = json.load(p)    

## Pigpio configuration
# TODO: move these methods into a Nosepoke object. That object should be
# defined in another script and imported here
a_state = 0
count = 0
nosepoke_pinL = 8
nosepoke_pinR = 15
nosepokeL_id = params['nosepokeL_id']
nospokeR_id = params['nosepokeR_id']

# Global variables for which nospoke was detected
left_poke_detected = False
right_poke_detected = False
current_port_poked = None
timestamp = None

# Callback function for nosepoke pin (When the nosepoke is completed)
def poke_inL(pin, level, tick):
    global a_state, left_poke_detected
    a_state = 0
    if left_poke_detected:
        # Write to left pin
        print("Left poke detected!")
        pig.set_mode(17, pigpio.OUTPUT)
        if params['nosepokeL_type'] == "901":
            pig.write(17, 1)
        elif params['nosepokeL_type'] == "903":
            pig.write(17, 0)
    # Reset poke detected flags
    left_poke_detected = False

# Callback function for nosepoke pin (When the nosepoke is completed)
def poke_inR(pin, level, tick):
    global a_state, right_poke_detected
    a_state = 0
    if right_poke_detected:
        # Write to left pin
        print("Right poke detected!")
        pig.set_mode(10, pigpio.OUTPUT)
        if params['nosepokeR_type'] == "901":
            pig.write(10, 1)
        elif params['nosepokeR_type'] == "903":
            pig.write(10, 0)
            
    # Reset poke detected flags
    right_poke_detected = False

# Callback functions for nosepoke pin (When the nosepoke is detected)
def poke_detectedL(pin, level, tick): 
    global a_state, count, left_poke_detected, current_port_poked
    a_state = 1
    count += 1
    left_poke_detected = True
    print("Poke Completed (Left)")
    print("Poke Count:", count)
    nosepoke_idL = params['nosepokeL_id']  # Set the left nosepoke_id here according to the pi
    current_port_poked = nosepoke_idL
    pig.set_mode(17, pigpio.OUTPUT)
    if params['nosepokeL_type'] == "901":
        pig.write(17, 0)
    elif params['nosepokeL_type'] == "903":
        pig.write(17, 1)
        
    # Sending nosepoke_id wirelessly
    try:
        print(f"Sending nosepoke_id = {nosepoke_idL}") 
        #poke_socket.send_string(str(nosepoke_idL))
        timestamp = datetime.now()
        poke_socket.send(bytes(timestamp, 'utf-8'))
    except Exception as e:
        print("Error sending nosepoke_id:", e)

def poke_detectedR(pin, level, tick): 
    global a_state, count, right_poke_detected, current_port_poked
    a_state = 1
    count += 1
    right_poke_detected = True
    print("Poke Completed (Right)")
    print("Poke Count:", count)
    nosepoke_idR = params['nosepokeR_id']  # Set the right nosepoke_id here according to the pi
    current_port_poked = nosepoke_idR
    pig.set_mode(10, pigpio.OUTPUT)
    if params['nosepokeR_type'] == "901":
        pig.write(10, 0)
    elif params['nosepokeR_type'] == "903":
        pig.write(10, 1)

    # Sending nosepoke_id wirelessly
    try:
        print(f"Sending nosepoke_id = {nosepoke_idR}") 
        #poke_socket.send_string(str(nosepoke_idR))
        timestamp = datetime.now()
        poke_socket.send(bytes(timestamp, 'utf-8'))

    except Exception as e:
        print("Error sending nosepoke_id:", e)


# Raspberry Pi's identity (Interchangeable with pi_name. This implementation is from before I was using the Pis host name)
pi_identity = params['identity']

## Creating a DEALER socket for communication regarding poke and poke times
poke_context = zmq.Context()
poke_socket = poke_context.socket(zmq.DEALER)

# Setting the identity of the socket in bytes
poke_socket.identity = bytes(f"{pi_identity}", "utf-8")

# Connecting to IP address (192.168.0.99 for laptop, 192.168.0.207 for seaturtle)
router_ip = "tcp://" + f"{params['gui_ip']}" + f"{params['poke_port']}" 
poke_socket.connect(router_ip) 

# Send the identity of the Raspberry Pi to the server
poke_socket.send_string(f"{pi_identity}") 

## Set up pigpio and callbacks
# TODO: rename this variable to pig or something; "pi" is ambiguous
pig = pigpio.pi()
pig.callback(nosepoke_pinL, pigpio.FALLING_EDGE, poke_inL)
pig.callback(nosepoke_pinL, pigpio.RISING_EDGE, poke_detectedL)
pig.callback(nosepoke_pinR, pigpio.FALLING_EDGE, poke_inR)
pig.callback(nosepoke_pinR, pigpio.RISING_EDGE, poke_detectedR)

## Create a Poller object
# TODO: document .. What is this?
poller = zmq.Poller()
poller.register(poke_socket, zmq.POLLIN)

## Main loop to keep the program running and exit when it receives an exit command
try:
    ## TODO: document these variables and why they are tracked
    # Initialize reward_pin variable
    reward_pin = None
    
    # Track the currently active LED
    current_pin = None  
    
    # Track prev_port
    prev_port = None
    
    ## Loop forever
    while True:
        ## Wait for events on registered sockets
        # TODO: how long does it wait? # Can be set, currently not sure
        socks = dict(poller.poll(100))
        
        ## Check for incoming messages on poke_socket
        # TODO: document the types of messages that can be sent on poke_socket 
        if poke_socket in socks and socks[poke_socket] == zmq.POLLIN:
            # Blocking receive: #flags=zmq.NOBLOCK)  
            # Non-blocking receive
            msg = poke_socket.recv_string()  
    
            if msg.startswith("Latency:"):
                print(msg)
           
            else:
                print("Unknown message received:", msg)


except KeyboardInterrupt:
    # Stops the pigpio connection
    pig.stop()

finally:
    # Close all sockets and contexts
    poke_socket.close()
    poke_context.term()
