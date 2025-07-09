"""Module for the individual plot widgets

Each individual widget should be initialized with the Dispatcher, 
and get the data it needs by reading the attributes of the Dispatcher.
"""

import math
import datetime
import time
import csv
import random
import numpy as np
import zmq
import pyqtgraph as pg


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


# ArenaWidget Class that represents all ports
class ArenaWidget(QWidget):
    """Displays a colored circle for each nosepoke indicating its status."""
    def __init__(self, dispatcher, *args, **kwargs):
        """Initialize an ArenaWidget
        
        dispatcher : controllers.Dispatcher
            Gets data from here
        """
        # Superclass QWidget init
        super(ArenaWidget, self).__init__(*args, **kwargs)
        
        # Store the dispatcher
        self.dispatcher = dispatcher

        # Add individual ports to the widget
        self.create_layout(
            self.dispatcher.port_names,
            self.dispatcher.port_positions,
            )
        
        # Create a timer and connect to self.update_time_elapsed
        self.timer_update = QTimer(self)
        self.timer_update.timeout.connect(self.update) 

    def create_layout(self, port_names, port_positions, circle_size=25):
        """Place `port_names` at `port_positions`.
        
        port_names : list of str
        port_positions : list of numeric
            Each is the angular position in degrees, with 0 meaning north.
        """
        # Create QGraphics
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        
        # Create each
        self.nosepoke_circles = []
        iter_obj = enumerate(zip(port_names, port_positions))
        for port_idx, (port_name, port_position) in iter_obj:
            # Create an ellipse
            ellipse = QGraphicsEllipseItem(0, 0, circle_size, circle_size) 
            
            # Setting the label for each port on the GUI
            label = QGraphicsTextItem(port_name, ellipse)
            font = QFont()
            font.setPointSize(8)  
            label.setFont(font)
        
            # Positioning the labels within the ellipse
            label.setPos(
                circle_size / 2 - label.boundingRect().width() / 2, 
                circle_size / 2 - label.boundingRect().height() / 2,
                )
        
            # Positioning the individual ports
            ellipse.setPos(self.calculate_position(port_position))
        
            # Setting the initial color of the ports to gray
            ellipse.setBrush(QColor("gray")) 

            # Add it to the scene
            self.scene.addItem(ellipse)
            
            # Save
            self.nosepoke_circles.append(ellipse)

        # Arranging the previous layout horizontally with the session details
        main_layout = QHBoxLayout(self)
        main_layout.addWidget(self.view)  
        self.setLayout(main_layout)

    def calculate_position(self, port_position, radius=50):  
        """Return QPointF corresponding to `port_position`
        
        port_position : numeric
            Angle of the port, in degrees
        """
        # Subtracting 90 makes 0 north, although I'm not really sure why
        # Is QPointF from the upper left or lower left?
        angle = (port_position - 90) * math.pi / 180
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        
        # Arranging the Pi signals in a circle based on x and y coordinates 
        # calculated using the radius
        # This seems to be auto-centered, so the actual values don't have
        # to be positive or anything
        return QPointF(x, y)

    def start(self):
        # Start the timer
        # The faster this is, the more responsive it will be, but when an 
        # error occurs it will spam the terminal
        self.timer_update.start(250)
    
    def update(self):
        """Update the colors of the circles"""
        for port_idx, port_name in enumerate(self.dispatcher.port_names):
            # Get circle
            nosepoke_circle = self.nosepoke_circles[port_idx]
            
            # Identify if poked
            if port_name == self.dispatcher.previously_rewarded_port:
                # It's the PRP, paint it white
                nosepoke_circle.setBrush(QColor("white"))
            
            elif port_name in self.dispatcher.ports_poked_this_trial:
                # It's been poked in this trial
                if port_name == self.dispatcher.goal_port:
                    # It was the rewarded port, make it blue
                    nosepoke_circle.setBrush(QColor("blue"))
                
                else:
                    # It was not rewarded, make it red
                    nosepoke_circle.setBrush(QColor("red"))
            
            elif port_name == self.dispatcher.goal_port:
                # It's the goal, make it green
                nosepoke_circle.setBrush(QColor("green"))
            
            else:
                # Nothing has happened, leave it gray
                nosepoke_circle.setBrush(QColor("gray"))

