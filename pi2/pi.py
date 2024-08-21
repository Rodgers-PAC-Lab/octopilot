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


## KILLING PREVIOUS / EXISTING BACKGROUND PROCESSES
os.system('sudo killall pigpiod')
os.system('sudo killall jackd')

# Wait long enough to make sure they are killed
# TODO: try lower values and find the lowest one that reliably works
# TODO: probe to make sure pigpiod and jackd actually got killed
time.sleep(1)


## STARTING PIGPIOD AND JACKD BACKGROUND PROCESSES 
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


## LOADING PARAMETERS FOR THE PI 
# Get the hostname of this pi and use that as its name
pi_hostname = sc.gethostname()
pi_name = str(pi_hostname)

# Load the config parameters for this pi
# Doc for these params is in README
param_directory = f"/home/pi/dev/paclab_sukrith/pi/configs/pis/{pi_name}.json"
with open(param_directory, "r") as p:
    params = json.load(p)    

# Loading pin values 
pin_directory = f"/home/pi/dev/paclab_sukrith/pi/configs/pins.json"
with open(pin_directory, "r") as n:
    pins = json.load(n)


## Defining a common queue to be used by SoundPlayer and SoundChooser
# Initializing queues 
sound_queue = mp.Queue()
nonzero_blocks = mp.Queue()

# Lock for thread-safe set_channel() updates
qlock = mp.Lock()
nb_lock = mp.Lock()

# Define a client to play sounds
sound_chooser = SoundQueue()
sound_player = SoundPlayer(name='sound_player')

# Raspberry Pi's identity (Interchangeable with pi_name. 
# This implementation is from before I was using the Pis host name)
pi_identity = params['identity']


## INITIALIZING NETWORK CONNECTION
"""
In order to communicate with the GUI, we create two sockets: 
    poke_socket and json_socket
Both these sockets use different ZMQ contexts and are used in different 
parts of the code, this is why two network ports need to be used 
    * poke_socket: Used to send and receive poke-related information.
        - Sends: Poked Port, Poke Times 
        - Receives: Reward Port for each trial, Commands to Start/Stop the 
        session, Exit command to end program
    * json_socket: Used to strictly receive task parameters from the GUI 
    (so that audio parameters can be set for each trial)
"""
# Creating a DEALER socket for communication regarding poke and poke times
poke_context = zmq.Context()
poke_socket = poke_context.socket(zmq.DEALER)

# Setting the identity of the socket in bytes
poke_socket.identity = bytes(f"{pi_identity}", "utf-8") 

# Creating a SUB socket and socket for receiving task parameters 
# (stored in json files)
json_context = zmq.Context()
json_socket = json_context.socket(zmq.SUB)

## Connect to the server
# Connecting to the GUI IP address stored in params
router_ip = "tcp://" + f"{params['gui_ip']}" + f"{params['poke_port']}" 
poke_socket.connect(router_ip) 

# Send the identity of the Raspberry Pi to the server
poke_socket.send_string(f"{pi_identity}") 

# Print acknowledgment
print(f"Connected to router at {router_ip}")  

# Connecting to json socket
router_ip2 = "tcp://" + f"{params['gui_ip']}" + f"{params['config_port']}"
json_socket.connect(router_ip2) 

# Subscribe to all incoming messages containing task parameters 
json_socket.subscribe(b"")

# Print acknowledgment
print(f"Connected to router at {router_ip2}")

# Creating a poller object for both sockets that will be used to 
# continuously check for incoming messages
poller = zmq.Poller()
poller.register(poke_socket, zmq.POLLIN)
poller.register(json_socket, zmq.POLLIN)


## CONFIGURING PIGPIO AND RELATED FUNCTIONS 
# TODO: move these methods into a Nosepoke object. That object should be
# defined in another script and imported here

# Count used to display how many pokes have happened on the pi terminal
count = 0 

# Assigning pins to variables 
nosepoke_pinL = pins['nosepoke_l']
nosepoke_pinR = pins['nosepoke_r']
led_red_l = pins['led_red_l']
led_red_r = pins['led_red_r']
led_blue_l = pins['led_blue_l']
led_blue_r = pins['led_blue_r']
led_green_l = pins['led_green_l']
led_green_r = pins['led_green_r']
valve_l = pins['solenoid_l']
valve_r = pins['solenoid_r']

# Assigning the port number for left and right ports
nosepokeL_id = params['nosepokeL_id']
nospokeR_id = params['nosepokeR_id']

# Global variables for which port the poke was detected at
left_poke_detected = False
right_poke_detected = False

# Currently, this version still uses messages from the GUI to determine 
# when to reward correct pokes. I included this variable to track the port 
# being poked to make the pi able to reward independent of the GUI. 
# I was working on implementing this in another branch but 
# have not finished it yet. Can work on it if needed
current_port_poked = None

