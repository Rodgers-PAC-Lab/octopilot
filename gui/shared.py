import sys
import zmq
import numpy as np
import time
import os
import math
import pyqtgraph as pg
import random
import csv
import json
import argparse
from datetime import datetime
import plotting
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import (
    QMenu, QAction, QComboBox, QGroupBox, QMessageBox, QLabel, 
    QGraphicsEllipseItem, QListWidget, QListWidgetItem, QGraphicsTextItem, 
    QGraphicsScene, QGraphicsView, QWidget, QVBoxLayout, QPushButton, 
    QApplication, QHBoxLayout, QLineEdit, QListWidget, QFileDialog, 
    QDialog, QLabel, QDialogButtonBox, QTreeWidget, QTreeWidgetItem,
    )
from PyQt5.QtCore import (
    QPointF, QTimer, QTime, pyqtSignal, QObject, QThread, pyqtSlot, 
    QMetaObject, Qt,
    )
from PyQt5.QtGui import QFont, QColor
from pyqttoast import Toast, ToastPreset


## TODO: find a way to not hardcode this
GIT_PATH = '/home/mouse/dev/paclab_sukrith'


## MAIN GUI WINDOW
class MainWindow(QtWidgets.QMainWindow):
    """Main window of the GUI that arranges all the widgets.
    
    Here we make objects of all the different elements of the GUI and arrange 
    the widgets. We also connect the signals defined earlier to slots defined 
    in other classes to make them be able to share information.
    """
    def __init__(self, json_filename):
        """Initialize a new MainWindow
        
        Arguments
        ---------
        json_filename : name of params file for this box
        
        
        Order of events
        ---------------
        * Load the parameters file.
        * Instantiate the following widgets:
            * PiWidget - in the middle, displays each port as a circle
            * ConfigurationList - on the left, allows choosing task params
            * PlotWindow - on the right, shows progress over time
        * Add a menu bar with one entry: File > Load Config Directory
            * Connect that entry to self.config_list.load_configurations
        * Create containers for each widget and lay them out
        * Connect signals
            * Pi_widget.worker.pokedportsignal to plot_window.handle_update_signal
            * widget.updateSignal to plot_window.handle_update_signal
            * Pi_widget.startButtonClicked to config_list.on_start_button_clicked
        """
        ## Superclass QMainWindow init
        super().__init__()
        
        
        ## Load params
        self.params = self.load_params(json_filename)


        #~ ## TODO: move this
        #~ # Fetching all the ports to use for the trials 
        #~ # (This was implemented becuase I had to test on less than 8 nosepokes)    
        #~ active_nosepokes = [int(i) for i in params['active_nosepokes']]

        #~ # Variable to store the name of the current task and the timestamp at 
        #~ # which the session was started (mainly used for saving)
        #~ current_task = None
        #~ current_time = None

        
        ## Set up the graphical objects
        # Instantiate a PiWidget to show the ports
        self.Pi_widget = plotting.PiWidget(self, self.params)
        
        # Instatiate a ConfigurationList to choose the task
        self.config_list = plotting.ConfigurationList(self.params)

        # Initializing PlotWindow to show the pokes
        # Note that it uses information from Pi_widget
        self.plot_window = plotting.PlotWindow(self.Pi_widget)


        ## Set up the actions for the menu bar
        # Creating a menu bar with some actions
        menubar = self.menuBar()
        file_menu = menubar.addMenu('File')

        # Creating an action to change directory to load mice from 
        load_action = QAction('Load Config Directory', self)
        load_action.triggered.connect(self.config_list.load_configurations)

        # Adding that action to the file menu
        file_menu.addAction(load_action)

        
        ## Creating container widgets for each component 
        # These containers determine size and arrangment of widgets
        
        # Container for each widget
        config_list_container = QWidget()
        pi_widget_container = QWidget()
        
        # Set the widths of the containers
        config_list_container.setFixedWidth(250)  
        pi_widget_container.setFixedWidth(500)  
        
        # Set each one to have a vertical layout
        config_list_container.setLayout(QVBoxLayout())
        pi_widget_container.setLayout(QVBoxLayout())
        
        # Add each widget to its container
        config_list_container.layout().addWidget(self.config_list)
        pi_widget_container.layout().addWidget(self.Pi_widget)


        ## Create a layout for all containers
        # Create a container for the whole thing (?)
        # Sukrith: why is "container_widget" initialized differently?
        container_widget = QWidget(self)
        
        # Horizontal layout because it will contain three things side by side
        container_layout = QtWidgets.QHBoxLayout(container_widget)
        
        # Add config_list_container, pi_widget_container, and plot_window
        # Why is plot_window handled differently
        container_layout.addWidget(config_list_container)
        container_layout.addWidget(pi_widget_container)
        container_layout.addWidget(self.plot_window)
        
        # Set this one as the central widget
        self.setCentralWidget(container_widget)

        
        ## Set the size and title of the main window
        # Title
        self.setWindowTitle(f"GUI - {json_filename}")
        
        # Size in pixels
        self.resize(2000, 270)
        
        # Show it
        self.show()

        
        ## Connecting signals to the respective slots/methods 
        # Wait till after the MainWindow is fully initialized
        # Sukrith: document these signals. What generates them? What happens
        # as a result?
        
        # Connect the pokedportsignal to handle_update_signal
        self.Pi_widget.worker.pokedportsignal.connect(
            self.plot_window.handle_update_signal)
        
        # Connect the pi_widget updateSignal to the handle_update_signal
        self.Pi_widget.updateSignal.connect(
            self.plot_window.handle_update_signal)
        
        # Connect the startButtonClicked signal to 
        # config_list.on_start_button_clicked
        self.Pi_widget.startButtonClicked.connect(
            self.config_list.on_start_button_clicked)

    def load_params(self, json_filename):
        """Loads params from `json_filename` and returns"""
        # Constructing the full path to the config file
        param_directory = f"{GIT_PATH}/gui/configs/{json_filename}.json"

        # Load the parameters from the specified JSON file
        with open(param_directory, "r") as p:
            params = json.load(p)
        
        return params

    # Sukrith: is this actually used for anything?
    def plot_poked_port(self, poked_port_value):
        """Function to plot the Pi signals using the PlotWindow class"""
        self.plot_window.handle_update_signal(poked_port_value)

    def closeEvent(self, event):
        """Executes when the window is closed
        
        Send 'exit' signal to all IP addresses bound to the GUI
        """
        # Iterate through identities and send 'exit' message
        for identity in self.Pi_widget.worker.identities:
            self.Pi_widget.worker.socket.send_multipart([identity, b"exit"])
        event.accept()