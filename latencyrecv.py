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
def update():
    try:
        # Receive message from the socket
        message = self.socket.recv_string()
        recv_time = datetime.now()
        pi_time = datetime.strptime(message)
        latency = recv_time - pi_time
        print(f"Latency:", latency)

    except ValueError:
        pass
        #print_out("Unknown message:", message_str)

while True:
    update()