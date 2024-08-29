"""Define the MainWindow of the GUI"""
import sys
import zmq
import numpy as np
import time
import os
import json

# From this module
from . import plotting
from . import config_dialog

# Qt imports
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QAction, QWidget, QVBoxLayout, QHBoxLayout


## TODO: find a way to not hardcode this
GIT_PATH = '/home/mouse/dev/paclab_sukrith'


## MAIN GUI WINDOW
class MainWindow(QtWidgets.QMainWindow):
    """Main window of the GUI that arranges all the widgets.
    
    Here we make objects of all the different elements of the GUI and arrange 
    the widgets. We also connect the signals defined earlier to slots defined 
    in other classes to make them be able to share information.

    Functions of the signals used in the Main Window:
    -------------------------------------------------
    pokedportsignal - Defined in Worker
    This is a signal that is emitted whenever a poke is 
    completed. The port id at which the poke occured is sent to be plotted. 
    This signal is connected to handle_update_signal in the plotting
    widget. This method takes the id of the port that has been poked and 
    appends the timestamp at which the message was received to the list used
    for plotting. The update_plot function is then called to plot an item at
    the particular port id (y-axis) at the timestamp it was received (x-axis)
    
    updateSignal - Defined in ArenaWidget
    This signal is sent from the arena_widget to plot_widget 
    the color of the item that needs to be plotted based on the oucome of the poke.
    This signal contains the port id at which the poke happened and the outcome 
    of the pokein the form of the color associated with that outcome (red - 
    any non-reward poke, blue - completed trial, green - rewarded poke).
    The item will be plotted according to the timestamp and id sent by
    pokedportsignal
    
    startButtonClicked - Defined in ArenaWidget
    This signal is emitted whenver the start button is 
    pressed in arena_widget. This connected to config list to display a warning
    if there is no config selected before starting the session 
    
    Methods
    -------
    __init__ : Initalizes
    
    load_params : Helper function to load the gui config JSON
    
    plot_poked_port : Not sure this is being used anymore
    
    closeEvent : Called on close, and tells each worker to exit
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
            * ArenaWidget - in the middle, displays each port as a circle and
            arranges them with respect to each other
            * ConfigurationList - on the left, allows choosing task params
            * PokePlotWidget - on the right, shows progress over time
        * Add a menu bar with one entry: File > Load Config Directory
            * Connect that entry to self.config_list.load_configurations
        * Create containers for each widget and lay them out
        * Connect signals
            * arena_widget.worker.pokedportsignal to poke_plot_widget.handle_update_signal
            * widget.updateSignal to poke_plot_widget.handle_update_signal
            * arena_widget.startButtonClicked to config_list.on_start_button_clicked
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
        # Instantiate a ArenaWidget to show the ports
        self.arena_widget = plotting.ArenaWidget(self, self.params)
        
        # Instatiate a ConfigurationList to choose the task
        self.config_list = config_dialog.ConfigurationList(self.params)

        # Initializing PokePlotWidget to show the pokes
        # Note that it uses information from arena_widget
        self.poke_plot_widget = plotting.PokePlotWidget(self.arena_widget)


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
        arena_widget_container = QWidget()
        
        # Set the widths of the containers
        config_list_container.setFixedWidth(250)  
        arena_widget_container.setFixedWidth(500)  
        
        # Set each one to have a vertical layout
        config_list_container.setLayout(QVBoxLayout())
        arena_widget_container.setLayout(QVBoxLayout())
        
        # Add each widget to its container
        config_list_container.layout().addWidget(self.config_list)
        arena_widget_container.layout().addWidget(self.arena_widget)


        ## Create a layout for all containers
        """
        container_widget is the container for the main window which arranges the
        previously defined widgets horizontally with respect to each other. You 
        can arrange the widgets in the order you want them to be displayed and 
        set the dimensions for the window that contains them
        """
        container_widget = QWidget(self)
        
        # Horizontal layout because it will contain three things side by side
        container_layout = QtWidgets.QHBoxLayout(container_widget)
        
        # Add config_list_container, arena_widget_container, and poke_plot_widget
        """
        poke_plot_widget is handled separately because we are not creating a container
        for it. This means that its width and height will both change when resizing
        the main window. it does not have a fixed width like the other widgets
        """
        container_layout.addWidget(config_list_container)
        container_layout.addWidget(arena_widget_container)
        container_layout.addWidget(self.poke_plot_widget)
        
        # Set this one as the central widget
        self.setCentralWidget(container_widget)

        
        ## Set the size and title of the main window
        # Title
        self.setWindowTitle(f"GUI - {json_filename}")
        
        # Size in pixels (can be used to modify the size of window)
        self.resize(2000, 270)
        
        # Show it
        self.show()

        
        ## Connecting signals to the respective slots/methods 
        # Wait till after the MainWindow is fully initialized

        # Connect the pokedportsignal to handle_update_signal
        #~ self.arena_widget.worker.pokedportsignal.connect(
            #~ self.poke_plot_widget.handle_update_signal)
        
        # Connect the arena_widget updateSignal to the handle_update_signal
        self.arena_widget.updateSignal.connect(
            self.poke_plot_widget.handle_update_signal)
        
        # Connect the startButtonClicked signal to 
        # config_list.on_start_button_clicked
        self.arena_widget.startButtonClicked.connect(
            self.config_list.on_start_button_clicked)

    def load_params(self, json_filename):
        """Loads params from `json_filename` and returns"""
        # Constructing the full path to the config file
        param_directory = f"{GIT_PATH}/gui/configs/{json_filename}.json"

        # Load the parameters from the specified JSON file
        try:
            with open(param_directory, "r") as p:
                params = json.load(p)
        except json.decoder.JSONDecodeError as e:
            raise ValueError(
                f"unable to load json file at {param_directory}; " +
                f"original exception: {e}"
                )
        
        return params

    # Sukrith: is this actually used for anything?
    def plot_poked_port(self, poked_port_value):
        """Function to plot the Pi signals using the PokePlotWidget class"""
        self.poke_plot_widget.handle_update_signal(poked_port_value)

    def closeEvent(self, event):
        """Executes when the window is closed
        
        Send 'exit' signal to all IP addresses bound to the GUI
        """
        # Iterate through identities and send 'exit' message
        for identity in self.arena_widget.worker.identities:
            self.arena_widget.worker.zmq_socket.send_multipart([identity, b"exit"])
        event.accept()