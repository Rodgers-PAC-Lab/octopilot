from . import controllers
import json
import argparse

## Use argparse to identify the box that we are controlling
# Set up argument parsing to select box
parser = argparse.ArgumentParser(
    description="Load parameters for a specific box.")
parser.add_argument(
    'json_filename', type=str, 
    help="The name of the JSON file (without 'configs/' and '.json')",
    )
args = parser.parse_args()


## TODO: move to shared location
GIT_PATH = '/home/mouse/dev/paclab_sukrith'

def load_params(json_filename):
    """Loads params from `json_filename` and returns"""
    # Constructing the full path to the config file
    param_directory = f"{GIT_PATH}/gui/configs/{json_filename}.json"

    # Load the parameters from the specified JSON file
    with open(param_directory, "r") as p:
        params = json.load(p)
    
    return params

params = load_params(args.json_filename)
dispatcher = controllers.Dispatcher(params)
dispatcher.main_loop()
    
    
    
