"""Module for the individual plot widgets"""

import math
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
from pyqttoast import Toast, ToastPreset


## VISUAL REPRESENTATION OF PORTS
class NosepokeCircle(QGraphicsEllipseItem):
    """Object to represent each individual nosepoke
    
    The ArenaWidget contains references to each of its individual NosepokeCircle.
    Each NosepokeCircle can respond to
    * calculate_position
    * set_color
    """
    def __init__(self, index, total_ports, params):
        # Setting the diameters of the ellipse while initializing the class
        super(NosepokeCircle, self).__init__(0, 0, 38, 38) 
        
        # The location at which the different ports will be arranged (range from 0-7)
        self.index = index 
        
        # Creating a variable for the total number of ports
        self.total_ports = total_ports 
        
        # Defining list and order of the ports
        # Ensure index is within specified number of ports listed in params 
        if 0 <= self.index < len(params['ports']): 
            port_data = params['ports'][self.index]
            
            # Assigning a label to each port index in params 
            label_text = port_data['label'] 
        
        # Setting the label for each port on the GUI
        self.label = QGraphicsTextItem(f"Port-{port_data['label']}", self) 
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


## HANDLING LOGIC FOR OTHER GUI CLASSES (TO LOWER LOAD)
class Worker(QObject):
    """
    The Worker class primarily communicates with the NosepokeCircle and 
    ArenaWidget classes. 
    It handles the logic of starting sessions, stopping sessions, 
    choosing reward ports
    sending messages to the pis (about reward ports), sending acknowledgements 
    for completed trials (needs to be changed).
    The Worker class also handles tracking information regarding each 
    poke / trial and saving them to a csv file.
    """
    # Sukrith: Why is this a class variable?
    # Signal emitted when a poke occurs (This is used to communicate with 
    # other classes that strictly handle defining GUI elements)
    pokedportsignal = pyqtSignal(int, str)

    def __init__(self, arena_widget, params):
        super().__init__()
        self.initial_time = None
        
        """
        Setting up a ZMQ socket to send and receive information about poked ports 
        (the DEALER socket on the Pi initiates the connection and then the ROUTER 
        manages the message queue from different dealers and sends acknowledgements)
        """
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.ROUTER)
        
        # Making it bind to the port used for sending poke related information
        self.socket.bind("tcp://*" + params['worker_port'])   
        
        """
        Making lists to store the trial parameters for each poke.
        We append the parameters at each poke to these lists so that we can write them to a CSV
        """
        self.amplitudes = []
        self.target_rates = []
        self.target_temporal_log_stds = []
        self.center_freqs = []

        # Tracking the parameters that need to be saved at every poke
        self.current_amplitude = 0.0
        self.current_target_rate = 0.0
        self.current_target_temporal_log_std = 0.0
        self.current_center_freq = 0.0
        self.current_bandwidth = 0.0
        self.current_poke = 0
        self.current_completed_trials = 0
        self.current_correct_trials = 0
        self.current_fraction_correct = 0
        
        # Initializing variables to track information used to control the logic of the task
        
        # Stores the identity of the pi that sent the most recent message
        self.last_pi_received = None 
        # Used while randomly selecting ports to make sure that the same port is not rewarded twice
        self.prev_choice = None 
        # Used to create a QTimer when the sequence is started
        self.timer = None  
        self.current_task = None # Used to keep track of the current task (used in naming the CSV file)
        self.ports = None

        
        # Connecting the Worker Class to ArenaWidget elements 
        self.arena_widget = arena_widget
        self.total_ports = self.arena_widget.total_ports 
        self.Pi_signals = self.arena_widget.Pi_signals
        self.poked_port_numbers = self.arena_widget.poked_port_numbers 

        """
        Variables used to store the functions to map the labels of ports present 
        in the params file of a particular to indicies and vice versa
        It is essentially to make sure that the labels of the ports are at the 
        right positions on the GUI widget
        """
        # Used to relate a label of a port to the index of that particular port in the GUI
        self.label_to_index = None 
        
        # Used this to properly update the port according to its label
        self.index_to_label = None 
        self.index = None
        
        # Variables to keep track of reward related messages 
        self.identities = set() # Set of identities of all pis connected to that instance of ther GUI 
        self.last_poke_timestamp = None  # Variable to store the timestamp of the last poke 
        self.reward_port = None # Keeping track of the current reward port
        self.last_rewarded_port = None # Keeping track of last rewarded port

        # Initializing variables and lists to store trial information 
        self.trials = 0 # Number of pokes per trial (needs to be renamed) 
        self.timestamps = []
        self.pokes = []
        self.completed_trials = []
        self.correct_trials = []
        self.fc = []
        self.reward_ports = []
        
        """
        These variables were used in my calculation for RCP, I don't think I've 
        implemented it correctly so these might need to be removed or changed
        """
        self.unique_ports_visited = []  # List to store unique ports visited in each trial
        self.unique_ports_colors = {}  # Dictionary to store the outcome for each unique port
        self.average_unique_ports = 0  # Variable to store the average number of unique ports visited
    
    # Method that contains logic to be executed when a new session is started
    @pyqtSlot()
    def start_sequence(self):
        """
        First we store the initial timestamp where the session was started in a 
        variable. This used with the poketimes sent by the pi to calculate the 
        time at which the pokes occured
        """
        self.initial_time = datetime.now() 
        print(self.initial_time)
        
        # Resetting sequences when a new session is started 
        self.timestamps = []
        self.reward_ports = []
        
        # Randomly choosing the initial reward port
        self.reward_port = self.choose()
        reward_message = f"Reward Port: {self.reward_port}"
        print_out(reward_message)
        
        # Sending the current reward port to all connected pis
        for identity in self.identities:
            self.socket.send_multipart([identity, bytes(reward_message, 'utf-8')])
        
        # Creating a dictionary that takes the label of each port and matches it to the index on the GUI (used for reordering)
        self.ports = params['ports']
        
        # Refer to documentation when variables were initialized 
        self.label_to_index = {port['label']: port['index'] for port in self.ports} 
        self.index_to_label = {port['index']: port['label'] for port in self.ports}
        
        # Setting an index of remapped ports (so that colors can be changed accordign to label)
        self.index = self.label_to_index.get(str(self.reward_port)) 
        
        # Set the color of the initial reward port to green
        self.Pi_signals[self.index].set_color("green")

        # Start the timer loop
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_Pi)
        self.timer.start(10)

    # Method that contains logic to be executed when a session is completed
    @pyqtSlot()
    def stop_sequence(self):
        if self.timer is not None:
            self.timer.stop() # Stops the timer for the session 
            
            # Blocking out communication with the Pis till a new session is started 
            self.timer.timeout.disconnect(self.update_Pi) 
        
        # Clearing recorded data for the completed session and resetting necessary variables
        self.initial_time = None
        self.timestamps.clear()
        self.reward_ports.clear()
        self.poked_port_numbers.clear()
        self.amplitudes.clear()
        self.target_rates.clear()
        self.target_temporal_log_stds.clear()
        self.center_freqs.clear()
        self.unique_ports_visited.clear()
        self.identities.clear()
        self.last_poke_timestamp = None
        self.reward_port = None
        self.trials = 0
        self.average_unique_ports = 0
    
    # Method to update unique ports visited (used to calculate RCP on GUI)
    def update_unique_ports(self):
        # Calculate unique ports visited in the current trial
        unique_ports = set(self.poked_port_numbers)
        self.unique_ports_visited.append(len(unique_ports))
 
    # Method to calculate the average number of unique ports visited (used to calculate RCP on GUI)
    def calculate_average_unique_ports(self):
        # Calculate the average number of unique ports visited per trial
        if self.unique_ports_visited:
            self.average_unique_ports = sum(self.unique_ports_visited) / len(self.unique_ports_visited)
            
    # Method to randomly choose next port to reward
    def choose(self):
        ports = active_nosepokes # Getting the list of choices to choose from  
        
        # Setting up a new set of possible choices after omitting the previously rewarded port
        poss_choices = [choice for choice in ports if choice != self.prev_choice] 
        
        # Randomly choosing within the new set of possible choices
        new_choice =  random.choice(poss_choices) 
        
        #Updating the previous choice that was made so the next choice can omit it 
        self.prev_choice = new_choice  
        return new_choice
    
    """
    ** This is the main method of this class that controls most of the logic for the GUI **
    Method to handle the updating Pis (sending and receiving poke related information and executing logic)
    """
    @pyqtSlot()
    def update_Pi(self):
        
        # Updating time related information 
        current_time = datetime.now() # Used to name the file 
        elapsed_time = current_time - self.initial_time # Used to display elapsed time in the Pi Widget class
        self.last_poke_timestamp = current_time # Update the last poke timestamp whenever a poke  occurs
        
        """
        This is the logic on what to do when the GUI receives messages that aren't pokes
        'rpi': Initial connection to all the pis trying to connect to the GUI 
        (Debug message to see if all Pis are connected)
        'stop': Pauses all updates from the Pi when the session is stopped
        'start': Setting a new reward port whenever a new session is started 
        after the previous one is stopped (might be redundant but works for now)
        'Current Parameters': Sends all the sound parameters for every trial; 
        the values are extracted from a string and then appended to lists to be saved in a csv 
        """
        try:
            # Waiting to receive messages from the pis
            identity, message = self.socket.recv_multipart()
            self.identities.add(identity)
            
            # Converting all messages from bytes to strings
            message_str = message.decode('utf-8')
            
            # Message from pi side that initiates the connection 
            if "rpi" in message_str:
                print_out("Connected to Raspberry Pi:", message_str)
            
            # Message to stop updates if the session is stopped
            if message_str.strip().lower() == "stop":
                print_out("Received 'stop' message, aborting update.")
                return
            
            # Sending the initial message to start the loop
            self.socket.send_multipart([identity, bytes(f"Reward Port: {self.reward_port}", 'utf-8')])

            # Starting next session
            if message_str.strip().lower() == "start":
                self.socket.send_multipart([identity, bytes(f"Reward Port: {self.reward_port}", 'utf-8')])
    
            # Keeping track of current parameters for every trial 
            if "Current Parameters" in message_str:
                sound_parameters = message_str
                print_out("Updated:", message_str) 
                
                # Remove the "Current Parameters - " part and strip any whitespace
                param_string = sound_parameters.split("-", 1)[1].strip()
                
                # Extracting parameters from message strings
                params = {}
                for param in param_string.split(','):
                    key, value = param.split(':')
                    params[key.strip()] = value.strip()
                
                # Extract and convert the strings to numeric values
                self.current_amplitude = float(params.get("Amplitude", 0))
                self.current_target_rate = float(params.get("Rate", "0").split()[0])
                self.current_target_temporal_log_std = float(params.get("Irregularity", "0").split()[0])
                self.current_center_freq = float(params.get("Center Frequency", "0").split()[0])
                self.current_bandwidth = float(params.get("Bandwidth", "0"))
                
            else:
                """
                Logic for what to do when a poke is received
                """
                poked_port = int(message_str) # Converting message string to int 
                
                # Check if the poked port is the same as the last rewarded port
                if poked_port == self.last_rewarded_port:
                     # If it is, do nothing and return
                        return

                # For any label in the list of port labels, correlate it to the index of the port in the visual arrangement in the widget  
                if 1 <= poked_port <= self.total_ports:
                    poked_port_index = self.label_to_index.get(message_str)
                    poked_port_icon = self.Pi_signals[poked_port_index]

                    """
                    Choosing colors to represent the outcome of each poke in the context of the trial
                    green: correct trial
                    blue: completed trial
                    red: pokes at all ports that aren't the reward port
                    """                    
                    if poked_port == self.reward_port:
                        color = "green" if self.trials == 0 else "blue"
                        if self.trials > 0:
                            self.trials = 0
                    else:
                        color = "red" 
                        self.trials += 1
                        self.current_poke += 1

                    # Setting the color of the port on the Pi Widget
                    poked_port_icon.set_color(color)
                    
                    # Appending the poked port to a sequence that contains all pokes during a session
                    self.poked_port_numbers.append(poked_port)
                    print_out("Sequence:", self.poked_port_numbers) # Can be commented out to declutter terminal
                    self.last_pi_received = identity

                    # Sending information regarding poke and outcome of poke to Pi Widget
                    self.pokedportsignal.emit(poked_port, color)
                    
                    # Appending the current reward port to save to csv 
                    self.reward_ports.append(self.reward_port)
                    
                    # Used to update RCP calculation
                    self.update_unique_ports()
                    
                    # Updating poke / trial related information depending on the outcome of the poke
                    if color == "green" or color == "blue":
                        self.current_poke += 1 # Updating number of pokes in the session 
                        self.current_completed_trials += 1 # Updating the number of trials in the session 
                        
                        # Sending an acknowledgement to the Pis when the reward port is poked
                        for identity in self.identities:
                            self.socket.send_multipart([identity, bytes(f"Reward Poke Completed: {self.reward_port}", 'utf-8]')])
                        
                        # Storing the completed reward port to make sure the next choice is not at the same port
                        self.last_rewarded_port = self.reward_port 
                        self.reward_port = self.choose() 
                        self.trials = 0 # Resetting the number of pokes that have happened in the trial
                        print_out(f"Reward Port: {self.reward_port}")
                        
                        # Logic for if a correct trial is completed
                        if color == "green":
                            self.current_correct_trials += 1 # Updating count for correct trials
                            self.current_fraction_correct = self.current_correct_trials / self.current_completed_trials

                        # Finding the index in the visual representation depending on the 
                        index = self.index_to_label.get(poked_port_index)
                        
                        # When a new trial is started reset color of all non-reward ports to gray and set new reward port to green
                        for index, Pi in enumerate(self.Pi_signals):
                            if index + 1 == self.reward_port: # This might be a hack that doesnt work for some boxes (needs to be changed)
                                Pi.set_color("green")
                            else:
                                Pi.set_color("gray")

                        # Sending the reward port to all connected Pis after a trial is completed
                        for identity in self.identities:
                            self.socket.send_multipart([identity, bytes(f"Reward Port: {self.reward_port}", 'utf-8')])
                            
                    
                    # Appending all the information at the time of a particular poke to their respective lists
                    self.pokes.append(self.current_poke)
                    self.timestamps.append(elapsed_time)
                    self.amplitudes.append(self.current_amplitude)
                    self.target_rates.append(self.current_target_rate)
                    self.target_temporal_log_stds.append(self.current_target_temporal_log_std)
                    self.center_freqs.append(self.current_center_freq)
                    self.completed_trials.append(self.current_completed_trials)
                    self.correct_trials.append(self.current_correct_trials)
                    self.fc.append(self.current_fraction_correct)
        
        except ValueError:
            pass
            #print_out("Unknown message:", message_str)
            
    
   # Method to save results to a CSV file
    def save_results_to_csv(self):
        global current_task, current_time
        
        # Specifying the directory where you want to save the CSV files
        save_directory = params['save_directory']
        
        # Generating filename based on current_task and current date/time
        filename = f"{current_task}_{current_time}_saved.csv"
        
        # Saving the results to a CSV file
        with open(f"{save_directory}/{filename}", 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Writing the header row for the CSV file with parameters to be saved as the columns
            writer.writerow(["No. of Pokes", "Poke Timestamp (seconds)", "Port Visited", "Current Reward Port", "No. of Trials", "No. of Correct Trials", "Fraction Correct", "Amplitude", "Rate", "Irregularity", "Center Frequency"])
           
           # Assigning the values at each individual poke to the columns in the CSV file
            for poke, timestamp, poked_port, reward_port, completed_trial, correct_trial, fc, amplitude, target_rate, target_temporal_log_std, center_freq in zip(
                self.pokes, self.timestamps, self.poked_port_numbers, self.reward_ports, self.completed_trials, self.correct_trials, self.fc, self.amplitudes, self.target_rates, self.target_temporal_log_stds, self.center_freqs):
                writer.writerow([poke, timestamp, poked_port, reward_port, completed_trial, correct_trial, fc, amplitude, target_rate, target_temporal_log_std, center_freq])

        print_out(f"Results saved to logs")
    
    # Method to send start message to the pi
    def start_message(self):
        for identity in self.identities:
            self.socket.send_multipart([identity, b"start"])
    
    # Method to send a stop message to the pi
    def stop_message(self):        
        for identity in self.identities:
            self.socket.send_multipart([identity, b"stop"])
        for index, Pi in enumerate(self.Pi_signals):
            Pi.set_color("gray")


## TRIAL INFORMATION DISPLAY / SESSION CONTROL    
# ArenaWidget Class that represents all ports
class ArenaWidget(QWidget):
    """This class is the main GUI class that displays the ports on the Raspberry 
    Pi and the information related to the trials. The primary use of the widget 
    is to keep track of the pokes in the trial (done through the port icons 
    and details box). This information is then used to calculate performance 
    metrics like fraction correct and RCP. It also has additional logic to 
    stop and start sessions. 
    """

    # Signals that communicate with the Worker class
    startButtonClicked = pyqtSignal() # Signal that is emitted whenever the start button is pressed (connects to the logic in Worker class)
    updateSignal = pyqtSignal(int, str) # Signal to emit the id and outcome of the current poke

    def __init__(self, main_window, params, *args, **kwargs):
        # Superclass QWidget init
        super(ArenaWidget, self).__init__(*args, **kwargs)

        # Creating the GUI widget to display the Pi signals
        self.main_window = main_window
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)

        # Adding individual ports to the widget 
        self.total_ports = 8
        self.Pi_signals = [NosepokeCircle(i, self.total_ports, params) for i in range(self.total_ports)]
        [self.scene.addItem(Pi) for Pi in self.Pi_signals]
        
        # Setting for bold font
        font = QFont()
        font.setBold(True)
        
        # Creating buttons to control the session (connects to the stop and start logic present in the worker class )
        self.poked_port_numbers = []
        self.start_button = QPushButton("Start Session")
        self.start_button.setStyleSheet("background-color : green; color: white;") # Changing the color of the buttons
        #self.start_button.setFont(font)   
        self.stop_button = QPushButton("Stop Session")
        self.stop_button.setStyleSheet("background-color : red; color: white;") 
        #self.stop_button.setFont(font)   
        self.stop_button.clicked.connect(self.save_results_to_csv)  # Making it so that the results are saved to a csvv when the session is stopped

        # Making a timer to be displayed on the GUI 
        self.timer = QTimer(self)
        
        # Method to calculate and update elapsed time (can be replaced with date time instead of current implementation if needed)
        self.timer.timeout.connect(self.update_time_elapsed) 
        
        # Setting initial time to zero for all labels
        self.start_time = QTime(0, 0)
        self.poke_time = QTime(0, 0)

        # Variables to keep track of poke outcomes (can be renamed if needed)
        self.red_count = 0
        self.blue_count = 0
        self.green_count = 0

        # Create QVBoxLayout for session details 
        self.details_layout = QVBoxLayout()
        
        # Setting title 
        self.title_label = QLabel("Session Details:", self)
        self.title_label.setFont(font)
        
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

        # Initializing QTimer for tracking time since last poke (resets when poke is detected)
        self.last_poke_timer = QTimer()
        self.last_poke_timer.timeout.connect(self.update_last_poke_time)

        # Creating horizontal layout for start and stop buttons
        start_stop_layout = QHBoxLayout()
        start_stop_layout.addWidget(self.start_button)
        start_stop_layout.addWidget(self.stop_button)

        # Creating a layout where the port window and buttons are arranged vertically
        view_buttons_layout = QVBoxLayout()
        view_buttons_layout.addWidget(self.view)  
        view_buttons_layout.addLayout(start_stop_layout)  

        # Arranging the previous layout horizontally with the session details
        main_layout = QHBoxLayout(self)
        main_layout.addLayout(view_buttons_layout)  
        main_layout.addLayout(self.details_layout)  

        # Set main_layout as the layout for this widget
        self.setLayout(main_layout)

        # Creating an instance of the Worker Class and a QThread to handle the logic in a separate thread from the GUI elements
        self.worker = Worker(self, params)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)  # Move the worker object to the thread
        
        # Connect the start button to the start_sequence function (includes start logic from the worker class)
        self.start_button.clicked.connect(self.start_sequence)

        # Connect the stop button to the stop_sequence function
        self.stop_button.clicked.connect(self.stop_sequence)  
        
        # Connect the pokedportsignal from the Worker to slots that call some methods in Pi Widget
        
        self.worker.pokedportsignal.connect(self.emit_update_signal)  # Connect the pokedportsignal to the emit_update_signal function
        self.worker.pokedportsignal.connect(self.reset_last_poke_time)
        
        # Used for RCP calculation (needs to be changed)
        self.worker.pokedportsignal.connect(self.calc_and_update_avg_unique_ports) 

    # Function to emit the update signal
    def emit_update_signal(self, poked_port_number, color):
        """
        This method is to communicate with the plotting object to plot the 
        different outcomes of each poke. 
        This is also used to update the labels present in Pi Widget based on the
        information received over the network by the Worker class
        Some of this logic is already present in the worker class for CSV saving
        but that was implemented after I implemented the initial version here
        """
        # Emit the updateSignal with the received poked_port_number and color (used for plotting)
        self.updateSignal.emit(poked_port_number, color)
        self.last_poke_timestamp = time.time() # This timer was present before I changed timing implementation. Did not try to change it 

        # Logic for non-reward pokes
        if color == "red":
            self.red_count += 1
            self.red_label.setText(f"Number of Pokes: {(self.red_count + self.green_count + self.blue_count)}") # Updating the number of pokes

        # Logic for completed trials
        if color == "blue":
            self.blue_count += 1
            self.red_label.setText(f"Number of Pokes: {(self.red_count + self.green_count + self.blue_count)}")
            self.blue_label.setText(f"Number of Trials: {(self.blue_count + self.green_count)}") # Updating number of completed trials
            if self.blue_count != 0:
                self.fraction_correct = self.green_count / (self.blue_count + self.green_count) # Updating fraction correct
                self.fraction_correct_label.setText(f"Fraction Correct (FC): {self.fraction_correct:.3f}")

        # Logic for correct trials
        elif color == "green":
            self.green_count += 1
            self.red_label.setText(f"Number of Pokes: {(self.red_count + self.green_count + self.blue_count)}")
            self.blue_label.setText(f"Number of Trials: {(self.blue_count + self.green_count)}")
            self.green_label.setText(f"Number of Correct Trials: {self.green_count}") # Updating number of correct trials 
            if self.blue_count == 0:
                self.fraction_correct_label.setText(f"Fraction Correct (FC): {(self.green_count/self.green_count):.3f}")    
            elif self.blue_count != 0:
                self.fraction_correct = self.green_count / (self.blue_count + self.green_count)
                self.fraction_correct_label.setText(f"Fraction Correct (FC): {self.fraction_correct:.3f}")

    # Method to start the session using the button on the GUI
    def start_sequence(self):
        self.startButtonClicked.emit() 
        self.worker.start_message() # Initiating start logic on the worker class
        
        # Starting the worker thread when the start button is pressed
        self.thread.start()
        print_out("Experiment Started!")
        QMetaObject.invokeMethod(self.worker, "start_sequence", Qt.QueuedConnection) 

        # Sending a message so that the plotting object can start plotting
        self.main_window.plot_window.start_plot()

        # Start the timer
        self.start_time.start()
        self.timer.start(10)  # Update every second               

    # Method of what to do when the session is stopped
    def stop_sequence(self):
        QMetaObject.invokeMethod(self.worker, "stop_sequence", Qt.QueuedConnection)
        print_out("Experiment Stopped!")
        
        # Stopping the plot
        self.main_window.plot_window.stop_plot()
        
        # Reset all labels to intial values 
        """
        Currently hasan issue with time since last poke updating after session is stopped. 
        Note: This parameter is not saved on the CSV but is just for display)
        """
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

    # Decorater function used to incorporate methods into slots
    @pyqtSlot() 
    def update_time_elapsed(self):
        # Timer to display the elapsed time in a particular session 
        elapsed_time = self.start_time.elapsed() / 1000.0  # Convert milliseconds to seconds
        minutes, seconds = divmod(elapsed_time, 60)  # Convert seconds to minutes:seconds
        # Update the QLabel text with the elapsed time in minutes and seconds
        self.time_label.setText(f"Time elapsed: {str(int(minutes)).zfill(2)}:{str(int(seconds)).zfill(2)}")
           
    # Method that stops and then starts the timer everytime a poke is detected 
    @pyqtSlot()
    def reset_last_poke_time(self):
        # Stopping the timer whenever a poke is detected 
        self.last_poke_timer.stop()

        # Start the timer again
        self.last_poke_timer.start(1000)  # Setting update interval to 1s (1000 ms)
        
    # RCP related function to calculate the number of unique ports visited in a trial and calculate average (currently incorrect)
    @pyqtSlot()
    def calc_and_update_avg_unique_ports(self):
        self.worker.calculate_average_unique_ports()
        average_unique_ports = self.worker.average_unique_ports
        self.rcp_label.setText(f"Rank of Correct Port: {average_unique_ports:.2f}")
    
    # Method to keep track of the time elapsed between pokes (not sure why I made this a separate method)
    @pyqtSlot()
    def update_last_poke_time(self):
        # Calculate the elapsed time since the last poke
        current_time = time.time()
        elapsed_time = current_time - self.last_poke_timestamp

        # Constantly update the QLabel text with the time since the last poke
        minutes, seconds = divmod(elapsed_time, 60)  # Convert seconds to minutes and seconds
        self.poke_time_label.setText(f"Time since last poke: {str(int(minutes)).zfill(2)}:{str(int(seconds)).zfill(2)}")

    # Method to save results by calling the worker method 
    def save_results_to_csv(self):
        self.worker.stop_message()
        self.worker.save_results_to_csv()  # Calling worker method to save results
        toast = Toast(self) # Initializing a toast message
        toast.setDuration(5000)  # Hide after 5 seconds
        toast.setTitle('Results Saved') # Printing acknowledgement in terminal
        toast.setText('Log saved to /home/mouse/dev/paclab_sukrith/logs') # Setting text for the toast message
        toast.applyPreset(ToastPreset.SUCCESS)  # Apply style preset
        toast.show()


