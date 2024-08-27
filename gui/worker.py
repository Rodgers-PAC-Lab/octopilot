"""The worker handles the interaction with the Pi, but not any graphics.

"""

import zmq
import time
import random
import datetime

class NetworkCommunicator(object):
    """Handles communication with the Pis"""
    def __init__(self, worker_port):
        ## Set up ZMQ
        # Setting up a ZMQ socket to send and receive information about 
        # poked ports 
        # (the DEALER socket on the Pi initiates the connection and then 
        # the ROUTER 
        # manages the message queue from different dealers and sends 
        # acknowledgements)
        self.context = zmq.Context()
        self.zmq_socket = self.context.socket(zmq.ROUTER)
        
        # Making it bind to the port used for sending poke related information
        self.zmq_socket.bind(f"tcp://*{worker_port}")

        # Set of identities of all pis connected to that instance of ther GUI 
        self.connected_pis = set() 
    
    def send_message_to_all(self, msg):
        # Sending the current reward port to all connected pis
        # Convert to bytes
        msg_bytes = bytes(msg, 'utf-8')
        
        # Send to all
        for identity in self.connected_pis:
            identity_bytes = bytes(identity, 'utf-8')
            self.zmq_socket.send_multipart([identity_bytes, msg_bytes])
    
    def send_trial_parameters(self, **kwargs):
        msg = "set_trial_parameters;"
        for key, value in kwargs.items():
            # Infer dtyp
            if hasattr(value, '__len__'):
                dtyp = 'str'
            elif isinstance(value, bool):
                # Note that bool is an instance of int
                dtyp = 'bool'
            elif isinstance(value, int):
                # https://stackoverflow.com/a/48940855/1676378
                dtyp = 'int'
            else:
                dtyp = 'float'
            
            # Append
            msg += f"{key}={value}={dtyp};"
        
        self.send_message_to_all(msg)
    
    def check_for_messages(self, verbose=True):
        """Check self.zmq_socket for messages.
        
        If a message is available: return identity, messages
        Otherwise: return None
        
        """
        no_message_received = False
        try:
            # Without NOBLOCK, this will hang until a message is received
            # TODO: use Poller here?
            identity, message = self.zmq_socket.recv_multipart(
                flags=zmq.NOBLOCK)
        except zmq.error.Again:
            no_message_received = True

        # If there's no message received, there is nothing to do
        if no_message_received:
            return        
        
        # Debug print identity and message
        if verbose:
            print(f'received message {message} from identity {identity}')

        # Otherwise decode it
        # TODO: in the future support bytes
        identity_str = identity.decode('utf-8')
        message_str = message.decode('utf-8')

    
        ## If a message was received, then keep track of the identities
        # TODO: wait to start session till all Pis have connected
        if identity_str not in self.connected_pis:
            # This better be a hello message
            if not message_str.startswith('hello'):
                print(
                    f'warning: first message from new identity {identity_str} '
                    f'was not hello but rather {message_str}'
                    )
            else:
                print(f'first message from new identity {identity_str}')
            
            # Either way keep track of it
            self.connected_pis.add(identity_str)
            
            # Either way, return
            return            
        
        return identity_str, message_str

