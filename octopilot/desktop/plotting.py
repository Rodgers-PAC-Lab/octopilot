"""Module for the individual plot widgets

Each individual widget should be initialized with the Dispatcher, 
and get the data it needs by reading the attributes of the Dispatcher.
"""

import math
from datetime import datetime
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

    def create_layout(self, port_names, port_positions):
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
            ellipse = QGraphicsEllipseItem(0, 0, 38, 38) 
            
            # Setting the label for each port on the GUI
            label = QGraphicsTextItem(port_name, ellipse)
            font = QFont()
            font.setPointSize(8)  
            label.setFont(font)
        
            # Positioning the labels within the ellipse
            label.setPos(
                19 - label.boundingRect().width() / 2, 
                19 - label.boundingRect().height() / 2,
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

    def calculate_position(self, port_position):  
        """Return QPointF corresponding to `port_position`
        
        port_position : numeric
            Angle of the port, in degrees
        """
        # Subtracting 90 makes 0 north, although I'm not really sure why
        # Is QPointF from the upper left or lower left?
        angle = (port_position - 90) * math.pi / 180
        radius = 62
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        
        # Arranging the Pi signals in a circle based on x and y coordinates 
        # calculated using the radius
        return QPointF(200 + x, 200 + y) 

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
    def set_up_session_progress_layout(self):
        """Create a Session Progress layout"""
        # Create QVBoxLayout for session details 
        self.details_layout = QVBoxLayout()

        # Variables to keep track of poke outcomes
        # TODO: rename by what it means, not its color
        self.red_count = 0
        self.blue_count = 0
        self.green_count = 0
        
        # QTime since session start or last poke
        # Sukrith: are these actually used anywhere?
        self.start_time = QTime(0, 0)
        #~ self.poke_time = QTime(0, 0)

        # Setting title 
        bold_font = QFont()
        bold_font.setBold(True)
        self.title_label = QLabel("Session Details:", self)
        self.title_label.setFont(bold_font)

        # Making labels that constantly update according to the session details
        self.time_label = QLabel("Time Elapsed: 00:00", self)
        self.poke_time_label = QLabel("Time since last poke: 00:00", self)
        self.red_label = QLabel("Number of Pokes: 0", self)
        self.blue_label = QLabel("Number of Trials: 0", self)
        self.green_label = QLabel("Number of Correct Trials: 0", self)
        self.fraction_correct_label = QLabel("Fraction Correct (FC): 0.000", self)
        self.rcp_label = QLabel("Rank of Correct Port (RCP): 0", self)
        
        # Adding these labels to the layout used to contain the session information 
        self.details_layout.addWidget(self.title_label)
        self.details_layout.addWidget(self.time_label)
        self.details_layout.addWidget(self.poke_time_label)
        self.details_layout.addWidget(self.red_label)
        self.details_layout.addWidget(self.blue_label)
        self.details_layout.addWidget(self.green_label)
        self.details_layout.addWidget(self.fraction_correct_label)
        self.details_layout.addWidget(self.rcp_label)       
    
    def update(self):
        # Updating the number of pokes (red + green + blue)
        n_pokes = self.red_count + self.green_count + self.blue_count
        self.red_label.setText(f"Number of Pokes: {(n_pokes)}")
        
        # Update the number of trials (green + blue)
        n_trials = self.blue_count + self.green_count
        self.blue_label.setText(f"Number of Trials: {n_trials}")            

        # Updating number of correct trials 
        n_correct_trials = self.green_count
        self.green_label.setText(
            f"Number of Correct Trials: {n_correct_trials}") 

        # Update fraction correct
        if n_trials > 0:
            self.fraction_correct = n_correct_trials / n_trials
        else:
            self.fraction_correct = np.nan
        
        # Update fraction correct label
        if self.fraction_correct is None:
            self.fraction_correct_label.setText(
                f"Fraction Correct (FC): NA")    
        else:
            self.fraction_correct_label.setText(
                f"Fraction Correct (FC): {self.fraction_correct:.3f}")        
    
    @pyqtSlot() 
    def update_time_elapsed(self):
        """Updates self.time_label with time elapsed
        
        Connected to self.timer.timeout
        """
        # Timer to display the elapsed time in a particular session 
        # Convert milliseconds to seconds
        elapsed_time = self.start_time.elapsed() / 1000.0  
        
        # Convert seconds to minutes:seconds
        minutes, seconds = divmod(elapsed_time, 60)  
        
        # Update the QLabel text with the elapsed time in minutes and seconds
        # Sukrith what is zfill?
        str1 = str(int(minutes)).zfill(2)
        str2 = str(int(seconds)).zfill(2)
        self.time_label.setText(f"Time elapsed: {str1}:{str2}")
    
    @pyqtSlot()
    def reset_last_poke_time(self):
        """Stop and start last_poke_timer whenever a poke is detected (why?)
        
        Connected to self.worker.pokedportsignal
        Sukrith is this necessary?
        """
        # Stopping the timer whenever a poke is detected 
        self.last_poke_timer.stop()

        # Start the timer again
        # Setting update interval to 1s (1000 ms)
        self.last_poke_timer.start(1000)  
        
    @pyqtSlot()
    def calc_and_update_avg_unique_ports(self):
        """Updates displayed RCP
        
        Connected to self.worker.pokedportsignal
        Gets rcp from self.worker and sets text label
        """
        self.worker.calculate_average_unique_ports()
        average_unique_ports = self.worker.average_unique_ports
        self.rcp_label.setText(f"Rank of Correct Port: {average_unique_ports:.2f}")
    
    @pyqtSlot()
    def update_last_poke_time(self):
        """Update the displayed time since last poke
        
        Connected to self.last_poke_timer.timeout
        """
        # Calculate the elapsed time since the last poke
        current_time = time.time()
        elapsed_time = current_time - self.last_poke_timestamp

        # Constantly update the QLabel text with the time since the last poke
        # Convert seconds to minutes and seconds
        minutes, seconds = divmod(elapsed_time, 60)  
        
        # Update label
        str1 = str(int(minutes)).zfill(2)
        str2 = str(int(seconds)).zfill(2)
        self.poke_time_label.setText(f"Time since last poke: {str1}:{str2}")

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
        
        # Setting the title of the plot 
        self.plot_widget.setTitle("Pokes vs Time", color="white", size="12px") 
        
        # Setting the font/style for the rest of the text used in the plot
        styles = {"color": "white", "font-size": "11px"} 
        
        # Setting label for y axis
        self.plot_widget.setLabel("left", "Port", **styles) 
        
        # Setting label for x axis 
        self.plot_widget.setLabel("bottom", "Time (s)", **styles) 
        self.plot_widget.addLegend()
        
        # Adding a grid background to make it easier to see where pokes are in time
        self.plot_widget.showGrid(x=True, y=True) 
        
        # Setting the range for the Y axis
        self.plot_widget.setYRange(-0.5, len(self.dispatcher.port_names))
        
        # Set the ticks
        ticks = list(enumerate(self.dispatcher.port_names))
        self.plot_widget.getPlotItem().getAxis('left').setTicks([ticks, []])

    def initalize_plot_handles(self):
        """Plots line_of_current_time and line"""
        # Plot the sliding timebar
        self.line_of_current_time_color = 0.5
        self.line_of_current_time = self.plot_widget.plot(
            x=[0, 0], y=[-1, 8], pen=pg.mkPen(self.line_of_current_time_color))

        # Included a separate symbol here that shows as a tiny dot under the 
        # raster to make it easier to distinguish multiple pokes in sequence
        self.plot_handle_poke_times1 = self.plot_widget.plot(
            [],
            [],
            pen=None,
            symbol="o", 
            symbolSize=1,
            symbolBrush="r",
        )

        self.plot_handle_poke_times2 = self.plot_widget.plot(
            [],
            [],
            pen=None, # no connecting line
            symbol="arrow_down",  
            symbolSize=20, # use 8 or lower if using dots
            symbolBrush='r',
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
            current_time = datetime.now()
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
        
        """
        # Extract x and y vals
        xvals = []
        yvals = []
        
        # Iterate over ports and get poke times from each
        for n_port, port_name in enumerate(self.dispatcher.port_names):
            # Get poke times for this port
            this_poke_times = self.dispatcher.history_of_pokes[port_name]
            
            # The x-value will be the n_port
            port_number = [n_port] * len(this_poke_times)
            
            # Append
            xvals += this_poke_times
            yvals += port_number
        
        # Update plot with the new xvals and yvals
        self.plot_handle_poke_times1.setData(x=xvals, y=yvals)
        self.plot_handle_poke_times2.setData(x=xvals, y=yvals)