def stop_session():
    """Runs when a session is stopped
    
    Flow
    ----
    * It turns off all active LEDs, 
    * resets all the variables used for tracking to None, 
    * stops playing sound,
    * and empties the queue.
    """
    global current_led_pin, prev_port
    hardware.flash()
    current_led_pin = None
    prev_port = None
    pig.write(led_red_l, 0)
    pig.write(led_red_r, 0)
    pig.write(led_green_l, 0)
    pig.write(led_green_r, 0)
    sound_chooser.set_channel('none')
    sound_chooser.empty_queue()
    sound_chooser.running = False

# Initializing pigpio and assigning the defined functions 
pig = pigpio.pi()

# Excutes when there is a falling edge on the voltage of the pin (when poke is completed)
pig.callback(nosepoke_pinL, pigpio.FALLING_EDGE, poke_inL) 

# Executes when there is a rising edge on the voltage of the pin (when poke is detected) 
pig.callback(nosepoke_pinL, pigpio.RISING_EDGE, poke_detectedL) 

pig.callback(nosepoke_pinR, pigpio.FALLING_EDGE, poke_inR)
pig.callback(nosepoke_pinR, pigpio.RISING_EDGE, poke_detectedR)

# Setting up LED parameters
pwm_frequency = 1
pwm_duty_cycle = 50


## Initializing variables for the sound parameters 
# (that will be changed when json file is sent to the Pi)
# Range of rates at which sound has to be played
rate_min = 0.0 
rate_max = 0.0

# Range of irregularity for each trial
irregularity_min = 0.0
irregularity_max = 0.0

# Range of amplitudes
amplitude_min = 0.0
amplitude_max = 0.0


## MAIN LOOP
def update_sound_chooser(config_data, sound_chooser, sound_player):
    """Use config_data to update acoustic parameters on sound_chooser
    
    """
    # Debug print
    print(config_data)

    # Updating parameters from the JSON data sent by GUI
    rate_min = config_data['rate_min']
    rate_max = config_data['rate_max']
    irregularity_min = config_data['irregularity_min']
    irregularity_max = config_data['irregularity_max']
    amplitude_min = config_data['amplitude_min']
    amplitude_max = config_data['amplitude_max']
    center_freq_min = config_data['center_freq_min']
    center_freq_max = config_data['center_freq_max']
    bandwidth = config_data['bandwidth']
    
    # Update the Sound Queue with the new acoustic parameters
    # TODO: Either update_parameters or pass as kwargs but not both
    sound_chooser.update_parameters(
        rate_min, rate_max, irregularity_min, irregularity_max, 
        amplitude_min, amplitude_max, center_freq_min, center_freq_max, 
        bandwidth)
    sound_chooser.initialize_sounds(
        sound_player.blocksize, sound_player.fs, 
        sound_chooser.amplitude, sound_chooser.target_highpass, 
        sound_chooser.target_lowpass)
    sound_chooser.set_sound_cycle()
    
    # Debug print
    print("Parameters updated")    


def start_playing(sound_chooser, channel):
    sound_chooser.running = True
    sound_chooser.empty_queue()
    sound_chooser.set_channel(channel)
    sound_chooser.set_sound_cycle()
    sound_chooser.play()    

def start_flashing(pig, led_pin)
    # Writing to the LED pin such that it blinks acc to the parameters 
    pig.set_mode(led_pin, pigpio.OUTPUT)
    pig.set_PWM_frequency(led_pin, pwm_frequency)
    pig.set_PWM_dutycycle(led_pin, pwm_duty_cycle)

def handle_reward_port_message(msg):
    ## This specifies which port to reward
    # Debug print
    print(msg)
    
    # Extract the integer part from the message
    msg_parts = msg.split()
    if len(msg_parts) != 3 or not msg_parts[2].isdigit():
        print("Invalid message format.")
        continue
    
    # Assigning the integer part to a variable
    value = int(msg_parts[2])  
    
    # Turn off the previously active LED if any
    if current_led_pin is not None:
        pig.write(current_led_pin, 0)
    
    # Depending on value, either start playing left, start playing right,
    # or 
    if value == int(params['nosepokeL_id']):
        # Start playing and flashing
        start_playing(sound_chooser, 'left')
        start_flashing(led_green_l)

        # Keep track of which port is rewarded and which pin
        # is rewarded
        prev_port = value
        current_led_pin = led_green_l

    elif value == int(params['nosepokeR_id']):
        # Start playing and flashing
        start_playing(sound_chooser, 'right')
        start_flashing(led_green_r)
        
        # Keep track of which port is rewarded and which pin
        # is rewarded
        prev_port = value
        current_led_pin = led_pin
    
    else:
        # In what circumstance would this happen?
        # Current Reward Port
        prev_port = value
        print(f"Current Reward Port: {value}")
    
    prev_port = value
    
