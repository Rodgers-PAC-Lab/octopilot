## Main script that runs the main launcher app on the desktop
# Run this script as follows:
#   python3 -m paclab_sukrith.gui.start_launcher


## Module imports
from ..shared import load_params

# This defines standard QApplication
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QPushButton
from PyQt5.QtCore import QObject, pyqtSignal, QThread
from PyQt5 import QtCore

# For getting info from the command line
import functools
import threading
import argparse
import sys
import signal
import glob
import os
import pandas


def call_external(mouse, box, task, **other_python_parameters):
    print(mouse, box, task)
    #~ ArduFSM.Runner.start_runner_cli.main(mouse=mouse, board=board, box=box,
        #~ experimenter=experimenter,
        #~ **other_python_parameters)


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
            
            # The mouse name
            item = QTableWidgetItem(mouse)
            item.setFlags(item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.table_widget.setItem(n_row, 0, item)
            
            # The box name
            item = QTableWidgetItem(mouse_records.loc[mouse, 'box'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.table_widget.setItem(n_row, 1, item )
            
            # The task name
            item = QTableWidgetItem(mouse_records.loc[mouse, 'task'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.table_widget.setItem(n_row, 2, item )
            
            # The start button
            qb = QPushButton('Start')
            qb.clicked.connect(functools.partial(self.start_session2, qb))
            self.table_widget.setCellWidget(n_row, 3, qb)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.table_widget)
        self.setLayout(self.layout)

    def start_session(self, row):
        """Collect data from row and pass to start session"""
        # Highlight clicked cell
        self.table_widget.setCurrentCell(row, 3)
        
        # Extract data from row
        mouse = str(self.table_widget.item(row, 0).text())
        box = str(self.table_widget.item(row, 1).text())
        task = str(self.table_widget.item(row, 2).text())
        
        # Call
        call_external(
            mouse=mouse,
            box=box,
            task=task,
            background_color=None,
        )

    def start_session2(self, row_qb):
        """Start the session associated with the push button for this row.
        
        """
        # Find which row the push button is in
        session_row = -1
        for nrow in range(self.table_widget.rowCount()):
            if self.table_widget.cellWidget(nrow, 3) is row_qb:
                session_row = nrow
                break
        if session_row == -1:
            raise ValueError("cannot find row for pushbutton")
        
        # Extract the mouse, board, box from this row
        self.start_session(session_row)
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