## Widget to display text performance metrics
class PerformanceMetricDisplay(QWidget):
    def __init__(self, dispatcher):
        """Create a PerformanceMetricDisplay
        
        dispatcher : controllers.Dispatcher
            Get data from here
        """
        # Superclass QWidget init
        super(PerformanceMetricDisplay, self).__init__()
        
        # Store the dispatcher
        self.dispatcher = dispatcher
        
        # Create QVBoxLayout for session details 
        self.details_layout = QVBoxLayout()

        # Making labels that constantly update according to the session details
        self.time_label = QLabel("", self)#Time Elapsed: 00:00", self)
        self.poke_time_label = QLabel("Time since last poke: 00:00", self)
        self.poke_count = QLabel("Number of Pokes: 0", self)
        self.trial_count = QLabel("Number of Trials: 0", self)
        self.correct_count = QLabel("Number of Correct Trials: 0", self)
        self.fraction_correct = QLabel("Fraction Correct (FC): 0.000", self)
        self.rcp = QLabel("Rank of Correct Port (RCP): 0", self)
        
        # Adding these labels to the layout used to contain the session information 
        self.details_layout.addWidget(self.time_label)
        self.details_layout.addWidget(self.poke_time_label)
        self.details_layout.addWidget(self.poke_count)
        self.details_layout.addWidget(self.trial_count)
        self.details_layout.addWidget(self.correct_count)
        self.details_layout.addWidget(self.fraction_correct)
        self.details_layout.addWidget(self.rcp)       
        
        # Init these
        self.update()
        
        # set layout
        self.setLayout(self.details_layout)

        # Create a timer and connect to self.update_time_elapsed
        self.timer_update = QTimer(self)
        self.timer_update.timeout.connect(self.update) 

    def start(self):
        # Start the timer
        # The faster this is, the more responsive it will be, but when an 
        # error occurs it will spam the terminal
        self.timer_update.start(250)
    
    def stop(self):
        """Stop updating the elapsed time
        
        Called by main_window.stop_button. 
        """
        self.timer_update.stop()
    
    def update(self):
        ## Get data from dispatcher
        # Number of pokes total
        n_pokes = int(np.sum([
            len(pokes_on_port) 
            for pokes_on_port in 
            self.dispatcher.history_of_pokes.values()
            ]))            
        
        # Number of correct trials (number of rewarded correct pokes)
        n_correct_trials = int(np.sum([
            len(rewards_on_port) 
            for rewards_on_port in 
            self.dispatcher.history_of_rewarded_correct_pokes.values()
            ]))            
        
        # Number of incorrect trials (number of rewarded incorrect pokes)
        n_incorrect_trials = int(np.sum([
            len(rewards_on_port) 
            for rewards_on_port in 
            self.dispatcher.history_of_rewarded_incorrect_pokes.values()
            ]))
        
        # The total number of unique ports poked per trial
        rcp_times_ntrials = int(np.sum(
            self.dispatcher.history_of_ports_poked_per_trial))
        
        # Time since session start
        if self.dispatcher.session_start_time is not None:
            time_from_session_start_sec = (
                datetime.datetime.now() - 
                self.dispatcher.session_start_time).total_seconds()        
        else:
            time_from_session_start_sec = None
        
        # Time since last poke
        if n_pokes > 0:
            last_poke = np.max(np.concatenate(
                list(self.dispatcher.history_of_pokes.values())
                ))
            time_from_last_poke = time_from_session_start_sec - last_poke
        else:
            time_from_last_poke = None
        
        
        ## Calculate performance metrics
        n_trials = n_correct_trials + n_incorrect_trials
        if n_trials > 0:
            fraction_correct = n_correct_trials / float(n_trials)
            rcp = rcp_times_ntrials / float(n_trials)
        
        else:
            # If no trials, these can't be calculated
            fraction_correct = None
            rcp = None
        
        
        ## Update labels
        # Update trial count
        self.trial_count.setText(f"N trials: {n_trials}")
        
        # Update poke count
        self.poke_count.setText(f"N pokes: {(n_pokes)}")
        
        # Updating number of correct trials 
        self.correct_count.setText(
            f"N correct trials: {n_correct_trials}") 

        # Update fraction correct label
        if fraction_correct is not None:
            self.fraction_correct.setText(
                f"fraction correct: {fraction_correct:.2f}")
        else:
            self.fraction_correct.setText(
                f"fraction correct: NA")

        if rcp is not None:
            self.rcp.setText(f"ports poked / trial: {rcp:.2f}")       
        else:
            self.rcp.setText(f"ports poked / trial: NA")
        
        # Update timing
        if time_from_session_start_sec is not None:
            self.time_label.setText(
                "elapsed time: {}".format(
                    self.format_time(int(time_from_session_start_sec))
                )
            )
        else:
            self.time_label.setText(
                'elapsed time: NA')
        
        if time_from_last_poke is not None:
            self.poke_time_label.setText(
                "time since poke: {}".format(
                    self.format_time(int(time_from_last_poke))
                )
            )

        else:
            self.poke_time_label.setText(
                'time since poke: NA')
            
    @staticmethod
    def format_time(seconds):
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        match hours > 0:
            case True:
                return f"{hours:02}:{minutes:02}:{seconds:02}"
            case False:
                return f"{minutes:02}:{seconds:02}"

