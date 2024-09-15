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
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget
from PyQt5.QtCore import QObject, pyqtSignal, QThread

# For getting info from the command line
import threading
import argparse
import sys
import signal


## Use argparse to identify the box, mouse, and task
parser = argparse.ArgumentParser(
    description="Start octopilot for a specific box, mouse, and task.")

# Add each argument
parser.add_argument(
    'box', 
    nargs='?',
    type=str, 
    help=(
        "The name of the box. There must be a matching JSON file at "
        "octopilot/config/box/boxname.json"
        ),
    default='box1',
    )

parser.add_argument(
    'mouse', 
    nargs='?',
    type=str, 
    help=(
        "The name of the mouse. There must be a matching JSON file at "
        "octopilot/config/mouse/mousename.json"
        ),
    default='mouse1',
    )

parser.add_argument(
    'task', 
    nargs='?',
    type=str, 
    help=(
        "The name of the task. There must be a matching JSON file at "
        "octopilot/config/task/taskname.json"
        ),
    default='single_sound_source',
    )

# Parse the args
args = parser.parse_args()


## Load parameters of the specified box, task, and mouse
box_params = load_params.load_box_params(args.box)
task_params = load_params.load_task_params(args.task)
mouse_params = load_params.load_mouse_params(args.mouse)


## Start
if __name__ == '__main__':
    # Apparently QApplication needs sys.argv for some reason
    # https://stackoverflow.com/questions/27940378/why-do-i-need-sys-argv-to-start-a-qapplication-in-pyqt
    app = QApplication(sys.argv)
    
    # Make CTRL+C work to close the GUI
    # https://stackoverflow.com/questions/4938723/what-is-the-correct-way-to-make-my-pyqt-application-quit-when-killed-from-the-co
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Instantiate a MainWindow
    win = main_window.MainWindow(box_params, task_params, mouse_params)
    win.show()
    sys.exit(app.exec())    
