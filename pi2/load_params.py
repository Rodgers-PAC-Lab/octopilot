"""Functions to load parameters for this pi

load_params : Load the configuration parameters
load_pins : Load the pin numbers
"""

import socket

def load_params_file():
    """Load parameters
    
    Returns: dict of parameters
    """
    # Get the hostname of this pi and use that as its name
    pi_hostname = socket.gethostname()
    pi_name = str(pi_hostname)

    # Load the config parameters for this pi
    # Doc for these params is in README
    param_directory = f"/home/pi/dev/paclab_sukrith/pi/configs/pis/{pi_name}.json"
    with open(param_directory, "r") as p:
        params = json.load(p)    

def load_pins():
    """Load pin numbers
    
    Returns : dict of pin numbers
    """
    pin_directory = f"/home/pi/dev/paclab_sukrith/pi/configs/pins.json"
    with open(pin_directory, "r") as n:
        pins = json.load(n)