## Widget to display text performance metrics for SurfaceOrientationTask
class PerformanceMetricDisplay_SOT(QWidget):
    def __init__(self, dispatcher):
        """Create a PerformanceMetricDisplay_SOT
        
        dispatcher : controllers.Dispatcher
            Get data from here
        """
        # Superclass init
        super(PerformanceMetricDisplay_SOT, self).__init__()
        
        # Store the dispatcher
        self.dispatcher = dispatcher
        
        # Create QVBoxLayout for session details 
        self.details_layout = QVBoxLayout()

        # Making labels that constantly update according to the session details
        self.time_label = QLabel("", self)
        self.trial_count = QLabel("Number of Trials: 0", self)
        self.correct_count = QLabel("Number of Correct Trials: 0", self)
        self.fraction_correct = QLabel("Fraction Correct (FC): 0.000", self)
        
        # Adding these labels to the layout used to contain the session information 
        self.details_layout.addWidget(self.time_label)
        self.details_layout.addWidget(self.trial_count)
        self.details_layout.addWidget(self.correct_count)
        self.details_layout.addWidget(self.fraction_correct)
        
        # Init these
        self.update()
        
        # set layout
        self.setLayout(self.details_layout)

        # Create a timer and connect to self.update_time_elapsed
        self.timer_update = QTimer(self)
        self.timer_update.timeout.connect(self.update) 

    def start(self):
        # Start the timer
        # The faster this is, the more responsive it will be, but when an 
        # error occurs it will spam the terminal
        self.timer_update.start(250)
    
    def stop(self):
        """Stop updating the elapsed time
        
        Called by main_window.stop_button. 
        """
        self.timer_update.stop()
    
    def update(self):
        ## Get data from dispatcher
        # Time since session start
        if self.dispatcher.session_start_time is not None:
            time_from_session_start_sec = (
                datetime.datetime.now() - 
                self.dispatcher.session_start_time).total_seconds()        
        else:
            time_from_session_start_sec = None

        # TODO: get actual data here
        n_correct_trials = 0
        n_incorrect_trials = 0

        
        ## Calculate performance metrics
        n_trials = n_correct_trials + n_incorrect_trials
        if n_trials > 0:
            fraction_correct = n_correct_trials / float(n_trials)
        
        else:
            # If no trials, these can't be calculated
            fraction_correct = None
        
        
        ## Update labels
        # Update trial count
        self.trial_count.setText(f"N trials: {n_trials}")
        
        # Updating number of correct trials 
        self.correct_count.setText(
            f"N correct trials: {n_correct_trials}") 

        # Update fraction correct label
        if fraction_correct is not None:
            self.fraction_correct.setText(
                f"fraction correct: {fraction_correct:.2f}")
        else:
            self.fraction_correct.setText(
                f"fraction correct: NA")

        # Update timing
        if time_from_session_start_sec is not None:
            self.time_label.setText(
                "elapsed time: {}".format(
                    self.format_time(int(time_from_session_start_sec))
                )
            )
        else:
            self.time_label.setText(
                'elapsed time: NA')

    @staticmethod
    def format_time(seconds):
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        match hours > 0:
            case True:
                return f"{hours:02}:{minutes:02}:{seconds:02}"
            case False:
                return f"{minutes:02}:{seconds:02}"

