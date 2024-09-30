"""Functions to load parameters for this pi

load_box_params : Load parameters for a box
load_mouse_params : Load parameters for a mouse
load_task_params : Load parameters for a task
load_pi_params : Load parameters for a pi
"""

import socket
import json
import datetime
import os

# Use this to get the location of the config files
# This hardcodes ../../config/ from here
# TODO: avoid hardcoding this
config_path = os.path.abspath(os.path.join(
    os.path.split(__file__)[0], 
    '..', 
    '..', 
    'config',
    ))

def simple_json_loader(path):
    """Simple loading function to return the JSON at `path`"""
    try:
        with open(path, 'r') as p:
            params = json.load(p)
    except json.decoder.JSONDecodeError as e:
        raise IOError(f'cannot load JSON at {path}; original exception:\n{e}')
        raise
    
    return params

def load_box_params(box):
    """Loads box params from `box.json` and returns
    
    The JSON has the following keys:
    * port (int): The port number to connect to
    * desktop_ip (str): IP address of the desktop PC running the GUI
    * camera (str): name of the connected camera
    * connected_pis : list of dict with info about each connected Pi
      Each entry has the following keys:
        * name (str): Name of the Pi. Example: 'rpi26'
        * ip (str): IP address of the Pi. Example: '192.168.0.101'
        * zmq_port (int) : What ZMQ port to connect to
            All Pis should connect to the same ZMQ port
        * left_port_name (str): Name of the Pi's left port. Example: rpi26_L
            If missing, it will be replaced with `name` + '_L'
        * right_port_name (str): Name of the Pi's right port. Example: rpi26_R
            If missing, it will be replaced with `name` + '_R'
        * left_port_position (numeric): Angular location in degrees of the 
          left port within the box. Example: 90 means east, 270 means west
        * right_port_position (numeric): Angular location in degrees of the 
          right port within the box. Example: 90 means east, 270 means west
    """
    # Constructing the full path to the config file
    full_path = os.path.join(config_path, 'box', box + '.json')

    # Load the parameters from the specified JSON file
    params = simple_json_loader(full_path)
    
    # Store the name
    params['name'] = box
    
    # Ensure 'connected_pis' is present
    if 'connected_pis' not in params:
        raise IOError(
            f'box params at {full_path} is missing entry "connected_pis"')
    
    # Set defaults
    for pi_params in params['connected_pis']:
        # Ensure 'name' is present
        if 'name' not in pi_params:
            raise IOError(
                f'box params at {full_path} is missing entry "name" '
                f'in pi {pi_params}')
        
        # Set default left_port_name
        if 'left_port_name' not in pi_params:
            pi_params['left_port_name'] = pi_params['name'] + '_L'
        
        # Set default right_port_name
        if 'right_port_name' not in pi_params:
            pi_params['right_port_name'] = pi_params['name'] + '_R'
    
    return params

def load_task_params(task):
    """Loads task params from `task.json` and returns
    
    The JSON has some set of the following keys:
    * target_amplitude : 
    "amplitude_min": 0.05,
    "amplitude_max": 0.05,
    "rate_min": 4.0,
    "rate_max": 4.0,
    "irregularity_min": -1.5,
    "irregularity_max": -1.5,
    "center_freq_min": 5000.0,
    "center_freq_max": 5000.0,
    "bandwidth": 3000.0,
    "reward_value": 0.5    
    """
    # Constructing the full path to the config file
    full_path = os.path.join(config_path, 'task', task + '.json')

    # Load the parameters from the specified JSON file
    params = simple_json_loader(full_path)

    # Store the name
    params['name'] = task

    # Return
    return params

def load_mouse_params(mouse):
    """Loads mouse params from `mouse.json` and returns
    
    The JSON has the following keys:
    * reward_value (numeric): The fraction of a default reward size that this
        mouse should receive.
    """
    # Constructing the full path to the config file
    full_path = os.path.join(config_path, 'mouse', mouse + '.json')

    # Load the parameters from the specified JSON file
    return simple_json_loader(full_path)

    # Store the name
    params['name'] = mouse

    # Return
    return params

def load_pi_params():
    """Loads pi params for this hostname and returns
    
    scoket.gethostname is used to get the hostname of this device, and then
    a matching json file for that hostname is sought.
    
    Returns: dict of parameters with keys
        box (str): Name of the box it's connected to (example: 'box1')
            This must match a JSON file in octopilot/config/box/boxname.json
            This is how the Pi knows what IP to connect to
        left_nosepoke_type and right_nosepoke_type : str, '901' or '903'
        left_nosepoke : pin number
        right_nosepoke : pin number
        left_solenoid : pin number
        right_solenoid : pin number
        left_led_red : pin number (similar for _green and _blue)
        right_led_red : pin number (similar for _green and _blue)
    
    TODO: add defaults for some of the pins that never change.
    """
    # Get the hostname of this pi and use that as its name
    pi_name = socket.gethostname()
    
    # Constructing the full path to the config file
    full_path = os.path.join(config_path, 'pi', pi_name + '.json')

    # Load the parameters from the specified JSON file
    params = simple_json_loader(full_path)

    return params
