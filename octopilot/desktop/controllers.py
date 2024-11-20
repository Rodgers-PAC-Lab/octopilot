"""The Dispatcher handles the interaction with the Agent on each Pi.

"""
import os
import time
import datetime
import logging
import io
import threading
import pandas
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
        
        # Timer for ITI
        self.timer_inter_trial_interval = None

        
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

        
        ## Parse task_params
        # Pop out the trial duration, if present
        # Pop because TrialParameterChooser can't parse this one
        if 'trial_duration' in task_params:
            self.trial_duration = task_params.pop('trial_duration')
        else:
            self.trial_duration = None
        
        # Same with ITI
        if 'inter_trial_interval' in task_params:
            self.inter_trial_interval = task_params.pop('inter_trial_interval')
        else:
            # Set default
            # It's best if this is long enough that the Pis can be informed
            # and there's no leftover sounds from the previous trial
            self.inter_trial_interval = 5
        
        # Use task_params to set TrialParameterChooser
        self.trial_parameter_chooser = (
            trial_chooser.TrialParameterChooser.from_task_params(
            port_names=self.port_names,
            task_params=task_params,
            ))
        
        
        ## Write out header rows of log files
        self._log_trial_header_row()
        self._log_poke_header_row()
        self._log_sound_header_row()
        
        # This one writes its own header row
        self._log_sound_plan_header_row_written = False
        

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
            'flash': self.handle_flash,
            'sound': self.handle_sound,
            'sound_plan': self.handle_sound_plan,
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

        # Start time
        self.trial_start_time = None
        
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
        #~ self.logger.info(
            #~ f'received alive from agent {identity}')# at {datetime.datetime.now()}')        
        
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
        alive_interval = 3
        self.alive_timer = RepeatedTimer(
            alive_interval, self.send_alive_request)

    def start_trial(self):
        ## Choose and broadcast reward_port
        # Choose trial parameters
        self.goal_port, self.trial_parameters, self.port_parameters = (
            self.trial_parameter_chooser.choose(self.previously_rewarded_port)
            )

        # Set start time as now (note that Pi will not receive the message 
        # until a bit later)
        self.trial_start_time = datetime.datetime.now()

        # Set up new trial index
        if self.current_trial is None:
            self.current_trial = 0
        else:
            self.current_trial += 1

        # Add trial number to trial_parameters, so that the Pi can use
        # this to label the pokes that come back
        self.trial_parameters['trial_number'] = self.current_trial

        # Update which ports have been poked
        self.ports_poked_this_trial = set()
        
        # Log
        self.logger.info(
            f'starting trial {self.current_trial}; '
            f'start time={self.trial_start_time}; '
            f'goal port={self.goal_port}; '
            f'trial parameters=:\n{self.trial_parameters}; '
            f'port_parameters=:\n{self.port_parameters}'
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
                # TODO: fix this, target_rate is likely specified in 
                # trial_parameters and also in port_parameters, so it will
                # be sent as 'target_rate', 'left_target_rate', and
                # 'right_target_rate'. This first is unnecessary but it will
                # also be ignored.
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
        
        # Optionally start a timer to advance the trial
        if self.trial_duration is not None:
            self.timer_advance_trial = threading.Timer(
                self.trial_duration, self.timed_advance_trial)
            self.timer_advance_trial.start()
        else:
            self.timer_advance_trial = None

    def stop_session(self):
        """Stop the session
        
        Called by QMetaObject.invokeMethod in arena_widget.stop_sequence
        
        Flow
        * Stops self.timer and disconnects it from self.update_Pi
        * Clears recorded data
        """
     
        """Send a stop message to the pi"""
        ## Stop the timers
        # Alive timer
        if self.alive_timer is None:
            self.logger.error('stopping session but no alive timer')
        else:
            # Syntax is different becasue this is a repeating timer
            self.alive_timer.stop()
        
        # Advance trial timer
        if self.timer_advance_trial is not None:
            self.timer_advance_trial.cancel()
        
        # Inter trial interval timer
        if self.timer_inter_trial_interval is not None:
            self.timer_inter_trial_interval.cancel()
        
        
        ## Send a stop message to each pi
        self.network_communicator.send_message_to_all('stop')

        
        ## Reset history when a new session is started 
        self.reset_history()    

        # Flag that it has started
        self.session_is_running = False
        
        
        ## Log
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
    
    def handle_flash(self, trial_number, identity, flash_time):
        """Store the flash time"""
        self._log_flash(trial_number, identity, flash_time)
    
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
        self._log_poke(trial_number, poke_time, identity, port_name, reward=False)

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
        self._log_poke(trial_number, poke_time, identity, port_name, reward=True)

        # Log the trial
        self._log_trial(poke_time)
        
        # Optionally start a timer to advance the trial
        if self.inter_trial_interval is not None:
            # Silence the sounds
            self.network_communicator.send_message_to_all('silence')
            
            # Create a timer that will call self.start_trial() after
            # self.inter_trial_interval seconds
            self.timer_inter_trial_interval = threading.Timer(
                self.inter_trial_interval, self.start_trial)
            self.timer_inter_trial_interval.start()
        else:
            # Just start trial immediately
            self.start_trial()

    def timed_advance_trial(self):
        """Advance trial without reward
        
        Typically this is called by a timer during the passive task. The
        trial is logged and the next one is started.
        """
        # Log that no reward was given
        self.previously_rewarded_port = None

        # Log the trial
        pseudo_reward_time = datetime.datetime.now().isoformat()
        self._log_trial(pseudo_reward_time)

        # Optionally start a timer to advance the trial
        self.logger.info('ITI is {self.inter_trial_interval}')
        if self.inter_trial_interval is not None:
            # Create a timer that will call self.start_trial() after
            # self.inter_trial_interval seconds
            self.timer_inter_trial_interval = threading.Timer(
                self.inter_trial_interval, self.start_trial)
            self.timer_inter_trial_interval.start()
        else:
            # Just start trial immediately
            self.start_trial()        

    def handle_sound(self, trial_number, identity, data_left, data_right, 
        data_hash, last_frame_time, frames_since_cycle_start, dt):
        """Called whenever a 'sound' message is received
        
        All of these parameters are logged by self._log_sound
        """
        # Log the sound
        self._log_sound(
            trial_number, identity, data_left, data_right, 
            data_hash, last_frame_time, frames_since_cycle_start, dt)

    def handle_sound_plan(self, trial_number, identity, sound_plan):
        """Called whenever a 'sound_plan' message is received
        
        All of these parameters are logged by self._log_sound_plan
        """
        # Log the sound
        df = pandas.read_table(io.StringIO(sound_plan), sep=',')
        
        # Return if empty
        if len(df) == 0:
            return
        
        # Log
        self.logger.info(f"received sound plan:\n{df}")
        
        # Add trial number and identity
        df['trial_number'] = trial_number
        df['identity'] = identity
        
        # Log
        self._log_sound_plan(df)
    
    def handle_goodbye(self, identity):
        self.logger.info(f'goodbye received from: {identity}')
        
        # remove from connected
        self.network_communicator.remove_identity_from_connected(identity)
        
        # TODO: stop the session if we've lost quorum
        if self.session_is_running and not self.network_communicator.check_if_all_pis_connected():
            self.logger.error('session stopped due to early goodbye')
            self.stop_session()
    
    def _log_trial_header_row(self):
        """Write the header row of trials.csv
        
        This is called once, at the beginning of the session, after
        self.trial_parameter_chooser is set but before any trials have run.
        
        The parameters will be taken from self.trial_parameter_chooser, and 
        then 'trial_number', start_time', 'goal_port', and 'reward_time' are
        added. The ordering matches that in self._log_trial
        """
        # The trial_parameters returned by this object are the keys of this
        # dict, plus also 'trial_number'
        param_names = list(
            self.trial_parameter_chooser.param2possible_values.keys())
        
        # Order as follows: sort the param_names, prepend and postpend a few
        # that are not contained within param_names
        param_names = (
            ['trial_number', 'start_time', 'goal_port'] + 
            sorted(param_names) + 
            ['reward_time']
            )
        
        # Write these as the column names
        with open(os.path.join(self.sandbox_path, 'trials.csv'), 'a') as fi:
            fi.write(','.join(param_names) + '\n')        
    
    def _log_trial(self, reward_time):
        """Log the results of a trial
        
        This writes out all of the values in self.trial_parameters, and then
        adds `reward_time` at the end. The values will be comma-separated
        and written to trials.csv in the sandbox path.
        
        Arguments
        ---------
        reward_time : datetime
            The time that the reward was delivered on this trial
        
        """
        # This ordering must patch _log_trial_header_row
        
        # First pop trial_number
        trial_number = self.trial_parameters.pop('trial_number')
        
        # Begin with these hardcoded ones
        str_to_log = f'{trial_number},{self.trial_start_time},{self.goal_port},'
        
        # Add trial_parameters in alphabetical order
        for key in sorted(self.trial_parameters.keys()):
            str_to_log += str(self.trial_parameters[key]) + ','
        
        # Add trial_number back to trial_parameters, in case anything depends
        # on it
        self.trial_parameters['trial_number'] = trial_number
        
        # End with reward_time
        str_to_log += str(reward_time)
        
        with open(os.path.join(self.sandbox_path, 'trials.csv'), 'a') as fi:
            fi.write(str_to_log + '\n')
    
    def _log_poke_header_row(self):
        """Write out the header row of pokes.csv
        
        Currently this is hard-coded as poke_time, trial_number, rpi,
        poked_port, and rewarded
        
        """
        with open(os.path.join(self.sandbox_path, 'pokes.csv'), 'a') as fi:
            fi.write('poke_time,trial_number,rpi,poked_port,rewarded\n')
        
    def _log_poke(self, trial_number, poke_time, identity, poked_port, reward):
        """Record that a poke occurred"""
        with open(os.path.join(self.sandbox_path, 'pokes.csv'), 'a') as fi:
            fi.write(f'{poke_time},{trial_number},{identity},{poked_port},{reward}\n')

    def _log_flash_header_row(self):
        """Write out the header row of flashes.csv
        
        Currently this is hard-coded
        """
        with open(os.path.join(self.sandbox_path, 'flashes.csv'), 'a') as fi:
            fi.write('trial_number,rpi,flash_time\n')
        
    def _log_flash(self, trial_number, identity, flash_time):
        """Record that a flash occurred"""
        with open(os.path.join(self.sandbox_path, 'flashes.csv'), 'a') as fi:
            fi.write(f'{trial_number},{identity},{flash_time}\n')

    def _log_sound_header_row(self):
        """Write out the header row of pokes.csv
        
        Currently this is hard-coded as poke_time, trial_number, rpi,
        poked_port, and rewarded
        
        """
        with open(os.path.join(self.sandbox_path, 'sounds.csv'), 'a') as fi:
            fi.write(
                'sound_time,trial_number,rpi,data_left,data_right,'
                'data_hash,last_frame_time,frames_since_cycle_start\n')
    
    def _log_sound(self, trial_number, identity, data_left, data_right,
        data_hash, last_frame_time, frames_since_cycle_start, dt):
        """Record that a sound was played"""
        with open(os.path.join(self.sandbox_path, 'sounds.csv'), 'a') as fi:
            fi.write(
                f'{dt},{trial_number},{identity},{data_left},'
                f'{data_right},{data_hash},{last_frame_time},'
                f'{frames_since_cycle_start}\n')

    def _log_sound_plan(self, sound_plan):
        """Record the sound plan"""
        # This function writes its own header the first time
        if not self._log_sound_plan_header_row_written:
            # Convert to csv with header
            txt = sound_plan.to_csv(index=False)
            
            # Flag
            self._log_sound_plan_header_row_written = True
        else:
            # Convert to csv without header
            txt = sound_plan.to_csv(index=False, header=False)
        
        # Write out
        with open(os.path.join(self.sandbox_path, 'sound_plans.csv'), 'a') as fi:
            fi.write(txt)
