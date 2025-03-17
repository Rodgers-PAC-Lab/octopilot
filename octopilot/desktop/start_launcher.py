## Main script that runs the main launcher app on the desktop
# Run this script as follows:
#   python3 -m paclab_sukrith.gui.start_launcher


## Module imports
from ..shared import load_params

# This defines standard QApplication
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QPushButton
from PyQt5 import QtCore, QtGui
import PyQt5.QtWidgets

import functools
import datetime
import argparse
import sys
import signal
import subprocess
import glob
import os
import pandas

# Helper function
def start_octopilot_gui_in_new_terminal(
    mouse, box, task, zoom=0.5, ncols=80, nrows=15, 
    xpos=350, ypos=200, keep_window_open=False):
    """Open a terminal and start an octopilot GUI session in it.
    
    We want to run the octopilot GUI session in its own subprocess so that 
    the Launcher will keep running even if that session crashes. We also
    want to be able to see the debug messages in the terminal. So we
    open a subprocess that runs a bash command to start the Octopilot session.
    
    Arguments
    ---------
    mouse, box, task : str
        These are passed as argparse kwargs to octopilot start_gui like this:
        python3 -m octopilot.desktop.start_gui {box} {mouse} {task}
    
    zoom, ncols, nrows, xpos, ypos : numeric
        These are used to set up how the gnome-terminal window appears
    
    Returns: the result of subprocess.Popen
    """
    ## Create a sandbox
    # Set the session name
    sandbox_creation_time = datetime.datetime.now()
    sandbox_name = (
        sandbox_creation_time.strftime('%Y-%m-%d_%H-%M-%S') 
        + '_' + mouse)

    # Create a path to store data
    # This is the high-level save directory, then the year, then the month,
    # and finally the sandbox_name
    save_path_l = [
        os.path.expanduser('/home/mouse/octopilot/logs'), 
        str(sandbox_creation_time.year),
        '{:02d}'.format(sandbox_creation_time.month),
        sandbox_name,
        ]
    
    # Create each of the above directories in order
    partial_path = None
    for path_part in save_path_l:
        # Gradually grow partial_path
        if partial_path is None:
            partial_path = path_part
        else:
            partial_path = os.path.join(partial_path, path_part)
        
        # Create if needed
        if not os.path.exists(partial_path):
            os.mkdir(partial_path)
    
    # Error check
    sandbox_path = os.path.join(*save_path_l)
    assert partial_path == sandbox_path
    
    
    ## Call the script
    # This is the python3 command used to start the octopilot session
    bash_command = (
        f'python3 -m octopilot.desktop.start_gui {box} {mouse} {task}')
    
    # Append a tee
    bash_command += f' |& tee -a logfile'

    # Optionally add a 'read' command afterward to keep the window open
    if keep_window_open:
        bash_command += '; read'    

    # Form the full list of Popen args, which are used to start the
    # gnome-terminal window and then run the bash_command inside it
    # Note: bash_command should NOT be enclosed in quotes here, because that
    # is magically handled by Popen, even though it would need to be enclosed
    # in quotes if we were typing this from the command line
    popen_args = [
        'gnome-terminal', 
        f'--working-directory={sandbox_path}',
        '--hide-menubar',
        '--geometry=%dx%d+%d+%d' % (ncols, nrows, xpos, ypos),
        '--zoom=%0.2f' % zoom,  
        '--', # used to be -x
        'bash', '-l', '-c',
        bash_command,
        ]
    
    # Print
    print(popen_args)
    
    # Popen
    # TODO: keep track of this process in Launcher
    proc = subprocess.Popen(popen_args)
    
    return proc

## Use argparse to identify the box, mouse, and task
parser = argparse.ArgumentParser(
    description="Launch octopilot")

# Optional debug
parser.add_argument('--debug', action=argparse.BooleanOptionalAction)

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
        # Super init for QWidget
        super().__init__()
        
        # Keep track of launched processes
        self.proc_l = []
        
        # Set window title
        self.setWindowTitle('Octopilot Launcher')
        
        # Create a table
        self.table_widget = QTableWidget()
        self.table_widget.setRowCount(1 + len(mouse_records))
        self.table_widget.setColumnCount(4)
        self.table_widget.setItem(0, 0, QTableWidgetItem('Mouse'))
        self.table_widget.setItem(0, 1, QTableWidgetItem('Box'))
        self.table_widget.setItem(0, 2, QTableWidgetItem('Task'))
        self.table_widget.setItem(0, 3, QTableWidgetItem('Start'))

        # Set row widths
        self.table_widget.horizontalHeader().resizeSection(0, 120)
        self.table_widget.horizontalHeader().resizeSection(1, 60)
        self.table_widget.horizontalHeader().resizeSection(2, 80)
        self.table_widget.horizontalHeader().resizeSection(3, 40)

        # Set font size
        font = QtGui.QFont()
        font.setPointSize(8)        
        self.table_widget.setFont(font)

        # Put data for each mouse in a row
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
            # Connect this to start_session_from_qb, using `qb` as an argument
            qb = QPushButton('Start')
            qb.clicked.connect(
                functools.partial(self.start_session_from_qb, qb))
            self.table_widget.setCellWidget(n_row, 3, qb)

        # Create a checkbox for debug mode
        self.debug_check_box_label = PyQt5.QtWidgets.QLabel(self)
        self.debug_check_box_label.setText('debug mode')
        self.debug_check_box = PyQt5.QtWidgets.QCheckBox(self)
        self.debug_check_box_layout = PyQt5.QtWidgets.QHBoxLayout()
        self.debug_check_box_layout.addWidget(self.debug_check_box_label)
        self.debug_check_box_layout.addWidget(self.debug_check_box)

        # Initialize state of checkbox
        if args.debug:
            self.debug_check_box.setChecked(True)

        # Create a layout and add items to it
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.table_widget)
        self.layout.addLayout(self.debug_check_box_layout)
        
        # Set the layout
        self.setLayout(self.layout)
        
        # Position in the upper left corner
        self.resize(400, 1000)
        self.move(0, 0)
    
    def start_session_from_row_idx(self, n_row):
        """Use data from row in self.table_widget to start octopilot session
        
        n_row : int
            The index of the row within self.table_widget corresponding
            to the session to start
        """
        # Highlight clicked cell
        self.table_widget.setCurrentCell(n_row, 3)
        
        # Extract data from row
        mouse = str(self.table_widget.item(n_row, 0).text())
        box = str(self.table_widget.item(n_row, 1).text())
        task = str(self.table_widget.item(n_row, 2).text())

        # Load the box params to find out where to put the GUI elements
        box_params = load_params.load_box_params(box)
        ypos = box_params['ypos_of_gui']
        
        # Get state of debug check box
        debug = self.debug_check_box.isChecked()
        
        # Call start_octopilot_gui_in_new_terminal with that data
        proc = start_octopilot_gui_in_new_terminal(
            mouse=mouse,
            box=box,
            task=task,
            ypos=ypos,
            keep_window_open=debug,
        )
        
        # Store
        self.proc_l.append(proc)

    def start_session_from_qb(self, row_qb):
        """Start the session associated with the push button for this row.
        
        This is connected to pushbutton click. The reason to pass the
        pushbutton itself, instead of the row index, is in case the 
        rows get rearranged (which is not currently possible, but should be).
        
        row_qb : QPushButton that was clicked
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
        self.start_session_from_row_idx(session_row)

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