class Worker:
    """Handles task logic
    
    It handles the logic of starting sessions, stopping sessions, 
    choosing reward ports
    sending messages to the pis (about reward ports), sending acknowledgements 
    for completed trials (needs to be changed).
    The Worker class also handles tracking information regarding each 
    poke / trial and saving them to a csv file.
    
    Arguments
    ---------

    params : dict
        'worker_port': what zmq port to bind
    

    """

    def __init__(self, params):
        self.network_communicator = NetworkCommunicator(params['worker_port'])
        self.params = params
        
        ## Variables to keep track of reward related messages 
        # Take this from params
        self.ports = [f'rpi{i}' for i in range(8)]
        
        # Variable to store the timestamp of the last poke 
        self.last_poke_timestamp = None  
        
        # Keeping track of the current reward port
        self.reward_port = None 
        
        # Keeping track of last rewarded port
        self.last_rewarded_port = None 


        ## Set up port labels and indices
        # Creating a dictionary that takes the label of each port and matches it to
        # the index on the GUI (used for reordering)
        self.ports = self.params['ports']
        
        # Refer to documentation when variables were initialized 
        self.label_to_index = {port['label']: port['index'] for port in self.ports} 
        self.index_to_label = {port['index']: port['label'] for port in self.ports}
        
        # Setting an index of remapped ports (so that colors can be changed accordign to label)
        self.index = self.label_to_index.get(str(self.reward_port)) 
        
        
        ## Initializing variables and lists to store trial information 
        # None is how it knows no session is running
        self.current_trial = None
    
    def start_session(self, verbose=True):
        """Start a session
        
        First we store the initial timestamp where the session was started in a 
        variable. This used with the poketimes sent by the pi to calculate the 
        time at which the pokes occured
        
        Flow
        * Sets self.initial_time to now
        * Resets self.timestamps and self.reward_ports to empty list
        * Chooses a reward_port using self.choose
        * Tell every pi which port is rewarded
        * Sets self.ports, selef.label_to_index, self.index_to_label
        * Sets color of nosepoke_circles to green
        * Starts self.timer and connects it to self.update_Pi
        """
        
        ## Set the initial_time to now
        self.session_start_time = datetime.datetime.now() 
        print(f'Starting session at {self.session_start_time}')
        
        
        ## Resetting sequences when a new session is started 
        self.reward_timestamps = []
        self.poke_timestamps = []
        self.prev_choice = None
        
        
        ## Start the first trial
        self.current_trial = 0
        self.start_trial()

    def start_trial(self, verbose=True):
        ## Choose and broadcast reward_port
        # Setting up a new set of possible choices after omitting 
        # the previously rewarded port
        poss_choices = [
            choice for choice in self.ports if choice != self.prev_choice] 
        
        # Randomly choosing within the new set of possible choices
        new_choice = 'rpi03' #random.choice(poss_choices) 
        
        # Updating the previous choice that was made so the next choice 
        # can omit it 
        self.prev_choice = new_choice          
        
        # Send start to each Pi
        self.network_communicator.send_trial_parameters(
            rewarded_port=new_choice,
            left_silenced=False,
            left_amplitude=0.0001,
            right_silenced=True,
            )

    def stop_session(self):
        """Stop the session
        
        Called by QMetaObject.invokeMethod in arena_widget.stop_sequence
        
        Flow
        * Stops self.timer and disconnects it from self.update_Pi
        * Clears recorded data
        """
     
        """Send a stop message to the pi"""
        # Send a stop message to each pi
        self.network_communicator.send_to_all('stop')
    
    def main_loop(self, verbose=True):
        """Main loop of Worker
        


        """
        while True:
            try:
                # Check for messages
                self.check_and_handle_messages()
                
                # Start a session if needed
                # TODO: this should be activated by a button instead
                if self.current_trial is None:
                    if len(self.network_communicator.connected_pis) >= 1:
                        self.start_session()
                
                time.sleep(0.1)
                
            except KeyboardInterrupt:
                print('shutting down')
                break
    
    def check_and_handle_messages(self, verbose=True):
        # Log current time (before checking)
        dt_now = datetime.datetime.now()
        
        
        ## Check for any messages from the Pis
        received_message = self.network_communicator.check_for_messages()
        
        # Handle whatever message it was
        if received_message is not None:
            identity_str, message_str = received_message
        
            if message_str.startswith('poke'):
                # A poke was received
                self.handle_poke_message(message_str, identity_str, dt_now)

            elif message_str.startswith('reward'):
                # A reward was delivered
                # Log it
                self.reward_times.append(dt_now)
                
                # Start a new trial
                self.start_trial()

            elif message_str.startswith('sound'):
                # A sound was played
                # Log it
                self.sound_times.append(dt_now)

            elif message_str.startswith('alive'):
                # Keep alive
                # Log it
                self.log_alive(identity, dt_now)

    def handle_poke_message(self, message_str, identity, elapsed_time):
        ## Converting message string to int 
        poked_port = int(message_str) 


        ## Check if the poked port is the same as the last rewarded port
        if poked_port == self.last_rewarded_port:
            # If it is, do nothing and return
            return
        
        
        ## Get index and icon
        # For any label in the list of port labels, correlate it to the 
        # index of the port in the visual arrangement in the widget 
        poked_port_index = self.label_to_index.get(message_str)
        poked_port_icon = self.nosepoke_circles[poked_port_index]

        
        ## Store results
        # Appending the poked port to a sequence that contains 
        # all pokes during a session
        self.poked_port_numbers.append(poked_port)
        
        # Can be commented out to declutter terminal
        print_out("Sequence:", self.poked_port_numbers)
        self.last_pi_received = identity

        # Appending the current reward port to save to csv 
        self.reward_ports.append(self.reward_port)
        
        # Used to update RCP calculation
        self.update_unique_ports()

        
        ## Take different actions depending on the type of poke
        if poked_port == self.reward_port:
            # This was the rewarded port
            # This is a correct trial if pokes == 0, otherwise incorrect
            if self.trials == 0:
                # This is a correct trial
                color = "green"

                # Updating count for correct trials
                self.current_correct_trials += 1 
                
                # Updating Fraction Correct
                self.current_fraction_correct = (
                    self.current_correct_trials / self.current_completed_trials)

            else:
                # This is an incorrect trial
                color = "blue"

            # Updating the number of completed trials in the session 
            self.current_completed_trials += 1 
            
            
            ## Sending an acknowledgement to the Pis when the reward port is poked
            for identity in self.identities:
                self.zmq_socket.send_multipart([
                    identity, 
                    bytes(f"Reward Poke Completed: {self.reward_port}", 
                    'utf-8]')])
            
            # Storing the completed reward port to make sure the next 
            # choice is not at the same port
            self.last_rewarded_port = self.reward_port 
            self.reward_port = self.choose() 
            
            # Resetting the number of pokes that have happened in the trial
            self.trials = 0 
            
            # Printing reward port
            print_out(f"Reward Port: {self.reward_port}")
            
            
            ## Start a new trial
            # When a new trial is started reset color of all 
            # non-reward ports to gray and set new reward port to green
            for index, Pi in enumerate(self.nosepoke_circles):
                # This might be a hack that doesnt work for some boxes 
                # (needs to be changed)
                if index + 1 == self.reward_port: 
                    Pi.set_color("green")
                else:
                    Pi.set_color("gray")

            
            ## Sending the reward port to all connected Pis after a trial is completed
            for identity in self.identities:
                self.zmq_socket.send_multipart([
                identity, bytes(f"Reward Port: {self.reward_port}", 'utf-8')])

        else:
            # This was an unrewarded poke
            color = "red" 
            self.trials += 1


        ## Emit signal
        # Sending information regarding poke and outcome of poke to Pi Widget
        self.pokedportsignal.emit(poked_port, color)


        ## Updating number of pokes in the session 
        self.current_poke += 1 
        
        ## Setting the color of the port on the Pi Widget
        poked_port_icon.set_color(color)

        
        ## Appending all the information at the time of a particular 
        # poke to their respective lists
        self.pokes.append(self.current_poke)
        self.timestamps.append(elapsed_time)
        self.amplitudes.append(self.current_amplitude)
        self.target_rates.append(self.current_target_rate)
        self.target_temporal_log_stds.append(self.current_target_temporal_log_std)
        self.center_freqs.append(self.current_center_freq)
        self.completed_trials.append(self.current_completed_trials)
        self.correct_trials.append(self.current_correct_trials)
        self.fc.append(self.current_fraction_correct)

    def save_results_to_csv(self):
        """Writes data to CSV"""
        # TODO: remove these globals
        global current_task, current_time
        
        # Specifying the directory where you want to save the CSV files
        save_directory = self.params['save_directory']
        
        # Generating filename based on current_task and current date/time
        #filename = f"{current_task}_{current_time}_saved.csv"
        filename = 'saved.csv'
        
        # Saving the results to a CSV file
        #with open(f"{save_directory}/{filename}", 'w', newline='') as csvfile:
        with open("filename", 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Writing the header row for the CSV file with parameters to be saved as the columns
            writer.writerow([
                "No. of Pokes", "Poke Timestamp (seconds)", "Port Visited", 
                "Current Reward Port", "No. of Trials", "No. of Correct Trials", 
                "Fraction Correct", "Amplitude", "Rate", "Irregularity", 
                "Center Frequency"])
           
            # Assigning the values at each individual poke to the columns in the CSV file
            for poke, timestamp, poked_port, reward_port, completed_trial, correct_trial, fc, amplitude, target_rate, target_temporal_log_std, center_freq in zip(
                self.pokes, self.timestamps, self.poked_port_numbers, self.reward_ports, self.completed_trials, self.correct_trials, self.fc, self.amplitudes, self.target_rates, self.target_temporal_log_stds, self.center_freqs):
                writer.writerow([poke, timestamp, poked_port, reward_port, completed_trial, correct_trial, fc, amplitude, target_rate, target_temporal_log_std, center_freq])

        print_out(f"Results saved to logs")
    
    