## Widget to plot pokes
class PokePlotWidget(QWidget):
    """Widget that plots the pokes as they happen
    
    """
    def __init__(self, dispatcher, *args, **kwargs):
        """Initialize a new PokePlotWidget
        

        """
        ## Superclass QWidget init
        super().__init__(*args, **kwargs)
        
        
        ## Instance variables
        # Dispatcher, where the data comes from
        self.dispatcher = dispatcher
        
        # Timers for continuous updating
        # Create a QTimer object to continuously update the plot         
        self.timer_update_plot = QTimer(self) 
        self.timer_update_plot.timeout.connect(self.update_plot)  
        
        # Creating a QTimer for updating the moving time bar
        self.timer_update_time_bar = QTimer(self)
        self.timer_update_time_bar.timeout.connect(self.update_time_bar) 

        
        ## Initialize the plot_widget which actually does the plotting
        # Initializing the pyqtgraph widget
        self.plot_widget = pg.PlotWidget() 
        
        # Setting the layout of the plotting widget 
        self.layout = QVBoxLayout(self) 
        self.layout.addWidget(self.plot_widget)
        
        # Set labels and colors of `plot_widget`
        self.setup_plot_graphics()
       
        # Plots line_of_current_time and line
        self.initalize_plot_handles()

    def setup_plot_graphics(self):
        """Sets colors and labels of plot_widget
        
        Flow
        * Sets background to black and font to white
        * Sets title and axis labels
        * Adds a grid
        * Sets y-limits to [1, 9]
        """
        # Set x-axis range to [0, 1600] which is more or less the duration of 
        # the task in seconds (can be changed) (might be better to display in 
        # minutes also)
        self.plot_widget.setXRange(0, 1600)  
        
        # Setting the background of the plot to be black. Use 'w' for white
        self.plot_widget.setBackground("k") 
        
        # Setting the font/style for the rest of the text used in the plot
        styles = {"color": "white", "font-size": "11px"} 
        
        # Adding a grid background to make it easier to see where pokes are in time
        self.plot_widget.showGrid(x=True, y=True) 
        
        # Setting the range for the Y axis
        self.plot_widget.setYRange(-0.5, len(self.dispatcher.port_names))
        
        # Set the ticks
        ticks = list(enumerate(self.dispatcher.port_names))
        self.plot_widget.getPlotItem().getAxis('left').setTicks([ticks, []])

    def initalize_plot_handles(self):
        """Plots line_of_current_time and line
        
        Creates these handles:
            self.line_of_current_time : a line that moves with the current time
            self.plot_handle_unrewarded_pokes : a raster plot of unrewarded
                pokes in red
            self.plot_handle_rewarded_incorrect_pokes : a raster plot of 
                rewarded incorrect pokes in blue
            self.plot_handle_rewarded_correct_pokes : a raster plot of 
                rewarded correct pokes in green
        """
        # Plot the sliding timebar
        self.line_of_current_time_color = 0.5
        self.line_of_current_time = self.plot_widget.plot(
            x=[0, 0], y=[-1, 8], pen=pg.mkPen(self.line_of_current_time_color))

        # Unrewarded pokes in red
        self.plot_handle_unrewarded_pokes = self.plot_widget.plot(
            x=[],
            y=[],
            pen=None, # no connecting line
            symbol="arrow_down",  
            symbolSize=10,
            symbolBrush='r',
            symbolPen=None,
        )
    
        # Rewarded incorrect pokes in blue
        self.plot_handle_rewarded_incorrect_pokes = self.plot_widget.plot(
            x=[],
            y=[],
            pen=None, # no connecting line
            symbol="arrow_down",  
            symbolSize=10,
            symbolBrush='c',
            symbolPen=None,
        )
        
        # Rewarded correct pokes in green
        self.plot_handle_rewarded_correct_pokes = self.plot_widget.plot(
            x=[],
            y=[],
            pen=None, # no connecting line
            symbol="arrow_down",  
            symbolSize=10,
            symbolBrush='g',
            symbolPen=None,
        )

    def start_plot(self):
        """Activates plot updates.
        
        Activates `timer` and `time_bar_timer` to update plot.
        Sets `start_time` and `is_active`.
        """
        # Plot updates every 200 ms
        self.timer_update_plot.start(200)  

        # Time bar updates every 50 ms
        self.timer_update_time_bar.start(50)  

    def stop_plot(self):
        """Deactivates plot updates"""
        self.timer_update_plot.stop()
        self.timer_update_time_bar.stop()

    def update_time_bar(self):
        """Controls how the timebar moves according to the timer"""
        # Do nothing if there is no start_time
        if self.dispatcher.session_start_time is not None:
            # Determine elapsed time
            current_time = datetime.datetime.now()
            approx_time_in_session = (
                current_time - self.dispatcher.session_start_time).total_seconds()

            # Update the color of the time bar to make it slowly change, so
            # that there is a visual indicator if it stops running
            self.line_of_current_time_color = np.mod(
                self.line_of_current_time_color + 0.1, 2)
            
            # Updating the position of the timebar
            self.line_of_current_time.setData(
                x=[approx_time_in_session, approx_time_in_session], y=[-1, 9],
                pen=pg.mkPen(np.abs(self.line_of_current_time_color - 1)),
            )

    def update_plot(self):
        """Update self.plot_handle_poke_times with poke times from dispatcher
        
        * Extracts pokes from 
          self.dispatcher.history_of_pokes 
          and plots as 
          self.plot_handle_unrewarded_pokes

        * Extracts pokes from 
          self.dispatcher.history_of_rewarded_correct_pokes 
          and plots as 
          self.plot_handle_rewarded_correct_pokes

        * Extracts pokes from 
          self.dispatcher.history_of_rewarded_incorrect_pokes 
          and plots as 
          self.plot_handle_rewarded_incorrect_pokes
        """
        # Plot each thing on the left into the thing on the right
        pairs = (
            (self.dispatcher.history_of_pokes, 
            self.plot_handle_unrewarded_pokes),
            (self.dispatcher.history_of_rewarded_correct_pokes , 
            self.plot_handle_rewarded_correct_pokes),
            (self.dispatcher.history_of_rewarded_incorrect_pokes , 
            self.plot_handle_rewarded_incorrect_pokes),            
            )
        
        # Iterate over each pair
        for data_from, plot_to in pairs:
            # Extract x and y vals
            xvals = []
            yvals = []
            
            # Iterate over ports and get poke times from each
            for n_port, port_name in enumerate(self.dispatcher.port_names):
                # Get poke times for this port
                this_poke_times = data_from[port_name]
                
                # The x-value will be the n_port
                port_number = [n_port] * len(this_poke_times)
                
                # Append
                xvals += this_poke_times
                yvals += port_number
            
            # Update plot with the new xvals and yvals
            plot_to.setData(x=xvals, y=yvals)

