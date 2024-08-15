## Main script that runs the GUI on the desktop
# Must be run in "sukrith" conda environment
# Run this script as follows:
#   python3 -m paclab_sukrith.gui.start_gui BOXNAME
# BOXNAME must match a configuration file in gui/configs
# 
# Current boxes:
#   box1 - Testing on seaturtle computer 
#   box2-5 - Behavior Boxes 
#
# TODO: 
# Document what each class in this script does.
# Separate the classes that are for running the GUI from the classes
# that interact with the Pi and run the task 
# Put the ones that run the GUI in another script and import them here


## Module imports
# shared defines all widgets
from . import main_window

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
    app = QApplication(sys.argv)
    
    # Instantiate a MainWindow
    this_main_window = main_window.MainWindow(args.json_filename)
    
    # TODO: Sukrith what does this do?
    """
    '.exec() is used to to enter the main loop and run the different widgets on 
    the GUI until it is closed (which is when sys.exit() is called)
    """
    sys.exit(app.exec())
