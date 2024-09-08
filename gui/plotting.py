"""Module for the individual plot widgets"""

import math
from datetime import datetime
import time
import csv
import random
import numpy as np
import zmq
import pyqtgraph as pg
#~ from .worker import Worker


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
#~ from pyqttoast import Toast, ToastPreset
#~ from .logging import print_out

## VISUAL REPRESENTATION OF PORTS
class NosepokeCircle(QGraphicsEllipseItem):
    """Object to represent each individual nosepoke
    
    The ArenaWidget contains references to each of its individual NosepokeCircle.
    Each NosepokeCircle can respond to
    * calculate_position
    * set_color
    """
    def __init__(self, index, total_ports, name):
        # Setting the diameters of the ellipse while initializing the class
        super(NosepokeCircle, self).__init__(0, 0, 38, 38) 
        
        # The location at which the different ports will be arranged (range from 0-7)
        self.index = index 
        
        # Creating a variable for the total number of ports
        self.total_ports = total_ports 
        
        # Setting the label for each port on the GUI
        self.label = QGraphicsTextItem(name, self)
        font = QFont()
        
        # Set the font size here (10 in this example)
        font.setPointSize(8)  
        self.label.setFont(font)
        
        # Positioning the labels within the ellipse
        self.label.setPos(
            19 - self.label.boundingRect().width() / 2, 
            19 - self.label.boundingRect().height() / 2) 
        
        # Positioning the individual ports
        self.setPos(self.calculate_position()) 
        
        # Setting the initial color of the ports to gray
        self.setBrush(QColor("gray")) 

    def calculate_position(self):  
        """
        Function to calculate the position of the ports and arrange them in a circle
        """
        angle = 2 * math.pi * self.index / self.total_ports 
        radius = 62
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        
        # Arranging the Pi signals in a circle based on x and y coordinates 
        # calculated using the radius
        return QPointF(200 + x, 200 + y) 

    def set_color(self, color):
        """
        Function used to change the color from the individual ports during a 
        trial according to the pokes. 
        The logic for when to change to color of the individual ports is 
        mostly present in the worker class.
        QColors currently used for ports: gray (default), green(reward port), 
        red(incorrect port), blue(used previously but not currently)
        """
        if color == "green":
            self.setBrush(QColor("green"))
        elif color == "blue":
            self.setBrush(QColor("blue"))
        elif color == "red":
            self.setBrush(QColor("red"))
        elif color == "gray":
            self.setBrush(QColor("gray"))
        else:
            print_out("Invalid color:", color)


