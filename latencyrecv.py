# Importing necessary libraries
import sys
import zmq
import numpy as np
import time
import os
import math
import pyqtgraph as pg
import random
import csv
import json
import argparse
from datetime import datetime
from PyQt5.QtCore import QTimer, QTime

# Constructing the full path to the config file
param_directory = f"gui/configs/{args.json_filename}.json"

# Load the parameters from the specified JSON file
with open(param_directory, "r") as p:
    params = json.load(p)

# Fetching all the ports to use for the trials    
active_nosepokes = [int(i) for i in params['active_nosepokes']]

# Variable to keep track of the current task
current_task = None
current_time = None

# Setting up ZMQ context to send and receive information about poked ports
self.context = zmq.Context()
self.socket = self.context.socket(zmq.ROUTER)
self.socket.bind("tcp://*" + params['worker_port'])  # Change Port number if you want to run multiple instances

# Method to handle the update of Pis
@pyqtSlot()
def update_Pi(self):
    current_time = datetime.now()
    elapsed_time = current_time - self.initial_time

    # Update the last poke timestamp whenever a poke event occurs
    self.last_poke_timestamp = current_time

    try:
        # Receive message from the socket
        identity, message = self.socket.recv_multipart()
        self.identities.add(identity)
        message_str = message.decode('utf-8')
        
        # Message to signal if pis are connected
        if "rpi" in message_str:
            print_out("Connected to Raspberry Pi:", message_str)
        
        # Message to stop updates if the session is stopped
        if message_str.strip().lower() == "stop":
            print_out("Received 'stop' message, aborting update.")
            return
        
        # Sending the initial message to start the loop
        self.socket.send_multipart([identity, bytes(f"Reward Port: {self.reward_port}", 'utf-8')])

        # Starting next session
        if message_str.strip().lower() == "start":
            self.socket.send_multipart([identity, bytes(f"Reward Port: {self.reward_port}", 'utf-8')])

        # Statement to keep track of the current parameters 
        if "Current Parameters" in message_str:
            sound_parameters = message_str
            print_out("Updated:", message_str)
            
            # Remove the "Current Parameters - " part and strip any leading/trailing whitespace
            param_string = sound_parameters.split("-", 1)[1].strip()
            
            # Extract parameters
            params = {}
            for param in param_string.split(','):
                key, value = param.split(':')
                params[key.strip()] = value.strip()
            
            # Extract and convert the values
            self.current_amplitude = float(params.get("Amplitude", 0))
            self.current_target_rate = float(params.get("Rate", "0").split()[0])
            self.current_target_temporal_log_std = float(params.get("Irregularity", "0").split()[0])
            self.current_center_freq = float(params.get("Center Frequency", "0").split()[0])
            self.current_bandwidth = float(params.get("Bandwidth", "0"))

        else:
            poked_port = int(message_str)
            # Check if the poked port is the same as the last rewarded port
            if poked_port == self.last_rewarded_port:
                 # If it is, do nothing and return
                    return

            if 1 <= poked_port <= self.total_ports:
                poked_port_index = self.label_to_index.get(message_str)
                poked_port_signal = self.Pi_signals[poked_port_index]

                if poked_port == self.reward_port:
                    color = "green" if self.trials == 0 else "blue"
                    if self.trials > 0:
                        self.trials = 0
                else:
                    color = "red"
                    self.trials += 1
                    self.current_poke += 1

                poked_port_signal.set_color(color)
                self.poked_port_numbers.append(poked_port)
                print_out("Sequence:", self.poked_port_numbers)
                self.last_pi_received = identity

                self.pokedportsignal.emit(poked_port, color)
                self.reward_ports.append(self.reward_port)
                self.update_unique_ports()
                

                if color == "green" or color == "blue":
                    self.current_poke += 1
                    self.current_completed_trials += 1
                    for identity in self.identities:
                        self.socket.send_multipart([identity, bytes(f"Reward Poke Completed: {self.reward_port}", 'utf-8]')])
                    self.last_rewarded_port = self.reward_port   
                    self.reward_port = self.choose()
                    self.trials = 0
                    print_out(f"Reward Port: {self.reward_port}")
                    if color == "green":
                        self.current_correct_trials += 1 
                        self.current_fraction_correct = self.current_correct_trials / self.current_completed_trials

                    index = self.index_to_label.get(poked_port_index)
                    
                    # Reset color of all non-reward ports to gray and reward port to green
                    for index, Pi in enumerate(self.Pi_signals):
                        if index + 1 == self.reward_port:
                            Pi.set_color("green")
                        else:
                            Pi.set_color("gray")

                    for identity in self.identities:
                        self.socket.send_multipart([identity, bytes(f"Reward Port: {self.reward_port}", 'utf-8')])
                        
                
                self.pokes.append(self.current_poke)
                self.timestamps.append(elapsed_time)
                self.amplitudes.append(self.current_amplitude)
                self.target_rates.append(self.current_target_rate)
                self.target_temporal_log_stds.append(self.current_target_temporal_log_std)
                self.center_freqs.append(self.current_center_freq)
                self.completed_trials.append(self.current_completed_trials)
                self.correct_trials.append(self.current_correct_trials)
                self.fc.append(self.current_fraction_correct)
    
    except ValueError:
        pass
        #print_out("Unknown message:", message_str)