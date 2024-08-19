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
socket = context.socket(zmq.ROUTER)
socket.bind("tcp://*:5555")  # Change Port number if you want to run multiple instances

# Create a poller object to handle the socket
poller = zmq.Poller()
poller.register(socket, zmq.POLLIN)

# Method to handle the update of Pis
def update():
    events = dict(poller.poll(1000))  # Polling with a timeout of 1000 ms
    if socket in events:
        try:
            # Receive message from the socket
            message = socket.recv_string(zmq.NOBLOCK)
            recv_time = datetime.now()
            pi_time = datetime.strptime(message, '%Y-%m-%d %H:%M:%S.%f')
            latency = recv_time - pi_time
            print(f"Latency: {latency}")
        except ValueError:
            print(f"Received an unknown message: {message}")

# Main loop
while True:
    update()
