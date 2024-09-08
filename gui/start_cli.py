from . import controllers
from ..shared import load_params
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
box_params = load_params.load_box_params(args.json_filename)
dispatcher = controllers.Dispatcher(box_params)
dispatcher.main_loop()
    
    
    
