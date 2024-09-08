"""The worker handles the interaction with the Pi, but not any graphics.

"""
import zmq
import time
import random
import datetime
from ..logging_utils.logging_utils import NonRepetitiveLogger
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
        ## Init logger
        self.logger = NonRepetitiveLogger("test")
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.DEBUG)


        # Store provided params
        # This is who we expect to connect
        self.expected_identities = expected_identities

        # Set of identities of all pis connected to that instance of ther GUI 
        self.connected_pis = set() 
        
        # Set up the method to call on each command
        self.command2method = {}
        
        # Set up sockets
        self.init_socket(worker_port)
    
    def init_socket(self, worker_port):
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
    
    def check_for_messages(self):
        """Check self.zmq_socket for messages.
        
        If a message is available: return identity, messages
        Otherwise: return None
        """
        ## Check for messages
        message_received = True
        try:
            # Without NOBLOCK, this will hang until a message is received
            # TODO: use Poller here?
            identity, message = self.zmq_socket.recv_multipart(
                flags=zmq.NOBLOCK)
        except zmq.error.Again:
            message_received = False

        # If there's no message received, there is nothing to do
        if message_received:
            self.handle_message(identity, message)
    
    def handle_message(self, identity, message):
        """Handle a message received on poke_socket
        
        Arguments
        ---------
        msg : str
            A ';'-separated list of strings
            The first string is the "command"
            The remaining strings should be in the format {KEY}={VALUE}={DTYP}
            The method self.command2method[command] is called with a dict
            of arguments formed from the remaining strings.
        """        
        # Debug print identity and message
        self.logger.debug(f'received from {identity}: {message}')
        
        # Decode the message
        # TODO: in the future support bytes
        identity_str = identity.decode('utf-8')
        message_str = message.decode('utf-8')

        # Keep track of the identities
        if identity_str not in self.connected_pis:
            self.add_identity_to_connected(identity_str, message_str)

        # Split on semicolon
        tokens = message_str.strip().split(';')
        
        # The command is the first token
        # This will always run, but command could be ''
        command = tokens[0]
        
        # Get the params
        # This will always run, but could return {}
        msg_params = self.parse_params(tokens[1:])
        
        # Insert identity into msg_params
        msg_params['identity'] = identity_str
        
        # Find associated method
        meth = None
        try:
            meth = self.command2method[command]
        except KeyError:
            self.logger.error(
                f'unrecognized command: {command}. '
                f'I only recognize: {list(self.command2method.keys())}'
                )
        
        # Call the method
        if meth is not None:
            self.logger.debug(f'calling method {meth} with params {msg_params}')
            meth(**msg_params)

    def parse_params(self, token_l):
        """Parse `token_l` into a dict
        
        Iterates over strings in token_l, parses them as KEY=VALUE=DTYPE,
        and stores in a dict to return. Raises ValueError if unparseable.
        
        TODO: replace this with json
        
        token_l : list
            Each entry should be a str, '{KEY}={VALUE}={DTYPE}'
            where KEY is the key, VALUE is the value, and DTYPE is
            either 'int', 'float', or 'str'
        
        Returns : dict d
            d[KEY] will be VALUE of type DTYPE
        """
        # Parse each token
        params = {}
        for tok in token_l:
            # Strip
            strip_tok = tok.strip()
            split_tok = strip_tok.split('=')
            
            # Skip if empty
            if strip_tok == '':
                # This happens if the message ends with a semicolon,
                # which is fine
                continue
            
            # Error if it's not KEY=VAL=DTYP
            try:
                key, val, dtyp = split_tok
            except ValueError:
                raise ValueError('unparseable token: {}'.format(tok))
            
            # Convert value
            if dtyp == 'int':
                conv_val = int(val)
            elif dtyp == 'float':
                conv_val = float(val)
            elif dtyp == 'str':
                conv_val = val
            elif dtyp == 'bool':
                conv_val = bool(val)
            else:
                # Error if DTYP unrecognized
                raise ValueError('unrecognized dtyp: {}'.format(dtyp))
            
            # Store
            params[key] = conv_val
        
        return params
    
    def add_identity_to_connected(self, identity_str, message_str):
        # This better be a hello message
        if not message_str.startswith('hello'):
            self.logger.warn(
                f'warning: first message from new identity {identity_str} '
                f'was not hello but rather {message_str}'
                )
        
        else:
            self.logger.info(
                f'first message from new identity {identity_str} '
                f'is {message_str}')
        
        # Check whether it's expected
        if identity_str in self.expected_identities:
            # Keep track of it
            self.connected_pis.add(identity_str)
        
        else:
            self.logger.warn(
                f'warning: {identity_str} is not in expected_identities '
                'but it attempted to connect'
                )
    
    def remove_identity_from_connected(self, identity):
        if identity not in self.connected_pis:
            self.logger.error(f'{identity} said goodbye but it was not connected')
        
        self.connected_pis.remove(identity)

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
        
        # What to do on each command
        # TODO: disconnect these handles after session is stopped
        self.network_communicator.command2method = {
            'poke': self.handle_poke,
            'reward': self.handle_reward,
            'sound': self.handle_sound,
            'alive': self.handle_alive,
            'goodbye': self.handle_goodbye,
            }
        
        
        ## Initializing variables and lists to store trial information 
        # Keeping track of last rewarded port
        self.last_rewarded_port = None 

        # None is how it knows no session is running
        self.current_trial = None
        
        # History
        self.poked_port_history = []
        self.reward_history = []
    
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

    def start_trial(self):
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
        self.network_communicator.send_message_to_all('stop')
    
    def main_loop(self, verbose=True):
        """Main loop of Worker

        """
        try:
            self.logger.info('starting main_loop')
            
            while True:
                # Check for messages
                self.network_communicator.check_for_messages()
                
                # Check if we're all connected
                if self.network_communicator.check_if_all_pis_connected():
                    # Start if it needs to start
                    # TODO: this should be started by a button
                    if self.current_trial is None:
                        self.start_session()
                else:
                    # We're not all connnected
                    self.logger.info(
                        'waiting for {} to connect; only {} connected'.format(
                        ', '.join(self.network_communicator.expected_identities),
                        ', '.join(self.network_communicator.connected_pis),
                    ))
                    time.sleep(.2)
            
        except KeyboardInterrupt:
            self.logger.info('shutting down')
        
        finally:
            self.stop_session()
    
    def handle_poke(self, identity, port_name, poke_time):
        ## Store results
        # Appending the poked port to a sequence that contains 
        # all pokes during a session
        self.poked_port_history.append((port_name, poke_time))

    def handle_reward(self, identity, port_name, poke_time):
        # Appending the current reward port to save to csv 
        self.reward_history.append((port_name, poke_time))

        # Start a new trial
        self.start_trial()

    def handle_sound(self):
        pass
    
    def handle_alive(self):
        pass
    
    def handle_goodbye(self, identity):
        self.logger.info(f'goodbye received from: {identity}')
        
        # remove from connected
        self.network_communicator.remove_identity_from_connected(identity)
        
        # TODO: stop the session if we've lost quorum
        if not self.network_communicator.check_if_all_pis_connected():
            self.logger.error('session stopped due to early goodbye')
            self.stop_session()
        