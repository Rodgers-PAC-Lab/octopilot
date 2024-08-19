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
param_directory = f"gui/configs/box1.json"

# Load the parameters from the specified JSON file
with open(param_directory, "r") as p:
    params = json.load(p)

# Fetching all the ports to use for the trials    
active_nosepokes = [int(i) for i in params['active_nosepokes']]

# Variable to keep track of the current task
current_task = None
current_time = None

# Setting up ZMQ context to send and receive information about poked ports
context = zmq.Context()
receiver = context.socket(zmq.ROUTER)
receiver.bind("tcp://*:5555")  # Change Port number if you want to run multiple instances

# Create a poller object to handle the socket
poller = zmq.Poller()
poller.register(receiver, zmq.POLLIN)

# Main loop to keep receiving messages
try:
    while True:
        # Poll for incoming messages with a timeout of 100ms
        socks = dict(poller.poll(100))

        if receiver in socks and socks[receiver] == zmq.POLLIN:
            print("Working")
            msg = receiver.recv_string()
            recv_time = datetime.now()
            pi_time = datetime.strptime(msg, '%Y-%m-%d %H:%M:%S.%f')
            latency = recv_time - pi_time
            print(f"Latency: {latency}")
            
except KeyboardInterrupt:
    print("Receiver script interrupted by user")

finally:
    receiver.close()
    context.term()
