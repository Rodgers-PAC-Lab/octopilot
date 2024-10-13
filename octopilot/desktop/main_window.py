"""Define the MainWindow of the GUI

This file shoud be used to lay out the connections between the Dispatcher
and the various plotting widgets, by instantiating them and by laying out
the way they are started and updated by threads and timers.

The MainWindow
* Instantiates and contains the Dispatcher to control the task
* Instantiates each of the individual plotting widgets and lays them out
* Starts QTimer to update the Dispatcher
* Instantiates a start button which will be connected to the start method
  of each individual widget

The plotting widgets are defined in plotting.py. They get the data they
need directly from the Dispatcher.
"""

import sys
import zmq
import numpy as np
import time
import os
import json

# Qt imports
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QAction, QWidget, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget
from PyQt5.QtCore import QObject, pyqtSignal, QThread, QTimer

# From this module
from . import plotting
from . import controllers


class MainWindow(QtWidgets.QMainWindow):
    """Main window of the GUI that arranges all the widgets.
    
    Here we make objects of all the different elements of the GUI and arrange 
    the widgets. We also connect the signals defined earlier to slots defined 
    in other classes to make them be able to share information.

    
    Methods
    -------
    __init__ : Initalizes
    closeEvent : Called on close, and tells each worker to exit
    """
    def __init__(self, box_params, task_params, mouse_params):
        """Initialize a new MainWindow
        
        """
        ## Superclass QMainWindow init
        super().__init__()
        
        
        ## Create the Dispatcher that will run the task
        self.dispatcher = controllers.Dispatcher(
            box_params, task_params, mouse_params)

        
        ## Create a timer to update the Dispatcher
        self.timer_dispatcher = QTimer(self)
        
        # Any error that happens in dispatcher.update will just crash the
        # timer thread, not the main thread
        # TODO: figure out how to capture those errors
        self.timer_dispatcher.timeout.connect(self.dispatcher.update)


        ## Set up the graphical objects
        # Instantiate a ArenaWidget to show the ports
        self.arena_widget = plotting.ArenaWidget(self.dispatcher)
        
        # Initializing PokePlotWidget to show the pokes
        self.poke_plot_widget = plotting.PokePlotWidget(self.dispatcher)


        ## Creating container widgets for each component 
        # These containers determine size and arrangment of widgets
        arena_widget_container = QWidget()
        arena_widget_container.setFixedWidth(200)  
        arena_widget_container.setLayout(QVBoxLayout())
        arena_widget_container.layout().addWidget(self.arena_widget)

        # Create self.start_button and connect it to self.start_sequence
        self.set_up_start_button()
        
        # Create self.start_button and connect it to self.stop_sqeuence
        # and to self.save_results_to_csv
        self.set_up_stop_button()
        
        # Creating vertical layout for start and stop buttons
        start_stop_layout = QVBoxLayout()
        start_stop_layout.addWidget(self.start_button)
        start_stop_layout.addWidget(self.stop_button)        


        ## Create a layout for all containers
        container_widget = QWidget(self)
        
        # Horizontal layout because it will contain three things side by side
        container_layout = QtWidgets.QHBoxLayout(container_widget)
        
        # Add config_list_container, arena_widget_container, and poke_plot_widget
        # poke_plot_widget is handled separately because we are not creating a container
        # for it. This means that its width and height will both change when resizing
        # the main window. it does not have a fixed width like the other widgets
        container_layout.addWidget(arena_widget_container)
        container_layout.addWidget(self.poke_plot_widget)
        container_layout.addLayout(start_stop_layout)
        
        # Set this one as the central widget
        self.setCentralWidget(container_widget)

        
        ## Set the size and title of the main window
        # Size in pixels (can be used to modify the size of window)
        self.resize(1200, 200)
        self.move(700, box_params['ypos_of_gui'])
        
        # Show it
        self.show()

        
        ## Connecting signals to the respective slots/methods 
        # Wait till after the MainWindow is fully initialized
        self.timer_dispatcher.start(50)

    def set_up_start_button(self):
        """Create a start button and connect to self.start_sequence"""
        # Create button
        self.start_button = QPushButton("Start Session")
        
        # Set style
        self.start_button.setStyleSheet(
            "background-color : green; color: white;") 

        # Start the dispatcher and the updates
        # TODO: Handle the case where the dispatcher doesn't actually start
        # because it's not ready
        self.start_button.clicked.connect(self.dispatcher.start_session)
        self.start_button.clicked.connect(self.poke_plot_widget.start_plot)
        self.start_button.clicked.connect(self.arena_widget.start)

    def set_up_stop_button(self):
        """Create a start button and connect to self.start_sequence"""
        # Create button
        self.stop_button = QPushButton("Stop Session")
        
        # Set style
        self.start_button.setStyleSheet(
            "background-color : green; color: white;") 
        
        # Stop the dispatcher and the updates
        self.stop_button.clicked.connect(self.dispatcher.stop_session)
        self.stop_button.clicked.connect(self.poke_plot_widget.stop_plot)

    def closeEvent(self, event):
        """Executes when the window is closed
        
        Send 'exit' signal to all IP addresses bound to the GUI
        """
        # Iterate through identities and send 'exit' message
        self.timer_dispatcher.stop()
        self.dispatcher.stop_session()
        event.accept()