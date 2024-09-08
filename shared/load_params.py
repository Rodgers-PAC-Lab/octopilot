"""Functions to load parameters for this pi

load_params : Load the configuration parameters
load_pins : Load the pin numbers
"""

import socket
import json
import datetime


def load_box_params(json_filename):
    """Loads box params from `json_filename` and returns"""
    GIT_PATH = '/home/mouse/dev/paclab_sukrith'
    
    # Constructing the full path to the config file
    param_directory = f"{GIT_PATH}/gui/configs/{json_filename}.json"

    # Load the parameters from the specified JSON file
    with open(param_directory, "r") as p:
        params = json.load(p)
    
    return params

def load_task_params(json_filename):
    """Load task params from `json_filename` and return
    
    """
    GIT_PATH = '/home/mouse/dev/paclab_sukrith'
    
    # Constructing the full path to the config file
    param_directory = f"{GIT_PATH}/configs/tasks/{json_filename}.json"

    # Load the parameters from the specified JSON file
    with open(param_directory, "r") as p:
        params = json.load(p)
    
    return params    

def load_task_params(mouse_name):
    """Load and return parameters for mouse `mouse_name`"""
    GIT_PATH = '/home/mouse/dev/paclab_sukrith'
    
    # Constructing the full path to the config file
    param_directory = f"{GIT_PATH}/configs/mouse/{mouse_name}.json"

    # Load the parameters from the specified JSON file
    with open(param_directory, "r") as p:
        params = json.load(p)
    
    return params    

def load_pi_params(verbose=False):
    """Load pi parameters
    
    Returns: dict of parameters with keys
        identity : str, name of rpi
        gui_ip : str, IP address of GUI
        poke_port : str, like ':5555'
        config_port : str, like ':5556'
        nosepokeL_type and nosepokeR_type : str, '901' or '903'
        nosepokeL_id and nosepokR_id : int, nosepoke number (TODO: what is this?)
    """
    # Get the hostname of this pi and use that as its name
    pi_hostname = socket.gethostname()
    pi_name = str(pi_hostname)

    # Load the config parameters for this pi
    # Doc for these params is in README
    param_directory = f"/home/pi/dev/paclab_sukrith/configs/pis/{pi_name}.json"
    with open(param_directory, "r") as p:
        params = json.load(p)    

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
    pin_directory = f"/home/pi/dev/paclab_sukrith/configs/pins.json"
    with open(pin_directory, "r") as n:
        pins = json.load(n)

    if verbose:
        dt_now = datetime.datetime.now().isoformat()
        print('{} load_params.load_pins: Loaded pins:'.format(dt_now))
        print(pins)

    return pins