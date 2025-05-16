## Main script that runs the GUI on the desktop
# Typically this script is launched by start_launcher.py 
# But you can also invoke manually like this:
#   python3 -m octopilot.desktop.start_gui BOXNAME TASKNAME MOUSENAME


## Module imports
import os
import argparse
import sys
import signal
import logging
import time

# shared defines all widgets
from . import main_window
from ..shared import load_params
from ..shared.logtools import NonRepetitiveLogger

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
    # this only works if the process ends nicely, not if the terminal 
    # window is closed. So it's not that useful
    # # https://docs.python.org/3/library/atexit.html
    # atexit.register(goodbye, 'Donny', 'nice')
    

    
    logger = NonRepetitiveLogger("start_gui.__main__")
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
    logger.addHandler(sh)
    logger.setLevel(logging.DEBUG)
    

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

    # This try/finally is no longer necessary, but kept in case we need
    # to put some kind of shutdown code
    retcode = 0 
    try:
        
        ## Instantiate an OctopilotSessionWindow
        # Pop out the main_window_name, because TrialParameterChooser tries
        # to parse all kwargs in task_params
        main_window_name = task_params.pop('main_window_name')
        
        # TODO - use main_window_name to find the right object
        if main_window_name == 'WheelSessionWindow':
            win_obj = main_window.WheelSessionWindow
        
        elif main_window_name == 'OctopilotSessionWindow':
            win_obj = main_window.OctopilotSessionWindow
        
        else:
            raise ValueError(
                "task specifies unrecognized main_window_name: "
                + str(task_params['main_window_name'])
                )
        
        # Instantiate
        win = win_obj(
            box_params=box_params, 
            task_params=task_params, 
            mouse_params=mouse_params, 
            sandbox_path=sandbox_path,
            )

        # Show it
        # This line is not blocking (although it might block Qt event loop)
        # https://forum.qt.io/topic/128580/why-is-widget-show-blocked-if-placing-long-running-code-right-after-it/2
        win.show()
        
        # This line sets the event-loop and blocks until the window is closed
        retcode = app.exec()
        logger.info(f'app.exec completed with retcode {retcode}')

    finally:
        pass
    
    # Wait a few seconds for any errors to be visible
    time.sleep(2)
    
    # Now exit with retcode
    sys.exit(retcode)

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
