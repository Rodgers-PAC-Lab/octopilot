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

from . import daemons
from . import load_params


## Set up daemons
daemons.kill_old_daemons()
daemons.start_pigpiod()
daemons.start_jackd()


## LOADING PARAMETERS FOR THE PI 
params = load_params.load_params_file()
pins = load_params.load_pins()


## MAIN LOOP
class HardwareController(object):
    """Object to control the flow of behavioral sessions
    
    This object waits to be told what types of sound to play (e.g., rate,
    amplitude, etc) and it can read and write pins through pigpio. It can
    also send messages to the GUI about events that occur (e.g., pokes.
    It should not be concerned with session-level task logic like what
    port to reward next.
    """
    def __init__(self, pins, params):
        # Store received parameters
        self.pins = pins
        self.params = params

        # Set up pigpio
        # Initialize a pig to use
        self.pig = pigpio.pi()

        # Connect callbacks to pins
        set_up_pi(pig, pins)

        # This object puts frames of audio into a sound queue
        self.sound_queuer = sound.SoundQueuer()
        
        # This object pulls frames of audio from that queue and gives them
        # to a jack.Client that it contains
        # TODO: probably instantiate the jack.Client here and provide it
        self.sound_player = sound.SoundPlayer(
            name='sound_player', 
            sound_queue=self.sound_queuer.sound_queue,
            )
    
    def set_up_networking(self):
        ## Set up networking
        poke_socket = networking.set_up_poke_socket()
        json_socket = networking.set_up_json_socket()

        # Creating a poller object for both sockets that will be used to 
        # continuously check for incoming messages
        poller = zmq.Poller()
        poller.register(poke_socket, zmq.POLLIN)
        poller.register(json_socket, zmq.POLLIN)        
    
    def stop_session():
        """Runs when a session is stopped
        
        Flow
        ----
        * It turns off all active LEDs, 
        * resets all the variables used for tracking to None, 
        * stops playing sound,
        * and empties the queue.
        """
        # Flash
        hardware.flash()
        
        # Reset flags
        self.current_led_pin = None
        self.prev_port = None
        
        # Turn off pins
        self.pig.write(pins['led_red_l'], 0)
        self.pig.write(pins['led_red_r'], 0)
        self.pig.write(pins['led_green_l'], 0)
        self.pig.write(pins['led_green_r'], 0)
        
        # Turn off sound chooser
        self.sound_chooser.set_channel('none')
        self.sound_chooser.empty_queue()
        self.sound_chooser.running = False

    def update_sound_chooser(config_data):
        """Use config_data to update acoustic parameters on sound_chooser
        
        TODO: reconfigure so that we receive specific parameters for this
        trial, not ranges.
        """
        # Update the Sound Queue with the new acoustic parameters
        # TODO: Either update_parameters or pass as kwargs but not both
        sound_chooser.set_parameters(
            rate,
            amplitude,
            center_frequency,
            bandwidth,
            irregularity,
            )
        sound_chooser.set_sound_cycle()
        
        # Debug print
        print("Parameters updated")    

    def start_playing(sound_chooser, channel):
        sound_chooser.running = True
        sound_chooser.empty_queue()
        sound_chooser.set_channel(channel)
        sound_chooser.set_sound_cycle()
        sound_chooser.play()    

    def start_flashing(pig, led_pin, pwm_frequency=1, pwm_duty_cycle=50)
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
            start_flashing(pins['led_green_l'])

            # Keep track of which port is rewarded and which pin
            # is rewarded
            prev_port = value
            current_led_pin = pins['led_green_l']

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


















        
    
