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

# Load parameters of the specified box
box_params = load_params.load_box_params(args.json_filename)

# Load parameters of the task
# TODO: make this configurable
task_params = load_params.load_task_params('single_sound_source')
mouse_params = load_params.load_mouse_params('mouse1')

# Start
dispatcher = controllers.Dispatcher(box_params, task_params, mouse_params)
dispatcher.main_loop()
    
    
    
