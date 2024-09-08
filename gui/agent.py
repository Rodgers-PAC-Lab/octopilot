"""The worker handles the interaction with the Pi, but not any graphics.

"""
import zmq
import time
import random
import datetime
import logging
from ..shared.logtools import NonRepetitiveLogger
from ..shared.networking import DispatcherNetworkCommunicator

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
        self.network_communicator = DispatcherNetworkCommunicator(
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
            'alive': self.recv_alive,
            }
        
        
        ## Initializing variables and lists to store trial information 
        # Keeping track of last rewarded port
        self.last_rewarded_port = None 

        # None is how it knows no session is running
        self.current_trial = None
        
        # History
        self.poked_port_history = []
        self.reward_history = []

    def recv_alive(self, identity):
        """Log that we know the Agent is out there
        
        This is useful in the case that the Dispatcher has been restarted
        """
        self.logger.info(f'received alive from agent {identity}')        
    
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
        # Tell it to start
        # TODO: wait for acknowledgement of start
        self.network_communicator.send_start()
        
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
        