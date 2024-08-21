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


## Defining a common queue tto be used by SoundPlayer and SoundChooser
# Initializing queues 
sound_queue = mp.Queue()
nonzero_blocks = mp.Queue()

# Lock for thread-safe set_channel() updates
qlock = mp.Lock()
nb_lock = mp.Lock()

# Define a client to play sounds
sound_chooser = SoundQueue()
sound_player = SoundPlayer(name='sound_player')

# Raspberry Pi's identity (Interchangeable with pi_name. This implementation is from before I was using the Pis host name)
pi_identity = params['identity']

## INITIALIZING NETWORK CONNECTION
"""
In order to communicate with the GUI, we create two sockets: poke_socket and json_socket
Both these sockets use different ZMQ contexts and are used in different parts of the code, this is why two network ports need to be used 
    * poke_socket: Used to send and receive poke-related information.
        - Sends: Poked Port, Poke Times 
        - Receives: Reward Port for each trial, Commands to Start/Stop the session, Exit command to end program
    * json_socket: Used to strictly receive task parameters from the GUI (so that audio parameters can be set for each trial)
"""
# Creating a DEALER socket for communication regarding poke and poke times
poke_context = zmq.Context()
poke_socket = poke_context.socket(zmq.DEALER)

# Setting the identity of the socket in bytes
poke_socket.identity = bytes(f"{pi_identity}", "utf-8") 

# Creating a SUB socket and socket for receiving task parameters (stored in json files)
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

# Creating a poller object for both sockets that will be used to continuously check for incoming messages
poller = zmq.Poller()
poller.register(poke_socket, zmq.POLLIN)
poller.register(json_socket, zmq.POLLIN)

## CONFIGURING PIGPIO AND RELATED FUNCTIONS 

# TODO: move these methods into a Nosepoke object. That object should be
# defined in another script and imported here

a_state = 0 # I think a_state used to be active state, which is what I was using to before I had to differentiate left and right pokes (might be safe to remove)
count = 0 # Count used to display how many pokes have happened on the pi terminal

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

"""
Currently, this version still uses messages from the GUI to determine when to reward correct pokes. 
I included this variable to track the port being poked to make the pi able to reward independent of the GUI. 
I was working on implementing this in another branch but have not finished it yet. Can work on it if needed
"""
current_port_poked = None

"""
Setting callback functions to run everytime a rising edge or falling edge is detected 
"""
# Callback functions for nosepoke pin (When the nosepoke is detected)
# Poke at Left Port 
def poke_detectedL(pin, level, tick): 
    global a_state, count, left_poke_detected, current_port_poked
    a_state = 1
    count += 1
    left_poke_detected = True
    print("Poke Completed (Left)")
    print("Poke Count:", count)
    nosepoke_idL = nosepoke_pinL  # Set the left nosepoke_id here according to the pi 
    current_port_poked = nosepoke_idL
    
    # Making red LED turn on when a poke is detected for troubleshooting
    pig.set_mode(led_red_l, pigpio.OUTPUT)
    if params['nosepokeL_type'] == "901":
        pig.write(led_red_l, 0)
    elif params['nosepokeL_type'] == "903":
        pig.write(led_red_l, 1)
        
    # Sending nosepoke_id to the GUI wirelessly
    try:
        print(f"Sending nosepoke_id = {nosepoke_idL}") 
        poke_socket.send_string(str(nosepoke_idL))
    except Exception as e:
        print("Error sending nosepoke_id:", e)

# Poke at Right Port
def poke_detectedR(pin, level, tick): 
    global a_state, count, right_poke_detected, current_port_poked
    a_state = 1
    count += 1
    right_poke_detected = True
    print("Poke Completed (Right)")
    print("Poke Count:", count)
    nosepoke_idR = nosepoke_pinR  # Set the right nosepoke_id here according to the pi
    current_port_poked = nosepoke_idR
    
    # Making red LED turn on when a poke is detected for troubleshooting
    pig.set_mode(led_red_r, pigpio.OUTPUT)
    if params['nosepokeR_type'] == "901":
        pig.write(led_red_r, 0)
    elif params['nosepokeR_type'] == "903":
        pig.write(led_red_r, 1)

    # Sending nosepoke_id to the GUI wirelessly
    try:
        print(f"Sending nosepoke_id = {nosepoke_idR}") 
        poke_socket.send_string(str(nosepoke_idR))
    except Exception as e:
        print("Error sending nosepoke_id:", e)

# Callback function for nosepoke pin (When the nosepoke is completed)
def poke_inL(pin, level, tick):
    global a_state, left_poke_detected
    a_state = 0
    if left_poke_detected:
        # Write to left pin
        print("Left poke detected!")
        pig.set_mode(led_red_l, pigpio.OUTPUT)
        if params['nosepokeL_type'] == "901":
            pig.write(led_red_l, 1)
        elif params['nosepokeL_type'] == "903":
            pig.write(led_red_l, 0)
    # Reset poke detected flags
    left_poke_detected = False

