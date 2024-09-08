"""The Dispatcher handles the interaction with the Agent on each Pi.

"""
import zmq
import time
import random
import datetime
import logging
from ..shared.misc import RepeatedTimer
from ..shared.logtools import NonRepetitiveLogger
from ..shared.networking import DispatcherNetworkCommunicator

class Dispatcher:
    """Handles task logic
    
    It handles the logic of starting sessions, stopping sessions, 
    choosing reward ports
    sending messages to the pis (about reward ports), sending acknowledgements 
    for completed trials (needs to be changed).
    The Worker class also handles tracking information regarding each 
    poke / trial and saving them to a csv file.
    
    """

    def __init__(self, box_params, task_params, mouse_params):
        """Initialize a new worker
        
        Arguments
        ---------
        box_params : dict
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
        task_params : dict, parameters of the task
        mouse_params : dict, parameters of the mouse
        """
        ## Init logger
        self.logger = NonRepetitiveLogger("test")
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.INFO)

        # Log
        self.logger.info(
            'Initializing Dispatcher with the following params:\n'
            f'box_params: {box_params};\n'
            f'task_params: {task_params};\n'
            f'mouse_params: {mouse_params};\n'
            )
        

        ## Init instance variables
        self.session_is_running = False
        self.last_alive_message_received = {}
        self.alive_timer = None

        # Store parameters
        self.task_params = task_params

        
        ## Set up port labels and indices
        # Keep track of which are actually active (mostly for debugging)
        self.expected_identities = [
            pi['name'] for pi in box_params['connected_pis']]
        
        # List of the connected port names
        self.ports = []
        for pi in box_params['connected_pis']:
            self.ports.append(pi['left_port_name'])
            self.ports.append(pi['right_port_name'])

        # Initialize trial history (requires self.ports)
        self.reset_history()


        ## Initialize network communicator and tell it what pis to expect
        self.network_communicator = DispatcherNetworkCommunicator(
            box_params['worker_port'],
            expected_identities=self.expected_identities,
            )
        
        # What to do on each command
        # TODO: disconnect these handles after session is stopped
        self.network_communicator.command2method = {
            'poke': self.handle_poke,
            'reward': self.handle_reward,
            'sound': self.handle_sound,
            'goodbye': self.handle_goodbye,
            'alive': self.recv_alive,
            }

    def reset_history(self):
        """Set all history variables to defaults
        
        This happens on init and on every stop_session
        This is how you can tell no session is running
        """
        # Identity of last_rewarded_port (to avoid repeats)
        self.previously_rewarded_port = None 

        # Trial index (None if not running)
        self.current_trial = None
        
        # History
        self.poked_port_history = {}
        self.reward_history = {}
        for port in self.ports:
            self.poked_port_history[port] = []
            self.reward_history[port] = []
    
    def recv_alive(self, identity):
        """Log that we know the Agent is out there
        
        This is useful in the case that the Dispatcher has been restarted
        """
        self.logger.info(
            f'received alive from agent {identity}')# at {datetime.datetime.now()}')        
        
        # Log that this happened
        self.last_alive_message_received[identity] = datetime.datetime.now()
    
    def start_session(self, verbose=True):
        """Start a session"""
        
        # Set the initial_time to now
        self.session_start_time = datetime.datetime.now() 
        self.logger.info(f'Starting session at {self.session_start_time}')
        
        # Deal with case where the old sessions is still going
        if self.session_is_running:
            # Log
            self.logger.error('session is started but session is running')
            
            # Reset history
            self.reset_history()    
        
        # Flag that it has started
        self.session_is_running = True

        # Tell the agent to start the session
        # TODO: wait for acknowledgement of start
        self.network_communicator.send_start()
        
        # Start the first trial
        self.start_trial()

        # Set up timer to test if the Agent is still running
        self.last_alive_message_received = {}
        alive_interval = 3
        self.alive_timer = RepeatedTimer(
            alive_interval, self.send_alive_request)

    def start_trial(self):
        ## Choose and broadcast reward_port
        # Setting up a new set of possible choices after omitting 
        # the previously rewarded port
        possible_rewarded_ports = [
            port for port in self.ports if port != self.previously_rewarded_port] 
        
        # Randomly choosing within the new set of possible choices
        # Updating the previous choice that was made so the next choice 
        # can omit it 
        self.previously_rewarded_port = random.choice(possible_rewarded_ports) 
        
        # Set up new trial index
        if self.current_trial is None:
            self.current_trial = 0
        else:
            self.current_trial += 1
        
        # TODO: choose acoustic params here
        acoustic_params = {
            'left_silenced': False,
            'left_amplitude': 0.0001,
            'right_silenced': True,
            }
        
        self.logger.info(
            f'starting trial {self.current_trial}; '
            f'rewarded port {self.previously_rewarded_port}; '
            f'acoustic params {acoustic_params}'
            )
        
        # Send start to each Pi
        self.network_communicator.send_trial_parameters(
            rewarded_port=self.previously_rewarded_port,
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
        # Stop the timer
        if self.alive_timer is None:
            self.logger.error('stopping session but no alive timer')
        else:
            self.alive_timer.stop()
        
        self.network_communicator.command2method = {}
        
        # Send a stop message to each pi
        self.network_communicator.send_message_to_all('stop')

        # Reset history when a new session is started 
        self.reset_history()    

        # Flag that it has started
        self.session_is_running = True

    def send_alive_request(self):
        # Warn if it's been too long
        for identity in self.network_communicator.connected_agents:
            if identity in self.last_alive_message_received.keys():
                last_time = self.last_alive_message_received[identity]
                threshold = datetime.datetime.now() - datetime.timedelta(seconds=4)
                if last_time < threshold:
                    self.logger.error(f'no recent alive responses from {identity}')
            else:
                self.logger.warning(f'{identity} is not in last_alive_message_received')
            
            # TODO: initiate shutdown
        
        self.network_communicator.send_alive_request()

    def update(self):
        # Check for messages
        self.network_communicator.check_for_messages()
        
        # Check if we're all connected
        if self.network_communicator.check_if_all_pis_connected():
            pass

        else:
            # We're not all connnected
            self.logger.info(
                'waiting for {} to connect; only {} connected'.format(
                ', '.join(self.network_communicator.expected_identities),
                ', '.join(self.network_communicator.connected_agents),
            ))
                    
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
                        ', '.join(self.network_communicator.connected_agents),
                    ))
                    time.sleep(.2)
            
        except KeyboardInterrupt:
            self.logger.info('shutting down')
        
        finally:
            self.stop_session()
    
    def handle_poke(self, identity, port_name, poke_time):
        ## Store results
        # TODO: store the raw datetime in the csv
        # Store the time in seconds on this port
        poke_time_sec = (
            datetime.datetime.fromisoformat(poke_time) - 
            self.session_start_time).total_seconds()
        self.poked_port_history[port_name].append(poke_time_sec)

    def handle_reward(self, identity, port_name, poke_time):
        # TODO: store the raw datetime in the csv
        # Store the time in seconds on this port
        poke_time_sec = (
            datetime.datetime.fromisoformat(poke_time) - 
            self.session_start_time).total_seconds()
        self.reward_history[port_name].append(poke_time_sec)

        # Start a new trial
        self.start_trial()

    def handle_sound(self):
        pass
    
    def handle_goodbye(self, identity):
        self.logger.info(f'goodbye received from: {identity}')
        
        # remove from connected
        self.network_communicator.remove_identity_from_connected(identity)
        
        # TODO: stop the session if we've lost quorum
        if not self.network_communicator.check_if_all_pis_connected():
            self.logger.error('session stopped due to early goodbye')
            self.stop_session()
        