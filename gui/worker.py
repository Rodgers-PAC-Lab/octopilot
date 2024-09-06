"""The worker handles the interaction with the Pi, but not any graphics.

"""

import zmq
import time
import random
import datetime
from logging_utils.logging_utils import NonRepetitiveLogger
import logging

class NetworkCommunicator(object):
    """Handles communication with the Pis"""
    def __init__(self, worker_port, expected_identities):
        """Initialize object to communicate with the Pis.
        
        Arguments
        ---------
        worker_port : str
            Taken from params['worker_port']
        expected_identies : list of str
            Each entry is the identity of a Pi
            The session can't start until all expected identities connect
        
        Flow
        ----
        * Create context and socket using zmq.ROUTER
        * Bind to tcp://*{worker_port}
        * Initialize empty self.connected_pis
        """
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
        
        # This is who we expect to connect
        self.expected_identities = expected_identities
    
        ## Init logger
        self.logger = NonRepetitiveLogger("test")
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.INFO)
    
    def check_if_all_pis_connected(self):
        """"Returns True if all pis in self.expected_identies are connected"""
        # Iterate over identies
        # Return False if any is missing
        all_connected = True
        for identity in self.expected_identities:
            if identity not in self.connected_pis:
                all_connected = False
                break
        
        return all_connected
    
    def send_message_to_all(self, msg):
        """"Send msg to all identities in self.connected_pis"""
        self.logger.info(f'sending message to all connecting pis: {msg}')
        
        # Convert to bytes
        msg_bytes = bytes(msg, 'utf-8')
        
        # Send to all
        for identity in self.connected_pis:
            identity_bytes = bytes(identity, 'utf-8')
            self.zmq_socket.send_multipart([identity_bytes, msg_bytes])
    
        self.logger.info(f'above message was sent to {self.connected_pis}')    
    
    def send_trial_parameters(self, **kwargs):
        """Encode a set_trial_parameters message and send to all Pis
        
        The message will begin with "set_trial_parameters;"
        Each keyword argument will be converted into "{key}={value}={dtyp}"
        (dtyp is inferred from value)
        
        TODO: do this with json instead
        
        Then it is sent to all Pis.
        """
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
        
        self.logger.info(msg)
        
        self.send_message_to_all(msg)
    
    def check_for_messages(self, verbose=True):
        """Check self.zmq_socket for messages.
        
        If a message is available: return identity, messages
        Otherwise: return None
        """
        ## Check for messages
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
            self.logger.debug(f'received message {message} from identity {identity}')

        
        ## Decode the message
        # TODO: in the future support bytes
        identity_str = identity.decode('utf-8')
        message_str = message.decode('utf-8')

    
        ## If a message was received, then keep track of the identities
        if identity_str not in self.connected_pis:
            # This better be a hello message
            if not message_str.startswith('hello'):
                self.logger.warn(
                    f'warning: first message from new identity {identity_str} '
                    f'was not hello but rather {message_str}'
                    )
            
            else:
                self.logger.info(f'first message from new identity {identity_str} is {message_str}')
            
            # Check whether it's expected
            if identity_str in self.expected_identities:
                # Keep track of it
                self.connected_pis.add(identity_str)
            
            else:
                self.logger.warn(
                    f'warning: {identity_str} is not in expected_identities '
                    'but it attempted to connect'
                    )

        
        ## Return identity and message
        return identity_str, message_str

class Worker:
    """Handles task logic
    
    It handles the logic of starting sessions, stopping sessions, 
    choosing reward ports
    sending messages to the pis (about reward ports), sending acknowledgements 
    for completed trials (needs to be changed).
    The Worker class also handles tracking information regarding each 
    poke / trial and saving them to a csv file.
    
    """

    def __init__(self, params):
        """Initialize a new worker
        
        Arguments
        ---------
        params : dict
            'worker_port': what zmq port to bind
            'config_port': no longer used (?)
            'save_directory'
            'pi_defaults'
            'task_configs'
            'connected_pis' : list. Each item is a dict:
                'name'
                'left_port_name' : str
                'right_port_name' : str
                'left_port_position' : float (in degrees)
                'right_port_position' : float (in degrees)
        """
        ## Init logger
        self.logger = NonRepetitiveLogger("test")
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.INFO)

        
        ## Save provided params
        self.params = params
        self.logger.info(f'Initializing worker with params: {params}')
        
        
        ## Set up port labels and indices
        # Keep track of which are actually active (mostly for debugging)
        self.expected_identities = [
            pi['name'] for pi in self.params['connected_pis']]
        
        # Creating a dictionary that takes the label of each port and matches 
        # it to the index on the GUI (used for reordering)
        self.ports = set()
        for pi in self.params['connected_pis']:
            self.ports.add(pi['left_port_name'])
            self.ports.add(pi['right_port_name'])


        ## Initialize network communicator and tell it what pis to expect
        self.network_communicator = NetworkCommunicator(
            params['worker_port'],
            expected_identities=self.expected_identities,
            )
        
        ## Initializing variables and lists to store trial information 
        # Keeping track of last rewarded port
        self.last_rewarded_port = None 

        # None is how it knows no session is running
        self.current_trial = None
    
    def check_if_running(self):
        if self.current_trial is None:
            return False
        else:
            return True
    
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
        self.logger.info(f'Starting session at {self.session_start_time}')
        
        
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
        new_choice = random.choice(poss_choices) 
        
        # Updating the previous choice that was made so the next choice 
        # can omit it 
        self.prev_choice = new_choice          
        
        # TODO: choose acoustic params here
        acoustic_params = {
            'left_silenced': False,
            'left_amplitude': 0.0001,
            'right_silenced': True,
            }
        
        self.logger.info(
            f'starting trial {self.current_trial}; '
            f'rewarded port {new_choice}; '
            f'acoustic params {acoustic_params}'
            )
        
        # Send start to each Pi
        self.network_communicator.send_trial_parameters(
            rewarded_port=new_choice,
            **acoustic_params,
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
                    if self.network_communicator.check_if_all_pis_connected():
                        self.start_session()
                    else:
                        self.logger.info(
                            'waiting for {} to connect; only {} connected'.format(
                            ', '.join(self.network_communicator.expected_identities),
                            ', '.join(self.network_communicator.connected_pis),
                            ))
                
                time.sleep(0.5)
                
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
                if not self.check_if_running():
                    self.logger.warn(
                        f'warning: received {message_str} from {identity_str}'
                        ' but session is not running')
                else:
                    # Log it
                    self.logger.info(
                        f'poke received {message_str} from {identity_str}')
                    self.poke_timestamps.append(dt_now)
                    #self.handle_poke_message(message_str, identity_str, dt_now)

            elif message_str.startswith('reward'):
                # A reward was delivered
                
                if not self.check_if_running():
                    self.logger.warn(
                        f'warning: received {message_str} from {identity_str}'
                        ' but session is not running')
                else:
                    # Log it
                    self.logger.info(
                        f'reward received {message_str} from {identity_str}')
                    self.reward_timestamps.append(dt_now)
                    
                    # Start a new trial
                    self.start_trial()

            elif message_str.startswith('sound'):
                # A sound was played
                if not self.check_if_running():
                    self.logger.warn(
                        f'warning: received {message_str} from {identity_str}'
                        ' but session is not running')
                else:
                    # Log it
                    self.logger.info(
                        f'sound played {message_str} from {identity_str}')                    
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