# Callback function for nosepoke pin (When the nosepoke is completed)
def poke_inR(pin, level, tick):
    global a_state, right_poke_detected
    a_state = 0
    if right_poke_detected:
        # Write to right pin
        print("Right poke detected!")
        pig.set_mode(led_red_r, pigpio.OUTPUT)
        if params['nosepokeR_type'] == "901":
            pig.write(led_red_r, 1)
        elif params['nosepokeR_type'] == "903":
            pig.write(led_red_r, 0)
            
    # Reset poke detected flags
    right_poke_detected = False

def open_valve(port):
    """Open the solenoid valve for port to deliver reward
    *port : port number to be rewarded (1,2,3..etc.)
    *reward_value: how long the valve should be open (in seconds) [imported from task parameters sent to the pi] 
    """
    reward_value = config_data['reward_value']
    if port == int(nosepoke_pinL):
        pig.set_mode(valve_l, pigpio.OUTPUT)
        pig.write(valve_l, 1) # Opening valve
        time.sleep(reward_value)
        pig.write(valve_l, 0) # Closing valve
    
    if port == int(nosepoke_pinR):
        pig.set_mode(valve_r, pigpio.OUTPUT)
        pig.write(valve_r, 1)
        time.sleep(reward_value)
        pig.write(valve_r, 0)

# TODO: document this function
def flash():
    """
    Flashing all the LEDs whenever a trial is completed 
    """
    pig.set_mode(led_blue_l, pigpio.OUTPUT)
    pig.write(led_blue_l, 1) # Turning LED on
    pig.set_mode(led_blue_r, pigpio.OUTPUT)
    pig.write(led_blue_r, 1) 
    time.sleep(0.5)
    pig.write(led_blue_l, 0) # Turning LED off
    pig.write(led_blue_r, 0)  

def stop_session():
    """
    This function contains the logic that needs to be executed whenever a session is stopped.
    It turns off all active LEDs, resets all the variables used for tracking to None, stops playing sound
    and empties the queue
    """
    global led_pin, current_led_pin, prev_port
    flash()
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
pig.callback(nosepoke_pinL, pigpio.FALLING_EDGE, poke_inL) # Excutes when there is a falling edge on the voltage of the pin (when poke is completed)
pig.callback(nosepoke_pinL, pigpio.RISING_EDGE, poke_detectedL) # Executes when there is a rising edge on the voltage of the pin (when poke is detected) 
pig.callback(nosepoke_pinR, pigpio.FALLING_EDGE, poke_inR)
pig.callback(nosepoke_pinR, pigpio.RISING_EDGE, poke_detectedR)

# Setting up LED parameters
pwm_frequency = 1
pwm_duty_cycle = 50

## Initializing variables for the sound parameters (that will be changed when json file is sent to the Pi)
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

