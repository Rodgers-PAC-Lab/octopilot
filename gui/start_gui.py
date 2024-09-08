## Main script that runs the GUI on the desktop
# Must be run in "sukrith" conda environment
# Run this script as follows:
#   python3 -m paclab_sukrith.gui.start_gui BOXNAME
# BOXNAME must match a configuration file in gui/configs
# 
# Current boxes:
#   box1 - Testing on seaturtle computer 
#   box2-5 - Behavior Boxes 


## Module imports
# shared defines all widgets
from . import main_window
from . import controllers
from ..shared import load_params

# This defines standard QApplication
from PyQt5.QtWidgets import QApplication

# For getting info from the command line
import argparse
import sys


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


## Start
if __name__ == '__main__':
    # Create a QApplication
    """
    QApplication manages the inital settings of the GUI. We pass sys.argv as an 
    argument to let it know that the settings for each box might be different 
    (for example,the particular log folder to use, the mice saved for that box etc.).
    Right now the settings for all boxes have the same directories but we can use 
    different locations to save session results and tasks for each box. 
    """
    # Apparently QApplication needs sys.argv for some reason
    # https://stackoverflow.com/questions/27940378/why-do-i-need-sys-argv-to-start-a-qapplication-in-pyqt
    app = QApplication([])#sys.argv)
    
    # Instantiate a MainWindow
    dispatcher = controllers.Dispatcher(box_params, task_params, mouse_params)
    this_main_window = main_window.MainWindow(dispatcher)
    
    """
    '.exec() is used to to enter the main loop and run the different widgets on 
    the GUI until it is closed (which is when sys.exit() is called)
    """
    sys.exit(app.exec())
