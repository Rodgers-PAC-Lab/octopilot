## Main script that runs the GUI on the desktop
# Must be run in "octopilot" conda environment
# Run this script as follows:
#   python3 -m paclab_sukrith.gui.start_gui BOXNAME TASKNAME MOUSENAME


## Module imports
import os
import argparse
import sys
import signal

# shared defines all widgets
from . import main_window
from ..shared import load_params

# This defines standard QApplication
from PyQt5.QtWidgets import QApplication


## This is the function that is actually run
def main(box, task, mouse, sandbox_path=None):
    """Main function to run an Octopilot GUI session
    
    Generally this is called by the code block below enclosed in 
    `if __name__ == '__main__'`, but it could also be called from another
    function.
    
    box, task, mouse: str
        These are sent to load_params.load_{box|task|mouse}_params, so
        they must correspond to JSON files in the appropriate places. 
        See top-level documentation of Config Files. 

    sandbox_path : path or None
        Place to store all data files
        If None, uses CWD

    This function will choose a session name, create a sandbox directory
    for logfiles, and then start the MainWindow of the GUI, which will then
    run the task.
    """
    ## Set sandbox_path
    if sandbox_path is None:
        # Use the current working directory
        # This works because start_launcher sets the working directory
        sandbox_path = os.getcwd()

    
    ## Load parameters of the specified box, task, and mouse
    box_params = load_params.load_box_params(args.box)
    task_params = load_params.load_task_params(args.task)
    mouse_params = load_params.load_mouse_params(args.mouse)

    # Apparently QApplication needs sys.argv for some reason
    # https://stackoverflow.com/questions/27940378/why-do-i-need-sys-argv-to-start-a-qapplication-in-pyqt
    app = QApplication(sys.argv)
    
    # Make CTRL+C work to close the GUI
    # https://stackoverflow.com/questions/4938723/what-is-the-correct-way-to-make-my-pyqt-application-quit-when-killed-from-the-co
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Instantiate an OctopilotSessionWindow
    win = main_window.WheelSessionWindow(
        box_params=box_params, 
        task_params=task_params, 
        mouse_params=mouse_params, 
        sandbox_path=sandbox_path,
        )

    # Show it
    win.show()
    
    # Exit when app exec
    sys.exit(app.exec())    


# This handles argparse in case we're calling from the command line
if __name__ == '__main__':
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

    # Call main
    main(
        box=args.box,
        task=args.task,
        mouse=args.mouse,
        )