## TRIAL INFORMATION DISPLAY / SESSION CONTROL    
# ArenaWidget Class that represents all ports
class ArenaWidget(QWidget):
    """Displays pokes and also contains logic to start and stop session
    
    This class is the main GUI class that displays the ports on the Raspberry 
    Pi and the information related to the trials. The primary use of the widget 
    is to keep track of the pokes in the trial (done through the port icons 
    and details box). This information is then used to calculate performance 
    metrics like fraction correct and RCP. It also has additional logic to 
    stop and start sessions. 
    
    Most of the work is done by self.worker. 
    This class is just for plotting.
    


    
    """
    def __init__(self, dispatcher, *args, **kwargs):
        """Initialize an ArenaWidget
        

        """
        ## Superclass QWidget init
        super(ArenaWidget, self).__init__(*args, **kwargs)


        # Store
        self.dispatcher = dispatcher
        

        ## Creating the GUI widget to display the Pi signals
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)


        ## Add individual ports to the widget
        self.total_ports = len(self.dispatcher.ports)
        self.nosepoke_circles = []
        for port_idx, port_name in enumerate(self.dispatcher.ports):
            # Create the nosepoke circle
            nosepoke_circle = NosepokeCircle(port_idx, self.total_ports, port_name)
            
            # Store it
            self.nosepoke_circles.append(nosepoke_circle)
            
            # Add it to the scene
            self.scene.addItem(nosepoke_circle)
        

        ## Create timers
        # Create a timer and connect to self.update_time_elapsed
        #~ self.timer = QTimer(self)
        
        # Method to calculate and update elapsed time (can be replaced with date 
        # time instead of current implementation if needed)
        #~ self.timer.timeout.connect(self.update_time_elapsed) 

        # Create timer and connect to update_last_poke_time
        # Initializing QTimer for tracking time since last poke 
        #~ # (resets when poke is detected)
        #~ self.last_poke_timer = QTimer()
        #~ self.last_poke_timer.timeout.connect(self.update_last_poke_time)

        
        ## Lay out all elements
        # Create session progress metrics and labels
        #~ self.set_up_session_progress_layout()
        
        # Put everything in the main layout
        self.set_up_main_layout()

    def set_up_main_layout(self):
        """Add all elements to main layout.
        
        Flow
        * Arranges self.start_button and self.stop_button in QHBoxLayout
        * Arranges the above in QVBoxLayout with self.view
        * Arranges the above in QHBoxLayout with self.details_layout
        * Calls setLayout on the above
        """

        
        # Creating a layout where the port window and buttons are arranged vertically
        view_buttons_layout = QVBoxLayout()
        view_buttons_layout.addWidget(self.view)  
        #~ view_buttons_layout.addLayout(start_stop_layout)  

        # Arranging the previous layout horizontally with the session details
        main_layout = QHBoxLayout(self)
        main_layout.addLayout(view_buttons_layout)  
        #~ main_layout.addLayout(self.details_layout)  

        # Set main_layout as the layout for this widget
        self.setLayout(main_layout)
        
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

    def emit_update_signal(self, poked_port_number, color):
        """Called on poke. Updates metrics and emits updateSignal
        
        Arguments
        ---------
        poked_port_number - int?
        color - str
            If red: it was a non-rewarded poke
            If blue: it was a rewarded poke, but not a correct trial
            If green: it was a rewarded poke, and a correct trial
        
        TODO: The transmitted signal should be a type of poke, not a color
        TODO: Why is self.updateSignal used just to repeat the signal?
        
        This method is to communicate with the plotting object to plot the 
        different outcomes of each poke. 
        This is also used to update the labels present in Pi Widget based on the
        information received over the network by the Worker class
        Some of this logic is already present in the worker class for CSV saving
        but that was implemented after I implemented the initial version here
        
        Flow
        ----
        * Emits updateSignal with poked_port_number and color
        * Stores self.last_poke_timestamp as datetime.now()
        * Updates the number of pokes and trials
        * Updates the performance metric labels
        """
        ## Continue the signal
        # TODO: Why do we need another signal just to repeat the same thing
        # Emit the updateSignal with the received poked_port_number and color 
        # (used for plotting)
        self.updateSignal.emit(poked_port_number, color)
        
        # This timer was present before I changed timing implementation. 
        # Did not try to change it 
        self.last_poke_timestamp = time.time() 


        ## Update the counts
        if color == "red":
            self.red_count += 1
        elif color == "blue":
            self.blue_count += 1
        elif color == "green":
            self.green_count += 1
        else:
            # TODO: Define if this is actually possible, and what to do 
            # in this case
            return
        

        ## Update the metrics
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

    def start_sequence(self):
        """Starts the session
        
        This is connected to self.start_button.clicked
        
        Flow
        ----
        * Emit the startButtonClicked signal
        * Calls self.worker.start_message
        * Starts worker thread
        * QMetaObject.invokeMethod ???
        * Tells MainWindow to start the plot
        * Starts the start_time QTime
        * Start self.timer
        """
        # Emit the startButtonClicked signal
        self.startButtonClicked.emit() 
        
        # Tell the worker to start
        self.worker.start_message()
        
        # Starting the worker thread when the start button is pressed
        self.thread.start()
        
        # Log
        print_out("Experiment Started!")
        
        # Sukrith: what does this do? 
        QMetaObject.invokeMethod(self.worker, "start_sequence", Qt.QueuedConnection) 

        # Sending a message so that the plotting object can start plotting
        self.main_window.poke_plot_widget.start_plot()

        # Start the timer
        self.start_time.start()
        
        # Update every second
        self.timer.start(10)  

    def stop_sequence(self):
        """Stop the session
        
        Flow:
        * QMetaObject.invokeMethod ???
        * Stops plot in main_window
        * Updates text on labels
        * Sets counts to zero
        * Stops self.timer
        * Quits self.thread
        """
        # Sukrith document this
        QMetaObject.invokeMethod(self.worker, "stop_sequence", Qt.QueuedConnection)
        
        # Log
        print_out("Experiment Stopped!")
        
        # Stopping the plot
        self.main_window.poke_plot_widget.stop_plot()
        
        # Reset all labels to intial values 
        # Currently has an issue with time since last poke updating after session is stopped. 
        # Note: This parameter is not saved on the CSV but is just for display)
        self.time_label.setText("Time Elapsed: 00:00")
        self.poke_time_label.setText("Time since last poke: 00:00")
        self.red_label.setText("Number of Pokes: 0")
        self.blue_label.setText("Number of Trials: 0")
        self.green_label.setText("Number of Correct Trials: 0")
        self.fraction_correct_label.setText("Fraction Correct (FC): 0.000")
        self.rcp_label.setText("Rank of Correct Port (RCP): 0")

        # Resetting poke and trial counts
        self.red_count = 0
        self.blue_count = 0
        self.green_count = 0

        # Stopping the timer for the session 
        self.timer.stop()
        
        # Quitting the thread so a new session can be started
        self.thread.quit()

    
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

    def save_results_to_csv(self):
        """Save results
        
        Tells worker to stop
        Tells worker to save results to csv
        Sets a toast notification
        """
        # Tell worker to stop
        self.worker.stop_message()
        
        # Tell worker to save
        self.worker.save_results_to_csv()
        
        # Send toast notification
        toast = Toast(self) # Initializing a toast message
        toast.setDuration(5000)  # Hide after 5 seconds
        toast.setTitle('Results Saved') # Printing acknowledgement in terminal
        
        # Setting text for the toast message
        toast.setText('Log saved to /home/mouse/dev/paclab_sukrith/logs') 
        toast.applyPreset(ToastPreset.SUCCESS)  # Apply style preset
        toast.show()


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
        self.plot_widget.setYRange(-0.5, len(self.dispatcher.ports))
        
        # Set the ticks
        ticks = list(enumerate(self.dispatcher.ports))
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
        for n_port, port_name in enumerate(self.dispatcher.ports):
            # Get poke times for this port
            this_poke_times = self.dispatcher.poked_port_history[port_name]
            
            # The x-value will be the n_port
            port_number = [n_port] * len(this_poke_times)
            
            # Append
            xvals += this_poke_times
            yvals += port_number
        
        # Update plot with the new xvals and yvals
        self.plot_handle_poke_times1.setData(x=xvals, y=yvals)
        self.plot_handle_poke_times2.setData(x=xvals, y=yvals)
