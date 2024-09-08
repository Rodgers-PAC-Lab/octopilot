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

"""
## Define a Worker who will execute the Dispatcher.main_loop in its own thread
# https://realpython.com/python-pyqt-qthread/

class Worker(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(int)

    def __init__(self, box_params, task_params, mouse_params):
        super(Worker, self).__init__()
        self.dispatcher = controllers.Dispatcher(box_params, task_params, mouse_params)

    def run(self):
        self.dispatcher.main_loop()
        self.finished.emit()


## Define a Window that will run the GUI and instantiate the Worker
# https://realpython.com/python-pyqt-qthread/

class Window(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.clicksCount = 0
        self.setupUi()

    def setupUi(self):
        self.setWindowTitle("Freezing GUI")
        self.resize(300, 150)
        self.centralWidget = QWidget()
        self.setCentralWidget(self.centralWidget)


        self.worker = Worker(box_params, task_params, mouse_params)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        
        # Step 5: Connect signals and slots
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.progress.connect(self.reportProgress)

        self.thread.start()

    def reportProgress(self, n):
        print(n)
"""

## Start
if __name__ == '__main__':
    # Apparently QApplication needs sys.argv for some reason
    # https://stackoverflow.com/questions/27940378/why-do-i-need-sys-argv-to-start-a-qapplication-in-pyqt
    app = QApplication([])#sys.argv)
    
    # Instantiate a MainWindow
    win = main_window.MainWindow(box_params, task_params, mouse_params)
    win.show()
    sys.exit(app.exec())    
