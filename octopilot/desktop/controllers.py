"""The Dispatcher handles the interaction with the Agent on each Pi.

"""
import os
import time
import datetime
import logging
from ..shared.misc import RepeatedTimer
from ..shared.logtools import NonRepetitiveLogger
from ..shared.networking import DispatcherNetworkCommunicator
from . import pi_marshaller
from . import trial_chooser

class Dispatcher:
    """Handles task logic
    
    It handles the logic of starting sessions, stopping sessions, 
    choosing reward ports
    sending messages to the pis (about reward ports), sending acknowledgements 
    for completed trials (needs to be changed).
    The Worker class also handles tracking information regarding each 
    poke / trial and saving them to a csv file.
    
    """

    def __init__(self, box_params, task_params, mouse_params, sandbox_path):
        """Initialize a new worker
        
        Arguments
        ---------
        box_params : dict, parameters of the box
        task_params : dict, parameters of the task
        mouse_params : dict, parameters of the mouse
        sandbox_path : path to where files should be stored
        
        Instance variables
        ------------------
        ports : list of port names (e.g., 'rpi27_L'
        port positions: list of port angular positions (e.g., 90 for East)
        pi_ip_addresses: list of Pi IP addresses
        pi_names: list of Pi names (e.g., 'rpi27')
        
        The length of self.port_names and self.port_positions is double that
        of self.pi_names and self.pi_ip_addresses, because each Pi has two 
        ports.
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
        self.session_start_time = None
        self.session_name = None
        
        
        ## Store
        self.box_params = box_params
        self.task_params = task_params
        self.mouse_params = mouse_params
        self.sandbox_path = sandbox_path

        
        ## Extract the port names, pi names, and ip addresses from box_params
        self.port_names = []
        self.port_positions = []
        self.pi_names = []
        self.pi_ip_addresses = []
        for pi in box_params['connected_pis']:
            # Name and position of each port
            self.port_names.append(pi['left_port_name'])
            self.port_names.append(pi['right_port_name'])
            self.port_positions.append(pi['left_port_position'])
            self.port_positions.append(pi['right_port_position'])
            
            # Name and IP address of each Pi
            self.pi_ip_addresses.append(pi['ip'])
            self.pi_names.append(pi['name'])

        # Initialize trial history (requires self.ports)
        self.reset_history()

        
        ## Use task_params to set TrialParameterChooser
        self.trial_parameter_chooser = (
            trial_chooser.TrialParameterChooser.from_task_params(
            port_names=self.port_names,
            task_params=task_params,
            ))


        ## Initialize network communicator and tell it what pis to expect
        self.network_communicator = DispatcherNetworkCommunicator(
            pi_names=self.pi_names,
            zmq_port=box_params['zmq_port'],
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
        
        
        ## Start the Agents
        self.marshaller = pi_marshaller.PiMarshaller(
            agent_names=self.pi_names,
            ip_addresses=self.pi_ip_addresses,
            sandbox_path=self.sandbox_path,
            )
        self.marshaller.start()

    def reset_history(self):
        """Set all history variables to defaults
        
        This happens on init and on every stop_session
        This is how you can tell no session is running
        """
        # Identity of last_rewarded_port (to avoid repeats)
        self.previously_rewarded_port = None 
        self.goal_port = None

        # Trial index (None if not running)
        self.current_trial = None
        
        # Keep track of which ports have been poked on this trial
        self.ports_poked_this_trial = set()
        
        # History (dict by port)
        self.history_of_pokes = {}
        self.history_of_rewarded_correct_pokes = {}
        self.history_of_rewarded_incorrect_pokes = {}
        for port in self.port_names:
            self.history_of_pokes[port] = []
            self.history_of_rewarded_correct_pokes[port] = []
            self.history_of_rewarded_incorrect_pokes[port] = []
        
        # History (simple lists)
        self.history_of_ports_poked_per_trial = []
    
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
        # Do not start if all pis not connected
        if not self.network_communicator.check_if_all_pis_connected():
            self.logger.warning(
                'ignoring start_session because not all pis connected')
            return
        
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
        alive_interval = 0.03
        self.alive_timer = RepeatedTimer(
            alive_interval, self.send_alive_request)

    def start_trial(self):
        ## Choose and broadcast reward_port
        # Choose trial parameters
        self.goal_port, self.trial_parameters, self.port_parameters = (
            self.trial_parameter_chooser.choose(self.previously_rewarded_port)
            )

        # Set up new trial index
        if self.current_trial is None:
            self.current_trial = 0
        else:
            self.current_trial += 1

        # Add trial number to trial_parameters
        # TODO: get Pi to store this with each poke
        self.trial_parameters['trial_number'] = self.current_trial

        # Update which ports have been poked
        self.ports_poked_this_trial = set()
        
        # Log
        self.logger.info(
            f'starting trial {self.current_trial}; '
            f'goal port {self.goal_port}; '
            f'trial parameters\n{self.trial_parameters}; '
            f'port_parameters:\n{self.port_parameters}'
            )
        
        # Send the parameters to each pi
        for pi_name in self.pi_names:
            # Make a copy
            pi_params = self.trial_parameters.copy()
            
            # Add the parameters that can vary by port 
            # from port_parameters to pi_params
            for side in ['left', 'right']:
                # Get port name (to index port_parameters)
                if side == 'left':
                    port_name = pi_name + '_L'
                else:
                    port_name = pi_name + '_R'
            
                # The parameters that can vary by port
                pi_specific_params = [
                    'target_rate', 'distracter_rate', 'reward']
                
                # Iterate over pi_specific_params
                for pi_specific_param in pi_specific_params:
                    # Add it only if it was specified
                    if pi_specific_param in self.port_parameters.columns:
                        # Add it, keyed by the side
                        pi_params[f'{side}_{pi_specific_param}'] = (
                            self.port_parameters.loc[port_name, pi_specific_param])
            
            # Send start to each Pi
            self.network_communicator.send_trial_parameters_to_pi(
                pi_name, **pi_params)

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
        
        # Send a stop message to each pi
        self.network_communicator.send_message_to_all('stop')

        # Reset history when a new session is started 
        self.reset_history()    

        # Flag that it has started
        self.session_is_running = False
        

        self.logger.info('done with stop_session')

        # We want to be able to process the final goodbye so commenting this 
        # out. But what if it keeps sending poke messages?
        #~ self.network_communicator.command2method = {}

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
        """Called by timer_dispatcher in MainWindow"""
        # Check for messages
        self.network_communicator.check_for_messages()
        
        # Print status if not all connected
        if not self.network_communicator.check_if_all_pis_connected():
            self.logger.info(
                'waiting for {} to connect; only {} connected'.format(
                ', '.join(self.network_communicator.pi_names),
                ', '.join(self.network_communicator.connected_agents),
            ))
        
        # TODO: test if "start_next_trial" datetime flag set
        
        # Check if procs are running
        for agent, proc in self.marshaller.agent2proc.items():
            proc.poll()
            if proc.returncode is not None:
                self.logger.warning(f'ssh proc for {agent} is not running')
        
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
                        ', '.join(self.network_communicator.pi_names),
                        ', '.join(self.network_communicator.connected_agents),
                    ))
                    time.sleep(.2)
            
        except KeyboardInterrupt:
            self.logger.info('shutting down')
        
        finally:
            self.stop_session()
    
    def handle_poke(self, trial_number, identity, port_name, poke_time):
        ## Store results
        # Keep track of what ports have been poked on this trial
        # handle_reward is always the last thing that is sent, so we can 
        # assume that the trial hasn't incremented yet
        self.ports_poked_this_trial.add(port_name)

        # Compute time in seconds from start of session
        poke_time_sec = (
            datetime.datetime.fromisoformat(poke_time) - 
            self.session_start_time).total_seconds()
        
        # Store
        self.history_of_pokes[port_name].append(poke_time_sec)
        
        # Log
        self.log_poke(trial_number, poke_time, identity, port_name, reward=False)

    def handle_reward(self, trial_number, identity, port_name, poke_time):
        # TODO: store the raw datetime in the csv
        # Store the time in seconds on this port
        
        # Compute time in seconds from start of session
        poke_time_sec = (
            datetime.datetime.fromisoformat(poke_time) - 
            self.session_start_time).total_seconds()

        # Error check
        if port_name not in self.ports_poked_this_trial:
            self.logger.error(
                f"reward delivered to {port_name} but it hasn't been poked yet")
        
        # Identify which ports have been poked on this trial, not including
        # the previously rewarded port, and not including the port that was
        # just poked
        not_including_current = (self.ports_poked_this_trial - 
            set([port_name, self.previously_rewarded_port]))
        
        # Store according to whether this was correct or incorrect
        if len(not_including_current) == 0:
            # This was a correct trial
            self.history_of_rewarded_correct_pokes[port_name].append(
                poke_time_sec)
        else:
            # This was an incorrect trial
            self.history_of_rewarded_incorrect_pokes[port_name].append(
                poke_time_sec)
        
        # Either way record the ports poked per trial
        # This will be 1 if the trial was correct
        self.history_of_ports_poked_per_trial.append(
            len(not_including_current) + 1)

        # Save the rewarded port as previously_rewarded_port
        self.previously_rewarded_port = port_name

        # Log the poke
        self.log_poke(trial_number, poke_time, identity, port_name, reward=True)

        # Log the trial
        self.log_trial(poke_time)
        
        # Start a new trial
        self.start_trial()

    def handle_sound(self):
        pass
    
    def handle_goodbye(self, identity):
        self.logger.info(f'goodbye received from: {identity}')
        
        # remove from connected
        self.network_communicator.remove_identity_from_connected(identity)
        
        # TODO: stop the session if we've lost quorum
        if self.session_is_running and not self.network_communicator.check_if_all_pis_connected():
            self.logger.error('session stopped due to early goodbye')
            self.stop_session()
    
    def log_trial(self, reward_time):
        # store in alphabetical order for consistency
        str_to_log = ''
        for key in sorted(self.trial_parameters.keys()):
            str_to_log += str(self.trial_parameters[key]) + ','
        str_to_log += str(reward_time)
        
        with open(os.path.join(self.sandbox_path, 'trials.csv'), 'a') as fi:
            fi.write(str_to_log + '\n')
    
    def log_poke(self, trial_number, poke_time, identity, poked_port, reward):
        """Record that a poke occurred"""
        with open(os.path.join(self.sandbox_path, 'pokes.csv'), 'a') as fi:
            fi.write(f'{poke_time},{trial_number},{identity},{poked_port},{reward}\n')