def reward_and_end_trial(sound_chooser, poke_socket):
    # This seems to occur when the GUI detects that the poked
    # port was rewarded. This will be too slow. The reward port
    # should be opened if it knows it is the rewarded pin. 
    # Tried to implement this logic within the Pi itself. 
    # Can work on it more if needed
    
    # Emptying the queue completely
    sound_chooser.running = False
    sound_chooser.set_channel('none')
    sound_chooser.empty_queue()

    # Flashing all lights and opening Solenoid Valve
    flash()
    open_valve(prev_port)
    
    # Updating all the parameters that will influence the next trial
    sound_chooser.update_parameters(
        rate_min, rate_max, irregularity_min, irregularity_max, 
        amplitude_min, amplitude_max, center_freq_min, center_freq_max, 
        bandwidth)
    poke_socket.send_string(
        sound_chooser.update_parameters.parameter_message)
    
    # Turn off the currently active LED
    if current_led_pin is not None:
        pig.write(current_led_pin, 0)
        print("Turning off currently active LED.")
        current_led_pin = None  # Reset the current LED
    else:
        print("No LED is currently active.")

def handle_message_on_poke_socket(msg, poke_socket, sound_chooser, sound_player):
    """Handle a message received on poke_socket
    
    poke_socket handles messages received from the GUI that are used 
    to control the main loop. 
    The functions of the different messages are as follows:
    'exit' : terminates the program completely whenever received and 
        closes it on all Pis for a particular box
    'stop' : stops the current session and sends a message back to the 
        GUI to stop plotting. The program waits until it can start next session 
    'start' : used to start a new session after the stop message pauses 
        the main loop
    'Reward Port' : this message is sent by the GUI to set the reward port 
        for a trial.
    The Pis will receive messages of ports of other Pis being set as the 
        reward port, however will only continue if the message contains 
        one of the ports listed in its params file
    'Reward Poke Completed' : Currently 'hacky' logic used to signify the 
        end of the trial. If the string sent to the GUI matches the 
        reward port set there it clears all sound parameters and opens 
        the solenoid valve for the assigned reward duration. The LEDs 
        also flash to show a trial was completed 
    """
    stop_running = False
    
    # Different messages have different effects
    if msg == 'exit': 
        # Condition to terminate the main loop
        stop_session()
        print("Received exit command. Terminating program.")
        
        # Deactivating the Sound Player before closing the program
        sound_player.client.deactivate()
        
        # Exit the loop
        stop_running = True  
    
    elif msg == 'stop':
        # Receiving message from the GUI to stop the current session 
        # Stopping all currently active elements and waiting for next session to start
        stop_session()
        
        # Sending stop signal wirelessly to stop update function
        try:
            poke_socket.send_string("stop")
        except Exception as e:
            print("Error stopping session", e)

        print("Stop command received. Stopping sequence.")
        continue

    elif msg == 'start':
        # Communicating with start button to start the next session
        try:
            poke_socket.send_string("start")
        except Exception as e:
            print("Error stopping session", e)
    
    elif msg.startswith("Reward Port:"):    
        handle_reward_port_message(msg)

    elif msg.startswith("Reward Poke Completed"):
        reward_and_end_trial(sound_chooser, poke_socket)
   
    else:
        print("Unknown message received:", msg)

    return stop_running


## Loop to keep the program running and exit when it receives an exit string
try:
    ## TODO: document these variables and why they are tracked
    # Initialize led_pin to set what LED to write to
    led_pin = None
    
    # Variable used to track the pin of the currently blinking LED 
    current_led_pin = None  
    
    # Tracking the reward port for each trial; does not update until reward is completed 
    prev_port = None
    
    # Loop forever
    while True:
        # Wait for events on registered sockets. Currently polls every 100ms to check for messages 
        socks = dict(poller.poll(100))
        
        # Used to continuously add frames of sound to the queue until the program stops
        sound_chooser.append_sound_to_queue_as_needed()
        
        ## Check for incoming messages on json_socket
        if json_socket in socks and socks[json_socket] == zmq.POLLIN:
            # If so, use it to update the acoustic parameters
            # Setting up json socket to wait to receive messages from the GUI
            json_data = json_socket.recv_json()

            # Deserialize JSON data
            config_data = json.loads(json_data)
            
            # Use that data to update parameters in sound_chooser
            update_sound_chooser(config_data, sound_chooser, sound_player)

            
        ## Check for incoming messages on poke_socket
        if poke_socket in socks and socks[poke_socket] == zmq.POLLIN:
            # Waiting to receive message strings that control the main loop
            msg = poke_socket.recv_string()  
    
            stop_running = handle_message_on_poke_socket(
                msg, poke_socket, sound_chooser, sound_player)
            
            if stop_running:
                    break

except KeyboardInterrupt:
    # Stops the pigpio connection
    pig.stop()

finally:
    ## QUITTING ALL NETWORK AND HARDWARE PROCESSES    
    # Close all sockets and contexts
    poke_socket.close()
    poke_context.term()
    json_socket.close()
    json_context.term()


















        
    