# Loop to keep the program running and exit when it receives an exit string
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
        # If so, use it to update the acoustic parameters
        """
        Socket is primarily used to import task parameters sent by the GUI
        Sound Parameters being updated: rate, irregularity, amplitude, center frequency        
        """
        if json_socket in socks and socks[json_socket] == zmq.POLLIN:
            # Setting up json socket to wait to receive messages from the GUI
            json_data = json_socket.recv_json()
            
            # Deserialize JSON data
            config_data = json.loads(json_data)
            
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
            sound_chooser.update_parameters(
                rate_min, rate_max, irregularity_min, irregularity_max, 
                amplitude_min, amplitude_max, center_freq_min, center_freq_max, bandwidth)
            sound_chooser.initialize_sounds(sound_player.blocksize, sound_player.fs, 
                sound_chooser.amplitude, sound_chooser.target_highpass, sound_chooser.target_lowpass)
            sound_chooser.set_sound_cycle()
            
            # Debug print
            print("Parameters updated")
            
        ## Check for incoming messages on poke_socket
        """
        poke_socket handles messages received from the GUI that are used to control the main loop. 
        The functions of the different messages are as follows:
        'exit' : terminates the program completely whenever received and closes it on all Pis for a particular box
        'stop' : stops the current session and sends a message back to the GUI to stop plotting. The program waits until it can start next session 
        'start' : used to start a new session after the stop message pauses the main loop
        'Reward Port' : this message is sent by the GUI to set the reward port for a trial.
        The Pis will receive messages of ports of other Pis being set as the reward port, however will only continue if the message contains one of the ports listed in its params file
        'Reward Poke Completed' : Currently 'hacky' logic used to signify the end of the trial. If the string sent to the GUI matches the reward port set there it
        clears all sound parameters and opens the solenoid valve for the assigned reward duration. The LEDs also flash to show a trial was completed 
        """        
        if poke_socket in socks and socks[poke_socket] == zmq.POLLIN:
            # Waiting to receive message strings that control the main loop
            msg = poke_socket.recv_string()  
    
            # Different messages have different effects
            if msg == 'exit': 
                # Condition to terminate the main loop
                stop_session()
                print("Received exit command. Terminating program.")
                
                # Deactivating the Sound Player before closing the program
                sound_player.client.deactivate()
                
                # Exit the loop
                break  
            
            # Receiving message from the GUI to stop the current session 
            if msg == 'stop':
                # Stopping all currently active elements and waiting for next session to start
                stop_session()
                
                # Sending stop signal wirelessly to stop update function
                try:
                    poke_socket.send_string("stop")
                except Exception as e:
                    print("Error stopping session", e)

                print("Stop command received. Stopping sequence.")
                continue

            # Communicating with start button to start the next session
            if msg == 'start':
                try:
                    poke_socket.send_string("start")
                except Exception as e:
                    print("Error stopping session", e)
            
            elif msg.startswith("Reward Port:"):    
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
                
                # Manipulate pin values based on the integer value
                if value == int(params['nosepokeL_id']):
                    # Starting sound the sound queue
                    sound_chooser.running = True
                    
                    # Setting the left LED to start blinking
                    led_pin = led_green_l  
                    
                    # Writing to the LED pin such that it blinks acc to the parameters 
                    pig.set_mode(led_pin, pigpio.OUTPUT)
                    pig.set_PWM_frequency(led_pin, pwm_frequency)
                    pig.set_PWM_dutycycle(led_pin, pwm_duty_cycle)
                    
                    # Playing sound from the left speaker
                    sound_chooser.empty_queue()
                    sound_chooser.set_channel('left')
                    sound_chooser.set_sound_cycle()
                    sound_chooser.play()
                    
                    # Debug message
                    print(f"Turning port {value} green")

                    # Keep track of which port is rewarded and which pin
                    # is rewarded
                    prev_port = value
                    current_led_pin = led_pin # for LED only 

                elif value == int(params['nosepokeR_id']):
                    # Starting sound
                    sound_chooser.running = True
                    
                    # Setting right LED pin to start blinking
                    led_pin = led_green_r
                    
                    # Writing to the LED pin such that it blinks acc to the parameters 
                    pig.set_mode(led_pin, pigpio.OUTPUT)
                    pig.set_PWM_frequency(led_pin, pwm_frequency)
                    pig.set_PWM_dutycycle(led_pin, pwm_duty_cycle)
                    
                    # Playing sound from the right speaker
                    sound_chooser.empty_queue()
                    sound_chooser.set_channel('right')
                    sound_chooser.set_sound_cycle()
                    sound_chooser.play()

                    # Debug message
                    print(f"Turning port {value} green")
                    
                    # Keep track of which port is rewarded and which pin
                    # is rewarded
                    prev_port = value
                    current_led_pin = led_pin
                
                else:
                    # TODO: document why this happens
                    # Current Reward Port
                    prev_port = value
                    print(f"Current Reward Port: {value}")
                
            elif msg.startswith("Reward Poke Completed"):
                # This seems to occur when the GUI detects that the poked
                # port was rewarded. This will be too slow. The reward port
                # should be opened if it knows it is the rewarded pin. 
                
                """
                Tried to implement this logic within the Pi itself. Can work on it more if needed
                """
                
                # Emptying the queue completely
                sound_chooser.running = False
                sound_chooser.set_channel('none')
                sound_chooser.empty_queue()

                # Flashing all lights and opening Solenoid Valve
                flash()
                open_valve(prev_port)
                
                # Updating all the parameters that will influence the next trialy
                sound_chooser.update_parameters(
                    rate_min, rate_max, irregularity_min, irregularity_max, 
                    amplitude_min, amplitude_max, center_freq_min, center_freq_max, bandwidth)
                poke_socket.send_string(sound_chooser.update_parameters.parameter_message)
                
                
                # Turn off the currently active LED
                if current_led_pin is not None:
                    pig.write(current_led_pin, 0)
                    print("Turning off currently active LED.")
                    current_led_pin = None  # Reset the current LED
                else:
                    print("No LED is currently active.")
           
            else:
                print("Unknown message received:", msg)

except KeyboardInterrupt:
    # Stops the pigpio connection
    pig.stop()

## QUITTING ALL NETWORK AND HARDWARE PROCESSES

finally:
    # Close all sockets and contexts
    poke_socket.close()
    poke_context.term()
    json_socket.close()
    json_context.term()


















        
    
