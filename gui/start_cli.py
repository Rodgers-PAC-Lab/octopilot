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
params = load_params(args.json_filename)
dispatcher = controllers.Dispatcher(params)
dispatcher.main_loop()
    
    
    