## Widget to plot pokes
class WheelPositionWidget(QWidget):
    """Widget that plots the wheel position in real time
    
    """
    def __init__(self, dispatcher, *args, **kwargs):
        """Initialize a new WheelPositionWidget

        """
        ## Superclass init
        super().__init__(*args, **kwargs)
        
        
        ## Instance variables
        # Dispatcher, where the data comes from
        self.dispatcher = dispatcher
        
        # Timers for continuous updating
        # Create a QTimer object to continuously update the plot         
        self.timer_update_plot = QTimer(self) 
        self.timer_update_plot.timeout.connect(self.update_plot)  
        
        # Creating a QTimer for updating the moving time bar
        self.timer_update_time_bar = QTimer(self)
        self.timer_update_time_bar.timeout.connect(self.update_time_bar) 

        
        ## Initialize the plot_widget which actually does the plotting
        # Initializing the pyqtgraph widget
        self.plot_widget = pg.PlotWidget() 
        
        # Setting the layout of the plotting widget 
        self.layout = QVBoxLayout(self) 
        self.layout.addWidget(self.plot_widget)
        
        # Set labels and colors of `plot_widget`
        self.setup_plot_graphics()
       
        # Plots line_of_current_time and line
        self.initalize_plot_handles()

    def setup_plot_graphics(self):
        """Sets colors and labels of plot_widget
        
        Flow
        * Sets background to black and font to white
        * Sets title and axis labels
        * Adds a grid
        * Sets y-limits to [1, 9]
        """
        # Show data only from the last N seconds
        self.plot_widget.setXRange(-10, 0)  
        
        # Setting the background of the plot to be black. Use 'w' for white
        self.plot_widget.setBackground("k") 
        
        # Setting the font/style for the rest of the text used in the plot
        styles = {"color": "white", "font-size": "11px"} 
        
        # Adding a grid background to make it easier to see where pokes are in time
        self.plot_widget.showGrid(x=True, y=True) 
        
        # Set the range for the Y axis to match wheel clipping
        self.plot_widget.setYRange(-1050, 1050)
        
        #~ # Set the ticks
        #~ ticks = list(enumerate(self.dispatcher.port_names))
        #~ self.plot_widget.getPlotItem().getAxis('left').setTicks([ticks, []])

    def initalize_plot_handles(self):
        """Plots line_of_current_time and line
        
        Creates these handles:
            self.line_of_current_time : a line that moves with the current time
            self.plot_handle_wheel_position : line graph of the wheel
            self.plot_handle_rewards : a raster plot of rewards
        """
        # Plot the sliding timebar
        self.line_of_current_time_color = 0.5
        self.line_of_current_time = self.plot_widget.plot(
            x=[0, 0], y=[-1, 8], pen=pg.mkPen(self.line_of_current_time_color))

        # Wheel position in white
        self.plot_handle_wheel_position = self.plot_widget.plot(
            x=[],
            y=[],
        )

        # Rewards in green
        self.plot_handle_rewards = self.plot_widget.plot(
            x=[],
            y=[],
            pen=None, # no connecting line
            symbol="arrow_down",  
            symbolSize=10,
            symbolBrush='g',
            symbolPen=None,
        )

    def start(self):
        """Activates plot updates.
        
        Activates `timer` and `time_bar_timer` to update plot.
        Sets `start_time` and `is_active`.
        """
        # Plot updates every 200 ms
        self.timer_update_plot.start(200)  

        # Time bar updates every 50 ms
        self.timer_update_time_bar.start(50)  

    def stop_plot(self):
        """Deactivates plot updates"""
        self.timer_update_plot.stop()
        self.timer_update_time_bar.stop()

    def update_time_bar(self):
        """Controls how the timebar moves according to the timer"""
        # Do nothing if there is no start_time
        if self.dispatcher.session_start_time is not None:
            # Determine elapsed time
            current_time = datetime.datetime.now()
            approx_time_in_session = (
                current_time - self.dispatcher.session_start_time).total_seconds()

            # Update the color of the time bar to make it slowly change, so
            # that there is a visual indicator if it stops running
            self.line_of_current_time_color = np.mod(
                self.line_of_current_time_color + 0.1, 2)
            
            # Updating the position of the timebar
            self.line_of_current_time.setData(
                x=[approx_time_in_session, approx_time_in_session], y=[-1, 9],
                pen=pg.mkPen(np.abs(self.line_of_current_time_color - 1)),
            )

    def update_plot(self):
        """Update plot of wheel time

        """
        # Extract data about wheel
        wheel_pos_x = np.array(self.dispatcher.history_of_wheel_time)
        wheel_pos_y = np.array(self.dispatcher.history_of_wheel_position)
        
        # Relative to time now
        # Note that slight clock differences might mean that the rpi's current
        # time is ahead of our current time
        time_now = datetime.datetime.now()
        wheel_pos_x = np.array(
            [(val - time_now).total_seconds() for val in wheel_pos_x])
        
        # Add a final data point for the present, which is presumably the same
        # as the last measurement
        if len(wheel_pos_y) > 0:
            wheel_pos_x = np.concatenate([wheel_pos_x, [0]])
            wheel_pos_y = np.concatenate([wheel_pos_y, [wheel_pos_y[-1]]])
        
        # Plot
        self.plot_handle_wheel_position.setData(x=wheel_pos_x, y=wheel_pos_y)
        
        #~ # Extract data about rewards
        #~ rewards_x = self.dispatcher.reward_times
        #~ rewards_y = np.zeros_like(rewards_x)
        #~ self.plot_handle_rewards.setData(x=rewards_x, y=rewards_y)
