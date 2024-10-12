## Main script that runs the main launcher app on the desktop
# Run this script as follows:
#   python3 -m paclab_sukrith.gui.start_launcher


## Module imports
from ..shared import load_params

# This defines standard QApplication
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout
from PyQt5.QtCore import QObject, pyqtSignal, QThread

# For getting info from the command line
import threading
import argparse
import sys
import signal
import glob
import os
import pandas


## Use argparse to identify the box, mouse, and task
parser = argparse.ArgumentParser(
    description="Launch octopilot")

# Parse the args
args = parser.parse_args()


## Load all the mice
all_mouse_json = sorted(glob.glob(
    os.path.expanduser('~/dev/octopilot/config/mouse/*.json')))

# Load params from each
records_l = []
for mouse_json in all_mouse_json:
    # Get mouse name from filename
    mouse_name = os.path.split(mouse_json)[1].replace('.json', '')
    
    # Load params from that mouse
    mouse_params = load_params.load_mouse_params(mouse_name)
    
    # Extract necessary params
    try:
        box = mouse_params['box']
        task = mouse_params['task']
    except KeyError:
        raise IOError(f'params file for {mouse_name} is missing a key')
    
    # Store
    records_l.append((mouse_name, box, task))

# DataFrame
mouse_records = pandas.DataFrame.from_records(
    records_l, 
    columns=['mouse', 'box', 'task']).set_index('mouse')
print(mouse_records)

## Create the main window
class LauncherWindow(QWidget):
    def __init__(self, mouse_records):
        super().__init__()
        self.setWindowTitle('Octopilot Launcher')
        
        self.table_widget = QTableWidget()
        self.table_widget.setRowCount(1 + len(mouse_records))
        self.table_widget.setColumnCount(4)
        self.table_widget.setItem(0, 0, QTableWidgetItem('Mouse'))
        self.table_widget.setItem(0, 1, QTableWidgetItem('Box'))
        self.table_widget.setItem(0, 2, QTableWidgetItem('Task'))
        self.table_widget.setItem(0, 3, QTableWidgetItem('Start'))

        # Put each
        for n_mouse, mouse in enumerate(mouse_records.index):
            n_row = n_mouse + 1
            self.table_widget.setItem(n_row, 0, QTableWidgetItem(mouse))
            self.table_widget.setItem(n_row, 1, QTableWidgetItem(mouse_records.loc[mouse, 'box']))
            self.table_widget.setItem(n_row, 2, QTableWidgetItem(mouse_records.loc[mouse, 'task']))
            self.table_widget.setItem(n_row, 3, QTableWidgetItem('Start'))

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.table_widget)
        self.setLayout(self.layout)

## Start
if __name__ == '__main__':
    # Apparently QApplication needs sys.argv for some reason
    # https://stackoverflow.com/questions/27940378/why-do-i-need-sys-argv-to-start-a-qapplication-in-pyqt
    app = QApplication(sys.argv)
    
    # Make CTRL+C work to close the GUI
    # https://stackoverflow.com/questions/4938723/what-is-the-correct-way-to-make-my-pyqt-application-quit-when-killed-from-the-co
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Instantiate a MainWindow
    win = LauncherWindow(mouse_records)
    win.show()
    sys.exit(app.exec())    