## PLOTTING 

class PlotWindow(QWidget):
    """Widget that plots the pokes as they happen
    
    This class defines a pyqtgraph plot that updates in real-time based on 
    the pokes received by Pi Widget
    It is connected to ArenaWidget but updates in accordance to updates 
    received by worker since ArenaWidget uses its methods
    It communicates using the signals updateSignal and startbuttonClicked 
    """
    def __init__(self, arena_widget, *args, **kwargs):
        """Initialize a new PlotWindow
        
        arena_widget : the corresponding ArenaWidget 
        """
        ## Superclass QWidget init
        super().__init__(*args, **kwargs)
        
        
        ## Flags
        # Flag to check if the Start Button is pressed
        self.is_active = False  
        
        # Initializing the start time 
        self.start_time = None 
        
        
        ## Timers for continuous updating
        # Create a QTimer object to continuously update the plot         
        self.timer = QTimer(self) 
        self.timer.timeout.connect(self.update_plot)  
        
        # Creating a QTimer for updating the moving time bar
        self.time_bar_timer = QTimer(self)
        self.time_bar_timer.timeout.connect(self.update_time_bar) 


        ## Entering the plot parameters and titles
        # Initializing the pyqtgraph widget
        self.plot_graph = pg.PlotWidget() 
        
        # Initializing the varaible that defines the start time 
        self.start_time = None  
        
        # Set x-axis range to [0, 1600] which is more or less the duration of 
        # the task in seconds (can be changed) (might be better to display in 
        # minutes also)
        self.plot_graph.setXRange(0, 1600)  
        
        
        ## Setting the layout of the plotting widget 
        self.layout = QVBoxLayout(self) 
        self.layout.addWidget(self.plot_graph)
        
        # Setting the background of the plot to be black. Use 'w' for white
        self.plot_graph.setBackground("k") 
        
        # Setting the title of the plot 
        self.plot_graph.setTitle("Pokes vs Time", color="white", size="12px") 
        
        # Setting the font/style for the rest of the text used in the plot
        styles = {"color": "white", "font-size": "11px"} 
        
        # Setting label for y axis
        self.plot_graph.setLabel("left", "Port", **styles) 
        
        # Setting label for x axis 
        self.plot_graph.setLabel("bottom", "Time (s)", **styles) 
        self.plot_graph.addLegend()
        
        # Adding a grid background to make it easier to see where pokes are in time
        self.plot_graph.showGrid(x=True, y=True) 
        
        # Setting the range for the Y axis
        self.plot_graph.setYRange(1, 9) 
        
        # List to store timestamps
        self.timestamps = []  
        
        # List to store pokes 
        self.signal = []  
        
        # Defining the parameters for the sliding timebar 
        self.line_of_current_time_color = 0.5
        self.line_of_current_time = self.plot_graph.plot(x=[0, 0], y=[-1, 8], pen=pg.mkPen(self.line_of_current_time_color))

        # Setting up the plot to be able to start plotting
        self.line = self.plot_graph.plot(
            self.timestamps,
            self.signal,
            pen=None,
            symbol="o", # Included a separate symbol here that shows as a tiny dot under the raster to make it easier to distinguish multiple pokes in sequence
            symbolSize=1,
            symbolBrush="r",
        )

        # List to keep track of all plotted items to make it easier to clear the plot
        self.plotted_items = []

        # Connecting to signals from ArenaWidget and Worker 
        arena_widget.updateSignal.connect(self.handle_update_signal)
        arena_widget.worker.pokedportsignal.connect(self.plot_poked_port)

    def start_plot(self):
        # Activating the plot window and starting the plot timer
        self.is_active = True # Flag to initiate plotting 
        self.start_time = datetime.now()  # Setting the initial time at which plotting starts 
        self.timer.start(10)  # Start the timer to update every 10 ms 

        # Start the timer for updating the time bar when the plot starts
        self.time_bar_timer.start(50)  # Update every 50 ms

    def stop_plot(self):
        # Deactivating the plot window and stopping the timer
        self.is_active = False # Stopping the plot
        self.timer.stop()
        
        # Stop the timer for updating the time bar when the plot stops
        self.time_bar_timer.stop()
        self.clear_plot() # Using a method to reset the plot to its initial state 

    def clear_plot(self):
        """Resets the plot"""
        # Clear the plot information by clearing lists
        self.timestamps.clear()
        self.signal.clear()
        # Resetting the initial plot location to zero
        self.line.setData(x=[], y=[])

        # Clear all items on the plot
        for item in self.plotted_items:
            self.plot_graph.removeItem(item)
        self.plotted_items.clear()

        # Resetting thje timebar to zero 
        self.line_of_current_time.setData(x=[], y=[])

    
    def update_time_bar(self):
        """Controls how the timebar moves according to the timer"""
        # Using current time to approximately update timebar based on total seconds 
        if self.start_time is not None:
            current_time = datetime.now()
            approx_time_in_session = (
                current_time - self.start_time).total_seconds()

            # Updating the position of the timebar
            self.line_of_current_time_color = np.mod(
                self.line_of_current_time_color + 0.1, 2)
            self.line_of_current_time.setData(
                x=[approx_time_in_session, approx_time_in_session], y=[-1, 9],
                pen=pg.mkPen(np.abs(self.line_of_current_time_color - 1)),
            )
    
    def handle_update_signal(self, update_value):
        """Append info from other classes to lists in this class"""
        if self.is_active:
            # Append current timestamp and update value to the lists
            self.timestamps.append((datetime.now() - self.start_time).total_seconds())
            self.signal.append(update_value)
            self.update_plot()

    def plot_poked_port(self, poked_port_value, color):
        """Main function used to draw the poke items as rasters on the plot. 
        
        It is similar to the previous implementation in autopilot
        It appends the items to a list based on the position of the relative 
        time from the start of the session
        Currently it does not used the timestamps sent from the pi to plot 
        these pokes but this could be changed in the future 
        """
        if self.is_active:
            # Setting item colors to match the logic present in the worker class
            brush_color = "g" if color == "green" else "r" if color == "red" else "b" 
            
            # Converting to seconds to plot according to start time
            relative_time = (datetime.now() - self.start_time).total_seconds()  
            
            # Setting the parameters for the individual items being plotted
            item = self.plot_graph.plot(
                [relative_time],
                [poked_port_value],
                pen=None, # No connecting line between these points 
                symbol="arrow_down",  # "o" for dots # Previous implementation used this to display rasters 
                symbolSize=20,  # use 8 or lower if using dots
                symbolBrush=brush_color, # Setting brush color to change dynamically 
                symbolPen=None,
            )
            self.plotted_items.append(item) # Appending items to a list of plotted items

    def update_plot(self):
        # Update plot with timestamps and signals
        self.line.setData(x=self.timestamps, y=self.signal)

