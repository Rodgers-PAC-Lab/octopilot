"""Functions to load parameters for this pi

load_params : Load the configuration parameters
load_pins : Load the pin numbers
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
    with open(path, 'r') as p:
        params = json.load(p)
    
    return params

def load_box_params(box):
    """Loads box params from `box.json` and returns"""
    # Constructing the full path to the config file
    full_path = os.path.join(config_path, 'box', box + '.json')

    # Load the parameters from the specified JSON file
    return simple_json_loader(full_path)

def load_task_params(task):
    """Loads task params from `task.json` and returns"""
    # Constructing the full path to the config file
    full_path = os.path.join(config_path, 'task', task + '.json')

    # Load the parameters from the specified JSON file
    return simple_json_loader(full_path)

def load_mouse_params(mouse):
    """Loads mouse params from `mouse.json` and returns"""
    # Constructing the full path to the config file
    full_path = os.path.join(config_path, 'mouse', mouse + '.json')

    # Load the parameters from the specified JSON file
    return simple_json_loader(full_path)

def load_pi_params(verbose=False):
    """Loads pi params for this hostname and returns
    
    scoket.gethostname is used to get the hostname of this device, and then
    a matching json file for that hostname is sought.
    
    Returns: dict of parameters with keys
        identity : str, name of rpi
        gui_ip : str, IP address of GUI
        poke_port : str, like ':5555'
        config_port : str, like ':5556'
        nosepokeL_type and nosepokeR_type : str, '901' or '903'
        nosepokeL_id and nosepokR_id : int, nosepoke number (TODO: what is this?)    
    """
    # Get the hostname of this pi and use that as its name
    pi_name = socket.gethostname()
    
    # Constructing the full path to the config file
    full_path = os.path.join(config_path, 'pi', pi_name + '.json')

    # Load the parameters from the specified JSON file
    params = simple_json_loader(full_path)

    # verbose
    if verbose:
        dt_now = datetime.datetime.now().isoformat()
        print('{} load_params.load_params_file: Loaded params:'.format(dt_now))
        print(params)

    return params

def load_pins(verbose=False):
    """Load pin numbers

    Returns : dict of pin numbers with the following keys
        nosepoke_l
        nosepoke_r
        led_red_l
        led_red_r
        led_green_l
        led_green_r
        led_blue_l
        led_blue_r
        solenoid_l
        solenoid_r
    
    Each value is an int
    """
    pin_directory = f"/home/pi/dev/paclab_sukrith/config/pins.json"
    with open(pin_directory, "r") as n:
        pins = json.load(n)

    if verbose:
        dt_now = datetime.datetime.now().isoformat()
        print('{} load_params.load_pins: Loaded pins:'.format(dt_now))
        print(pins)

    return pins