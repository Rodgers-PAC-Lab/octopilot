"""The Dispatcher handles the interaction with the Agent on each Pi.

"""
import zmq
import time
import subprocess
import threading
import random
import datetime
import logging
import numpy as np
from ..shared.misc import RepeatedTimer
from ..shared.logtools import NonRepetitiveLogger
from ..shared.networking import DispatcherNetworkCommunicator

class PiMarshaller(object):
    """Connects to each Pi over SSH and starts the Agent.
    
    """
    def __init__(self, agent_names, ip_addresses, shell_script='start_cli.sh'):
        """Init a new PiMarshaller to connect to each in `ip_addresses`.
        
        agent_names : list of str
            Each entry should be the name of an Agent
        ip_addresses : list of str
            Each entry should be an IP address of a Pi
            This list should be the same length and correspond one-to-one
            with `agent_names`.
        """
        # Init logger
        self.logger = NonRepetitiveLogger("test")
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.INFO)
        
        # Save arguments
        self.agent_names = agent_names
        self.ip_addresses = ip_addresses
        self.shell_script = shell_script
    
    def start(self):
        """Open an ssh connection each Agent in self.agent_names
        
        Flow
        * For each agent:
            * A Popen is used to maintain the ssh connection in the background
            * That ssh connection is used to run `start_cli.sh` on the Pi,
              which starts the Agent
            * A thread is used to collect data from each of stdout and stderr
            * That data is also written to a logger, prepended with agent name
        """
        # This function is used only as a thread target
        def capture(buff, buff_name, agent_name, logger, output_filename):
            """Thread target: read from `buff` and write out
            
            Read lines from `buff`. Write them to `logger` and to
            `output_filename`. This is blocking so it has to happen in 
            a thread. I think these operations are all thread-safe, even
            the logger.
            
            buff : a process's stdout or stderr
                Lines of text will be read from this
            buff_name : str, like 'stdout' or 'stderr'
                Prepended to the line in the log
            agent_name : str
                Prepended to the line in the log
            logger : Logger
                Lines written to here, with agent_name and buff_name prepended
            output_filname: path
                Lines written to here
            """
            # Open output filename
            with open(output_filename, 'w') as fi:
                # Iterate through the lines in buff, with '' indicating
                # that buff has closed
                for line in iter(buff, ''):
                    # Log the line
                    # TODO: make the loglevel configurable
                    logger.debug(
                        f'  from {agent_name} {buff_name}: {line.strip()}')
                    
                    # Write the line to the file
                    fi.write(line)  
        
        # Iterate over agents
        for agent_name, ip_address in zip(self.agent_names, self.ip_addresses):
            self.logger.info(
                f'starting ssh proc to {agent_name} at {ip_address}')
            # Create the ssh process
            # https://stackoverflow.com/questions/76665310/python-run-subprocess-popen-with-timeout-and-get-stdout-at-runtime
            # -tt is used to make it interactive, and to ensure it closes
            #    the remote process when the ssh ends.
            # PIPE is used to collect data in threads
            # text, universal_newlines ensures we get text back
            proc = subprocess.Popen(
                ['ssh', '-tt', f'pi@{ip_address}', 
                'bash', '-i', self.shell_script], 
                stdin=subprocess.PIPE, 
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                universal_newlines=True,
                )
            
            # Start threads to capture output
            thread_stdout = threading.Thread(
                target=capture, 
                kwargs={
                    'buff': proc.stdout, 
                    'buff_name': 'stdout',
                    'agent_name': agent_name,
                    'logger': self.logger,
                    'output_filename': f'{agent}_stdout.output',
                    },
                )
            
            thread_stderr = threading.Thread(
                target=capture, 
                kwargs={
                    'buff': proc.stderr, 
                    'buff_name': 'stderr',
                    'agent_name': agent_name,
                    'logger': self.logger,
                    'output_filename': f'{agent}_stderr.output',
                    },
                )
            
            # Start
            thread_stdout.start()
            thread_stderr.start()      
            
            # Store
            self.agent2proc[agent_name] = proc
            self.agent2thread_stdout[agent_name] = thread_stdout
            self.agent2thread_stderr[agent_name] = thread_stderr
    
    def stop(self):
        """Close ssh proc to agent"""
        # Wait until it's had time to shut down naturally because we probably
        # just sent the stop command
        time.sleep(1)
        
        # Iterate over agents
        for agent, proc in self.agent2proc.items():
            # Poll to see if done
            # TODO: do this until returncode
            proc.poll()
            
            # Kill if needed
            if proc.returncode is None:
                self.logger.warning(
                    f"ssh proc to {agent} didn't end naturally, killing")
                
                # Kill
                proc.terminate()
                
                # Time to kill
                time.sleep(.5)
            
            # Log
            self.logger.info(
                f'proc_ssh_to_agent returncode: {proc.returncode}')

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
        
        
        ## Start the Agents
        # TODO: add IP addresses here from box_params
        self.marshaller = PiMarshaller(agent_names=self.expected_identities)

    def reset_history(self):
        """Set all history variables to defaults
        
        This happens on init and on every stop_session
        This is how you can tell no session is running
        """
        # Identity of last_rewarded_port (to avoid repeats)
        self.previously_rewarded_port = None 
        self.rewarded_port = None

        # Trial index (None if not running)
        self.current_trial = None
        
        # History (dict by port)
        self.history_of_pokes = {}
        self.history_of_rewarded_correct_pokes = {}
        self.history_of_rewarded_incorrect_pokes = {}
        for port in self.ports:
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
        # Update which ports have been poked
        self.ports_poked_this_trial = set()
        
        # Update the previously_rewarded_port
        self.previously_rewarded_port = self.rewarded_port
        
        # Setting up a new set of possible choices after omitting 
        # the previously rewarded port
        possible_rewarded_ports = [
            port for port in self.ports 
            if port != self.previously_rewarded_port] 
        
        # Randomly choosing within the new set of possible choices
        # Updating the previous choice that was made so the next choice 
        # can omit it 
        self.rewarded_port = random.choice(possible_rewarded_ports) 
        
        # Keep track of which have been poked
        self.ports_poked_this_trial = set()
        
        # Set up new trial index
        if self.current_trial is None:
            self.current_trial = 0
        else:
            self.current_trial += 1
        
        # TODO: choose acoustic params here
        # TODO: also send the current_trial number, so that the Agent
        # can assign a trial number to pokes that come back
        # TODO: actually use task_params to choose instead of hardcoding
        # TODO: send different acoustic_params to each pi
        if np.random.random() < 0.5:
            acoustic_params = {
                'left_silenced': False,
                'left_amplitude': 0.01,
                'left_center_frequency': 8000,
                'left_rate': 1,
                'left_temporal_std': .001,
                'right_silenced': True,
                }
        else:
            acoustic_params = {
                'right_silenced': False,
                'right_amplitude': 0.01,
                'right_center_frequency': 8000,
                'right_rate': 1,
                'right_temporal_std': .001,
                'left_silenced': True,
                }            
        
        self.logger.info(
            f'starting trial {self.current_trial}; '
            f'rewarded port {self.rewarded_port}; '
            f'acoustic params {acoustic_params}'
            )
        
        # Send start to each Pi
        self.network_communicator.send_trial_parameters(
            rewarded_port=self.rewarded_port,
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
        # Check for messages
        self.network_communicator.check_for_messages()
        
        # Print status if not all connected
        if not self.network_communicator.check_if_all_pis_connected():
            self.logger.info(
                'waiting for {} to connect; only {} connected'.format(
                ', '.join(self.network_communicator.expected_identities),
                ', '.join(self.network_communicator.connected_agents),
            ))
        
        # TODO: test if "start_next_trial" datetime flag set
        
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

    def handle_reward(self, identity, port_name, poke_time):
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
        