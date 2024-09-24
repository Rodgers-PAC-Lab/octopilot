"""The Dispatcher handles the interaction with the Agent on each Pi.

"""
import zmq
import time
import subprocess
import threading
import random
import datetime
import logging
import pandas
import numpy as np
from ..shared.misc import RepeatedTimer
from ..shared.logtools import NonRepetitiveLogger
from ..shared.networking import DispatcherNetworkCommunicator

class PiMarshaller(object):
    """Connects to each Pi over SSH and starts the Agent.
    
    """
    def __init__(
        self, agent_names, ip_addresses, 
        shell_script='/home/pi/dev/octopilot/octopilot/pi/start_cli.sh'):
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
        self.logger.setLevel(logging.DEBUG)
        
        # Save arguments
        self.agent_names = agent_names
        self.ip_addresses = ip_addresses
        self.shell_script = shell_script
    
    def start(self):
        """Open an ssh connection each Agent in self.agent_names
        
        TODO: provide a handle that is called whenever the ssh proc closes,
        especially unexpectedly.
        
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
                for line in iter(buff.readline, ''):
                    # Log the line
                    # TODO: make the loglevel configurable
                    logger.debug(
                        f'  from {agent_name} {buff_name}: {line.strip()}')
                    
                    # Write the line to the file
                    fi.write(line)  
        
        # Iterate over agents
        self.agent2proc = {}
        self.agent2thread_stdout = {}
        self.agent2thread_stderr = {}
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
                ['ssh', '-tt', '-o', 'ConnectTimeout=2', f'pi@{ip_address}', 
                'bash', '-i', self.shell_script], 
                stdin=subprocess.PIPE, 
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                universal_newlines=True,
                )
            
            time.sleep(.1)
            proc.poll()
            if proc.returncode is not None:
                print(f'error, cannot start proc to {agent_name}')
                continue
            
            # Start threads to capture output
            thread_stdout = threading.Thread(
                target=capture, 
                kwargs={
                    'buff': proc.stdout, 
                    'buff_name': 'stdout',
                    'agent_name': agent_name,
                    'logger': self.logger,
                    'output_filename': f'{agent_name}_stdout.output',
                    },
                )
            
            thread_stderr = threading.Thread(
                target=capture, 
                kwargs={
                    'buff': proc.stderr, 
                    'buff_name': 'stderr',
                    'agent_name': agent_name,
                    'logger': self.logger,
                    'output_filename': f'{agent_name}_stderr.output',
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

class TrialParameterChooser(object):
    """Chooses the parameters of each trial.
    
    Methods
    -------
    * __init__ : Initialize with the range of parameters that are possible
        on each trial.
    * choose : Return the parameters for a single trial.
    """
    @classmethod
    def from_task_params(self, port_names, task_params):
        """Construct from the kind of data in the task json
        
        This class method is a convenience method to initialize a 
        TrialParameterChooser. For every parameter that can be ranged, it
        identifies whether it's stored as a fixed value or a range in 
        task_params. In either case it sets up the arguments for 
        TrialParameterChooser in the expected format, a dict with the keys
        min, max, and n_choices. 
        
        All other items in task_params are forwarded to TrialParameterChooser
        unchanged. Generally, task_params should specify play_targets 
        and play_distracters as True or False.
        
        Arguments
        ---------
        port_names: see __init__
        task_params : dict from load_params.load_task_params
        """
        # Identify whether these have ranges
        ranged_params = [
            'target_rate',
            'target_temporal_log_std',
            'target_center_freq',
            'target_log_amplitude',
            'target_radius',
            'distracter_rate',
            'distracter_temporal_log_std',
            'distracter_center_freq',
            'distracter_log_amplitude',
            'n_distracters',
            ]
        
        # Iterate over ranged_params and extract each
        kwargs = {}
        for param in ranged_params:
            rangeval = {}
            
            if param in task_params:
                # It's fixed at this value
                assert param + '_min' not in task_params
                assert param + '_max' not in task_params
                assert param + '_n_choices' not in task_params
                
                rangeval['min'] = task_params.pop(param)
                rangeval['max'] = rangeval['min']
                rangeval['n_choices'] = 1
            
            elif param + '_min' in task_params:
                # It's specified as a range
                assert param + '_max' in task_params
                assert param + '_n_choices' in task_params
                
                rangeval['min'] = task_params.pop(param + '_min')
                rangeval['max'] = task_params.pop(param + '_max')
                rangeval['n_choices'] = task_params.pop(param + '_n_choices')
        
            else:
                # It's not specified in task_params
                # Assign a default here
                if param == 'target_radius':
                    default_value = 0
                else:
                    #raise ValueError(f'no default value specified for {param}')
                    print (f'warning: no default value specified for {param}')
                rangeval['min'] = default_value
                rangeval['max'] = default_value
                rangeval['n_choices'] = 1
        
            # Store in kwargs
            kwargs['range_' + param] = rangeval
        
        # Transfer any remaining items in task_params to kwargs
        # This includes: play_targets, play_distracters, and reward_radius,
        # none of which are ranged
        for key, val in task_params.items():
            kwargs[key] = val
        
        # Return
        return TrialParameterChooser(port_names, **kwargs)
    
    def __init__(self,
        port_names,
        reward_radius=0,
        play_targets=False,
        play_distracters=False,
        range_target_rate=None,
        range_target_temporal_log_std=None,
        range_target_center_freq=None,
        range_target_log_amplitude=None,
        range_target_radius=None,
        range_distracter_rate=None,
        range_distracter_temporal_log_std=None,
        range_distracter_center_freq=None,
        range_distracter_log_amplitude=None,
        range_n_distracters=None,
        ):
        """Init new object that will choose trial params from specified ranges.
        
        Based on the range of parameters provided, this object will 
        set self.param2possible_values to be a dict from parameter name
        to a list of possible values. This dict will lack entries for target
        if play_targets is False, for distracters if play_distracters is False,
        and may be empty if both are False.
        
        For poketrain, set play_targets and play_distracters to False,
        and reward_radius to len(port_names) / 2 - 1 or greater.
        
        Arguments
        ---------
        port_names: list of str
            Ordered list of port names. Adjacent ports should be adjacent
            in this list, which is assumed to wrap around. The ordering 
            matters in the spatial task, and when reward_n_ports > 1.
        reward_radius : int
            The number of ports on each side of the goal that will be rewarded 
            on each trial. These will always be contiguous and centered on 
            the goal. The previously rewarded port will never be rewarded 
            and is excluded from this calculation. Set this parameter to 0 
            to reward only the goal. Set this parameter to be >=
            len(port_names) / 2 - 1 in order to reward all ports. 
        play_targets : bool
            If False, no target sounds will be played, and all arguments
            beginning with "range_target_" are ignored.
        play_distracters : bool
            If False, no distracter sounds will be played, and all arguments
            beginning with "range_distracter_" are ignored.
        
        All keyword arguments that begin with "range_" must be either None,
        or a dict with the keys 'min', 'max', and 'n_choices'. 
        * They can only be None if play_targets or play_distracters is False
        * Otherwise, the parameter specified by this range will be one of 
          the values in np.linspace(min, max, n_choices). 
        
        target_rate : rate of target sounds at goal (Hz)
        target_temporal_log_std : log(std(inter-target intervals [s]))
        target_center_freq : center freq of target sound (Hz)
        target_log_amplitude : log(amplitude of target sound)
        distracter_* : analogous to above, but for distracter
        target_radius : number of ports on each side of goal that play targets
        n_distracters : number of ports playing distracters at distracter_rate
        """
        ## Store the values that don't change with trial
        self.port_names = port_names
        self.reward_radius = reward_radius
        self.play_targets = play_targets
        self.play_distracters = play_distracters
        
        
        ## Determine what parameters need to be set on each trial
        # These are the ranged parameters
        self.param2range = {
            'target_rate': range_target_rate,
            'target_temporal_log_std': range_target_temporal_log_std,
            'target_center_freq': range_target_center_freq,
            'target_log_amplitude': range_target_log_amplitude,
            'target_radius': range_target_radius,
            'distracter_rate': range_distracter_rate,
            'distracter_temporal_log_std': range_distracter_temporal_log_std,
            'distracter_center_freq': range_distracter_center_freq,
            'distracter_log_amplitude': range_distracter_log_amplitude,
            'n_distracters': range_n_distracters,
            }
        
        # If play_target is False, remove the target ones
        if self.play_targets == False:
            self.param2range.pop('target_rate')
            self.param2range.pop('target_temporal_log_std')
            self.param2range.pop('target_center_freq')
            self.param2range.pop('target_log_amplitude')
            self.param2range.pop('target_radius')
        
        # If play_distracter is False, remove the distracter ones
        if self.play_distracters == False:
            self.param2range.pop('distracter_rate')
            self.param2range.pop('distracter_temporal_log_std')
            self.param2range.pop('distracter_center_freq')
            self.param2range.pop('distracter_log_amplitude')
            self.param2range.pop('n_distracters')        


        ## Calculate the possible values for each trial parameter
        # This is a dict from param name to a list of possible values
        self.param2possible_values = {}
        
        # Iterate over parameters
        for param_name, param_range in self.param2range.items():
            if param_range is None:
                print(f'{param_name} is None')
            
            # Shortcuts
            param_min = param_range['min']
            param_max = param_range['max']
            param_n_choices = param_range['n_choices']
            
            # Depends on how many choices
            if param_n_choices == 1:
                # If only 1, assert equal, and corresponding entry in 
                # self.stim_choosing_params is a list of length one
                assert param_min == param_max
                self.param2possible_values[param_name] = [param_min]
            
            else:
                # Otherwise, linspace between min and max                
                assert param_min < param_max
                self.param2possible_values[param_name] = np.linspace(
                    param_min, param_max, param_n_choices)
                
            # This parameter must be integer
            if param_name == 'n_distracters':
                orig = self.param2possible_values[param_name]
                casted = orig.astype(int)
                if (casted != orig).any(): 
                    raise ValueError("cannot convert n_distracters to int")
                self.param2possible_values[param_name] = casted
                
            # It should always be a list, for consistency
            self.param2possible_values[param_name] = list(
                self.param2possible_values[param_name])
    
    def choose(self, previously_rewarded_port):
        """Return parameters for one trial
        
        The port named `previously_rewarded_port` will never be selected
        as the goal and will never be rewarded. If this argument is None or
        is not in self.port_names, then it has no effect.
        
        Some parameters are port-specific, such as whether they are rewarded
        and whether they play distracters. Others apply to all ports, such
        as target_amplitude. 
        
        Some parameters will be left unset
        * All target-related parameters are unset if not self.play_targets
        * All distracter-related params are unset if not self.play_distracters
        
        Returns: goal_port, trial_parameters, port_parameters
            goal_port : str, the name of the goal port
            trial_parameters : dict, param name to param value
                The same length as self.param2possible_values, so it will 
                be missing params that are irrelevant (e.g., no params relating
                to targets if not self.play_targets)
            port_parameters : DataFrame, with the following columns
                'port' : equal to self.port_names
                'goal' : True for the single goal port, False everywhere else
                    The goal port will never be equal to previously_rewarded_port
                'reward' : True for rewarded ports, False everywhere else
                'absdist' : int, absolute distance from goal
                'target_rate' : rate of targets
                    This column is missing if not self.play_targets
                'distracter_rate' : rate of distracters
                    This column is missing if not self.play_distracters
            
            Note that 'target_rate' appears both as a column in port_parameters
            and also a value in trial_parameters. 
            trial_parameters['target_rate'] sets the maximum value in 
            port_parameters['target_rate']
        """
        ## Choose the goal
        # Exclude previously rewarded port
        choose_from = [
            port for port in self.port_names
            if port != previously_rewarded_port]
        
        # Choose goal port randomly from those
        goal_port = random.choice(choose_from)
        

        ## Generate port_params, a DataFrame of parameters for each port
        # Use the ordered list of port names
        port_params = pandas.Series(
            self.port_names, name='port').to_frame()
        
        # Identify the row corresponding to the goal
        goal_idx = port_params.index[
            np.where(port_params['port'] == goal_port)[0][0]]
        port_params['goal'] = False
        port_params.loc[goal_idx, 'goal'] = True

        # This is the distance from each port to the goal
        half_dist = len(port_params) // 2
        port_params['absdist'] = np.abs(np.mod(
            port_params.index - goal_idx + half_dist, 
            len(port_params)) - half_dist)
        
        
        ## Identify which ports to reward
        # Those within `reward_radius` of the goal
        port_params['reward'] = False
        port_params.loc[
            port_params['absdist'] <= self.reward_radius, 'reward'] = True
        assert port_params['reward'].any()
        
        
        ## Choose params for this trial
        trial_parameters = {}
        for param_name, possible_values in self.param2possible_values.items():
            param_value = random.choice(possible_values)
            trial_parameters[param_name] = param_value


        ## Compute port-specific parameters
        # If targets are played, compute the rate at each port
        if self.play_targets:
            # How fast the targets will be at the goal
            target_rate = trial_parameters['target_rate']
            
            # How quickly the rate falls with distance from goal
            target_radius = trial_parameters['target_radius']
            
            # Set rate of target sounds
            # Once port_params['absdist'] reaches 1 + stim_target_spatial_extent,
            # target rate falls to zero
            port_params.loc[:, 'target_rate'] = target_rate * (
                (1 + target_radius - port_params['absdist']) /
                (1 + target_radius)
                )
            
            # Floor target rate at zero
            port_params.loc[port_params['target_rate'] < 0, 'target_rate'] = 0
        
        # If distracters are played, compute the rate at each port
        if self.play_distracters:
            # How fast the distracters will be at each chosen port
            distracter_rate = trial_parameters['distracter_rate']
            
            # How many ports will play distracters
            n_distracters = trial_parameters['n_distracters']
            
            # Choose `n_distracters` non-goal ports at random
            potential_distracter_idx = [
                idx for idx in port_params.index if idx != goal_idx]
            chosen_distracter_idx = random.sample(
                potential_distracter_idx, k=n_distracters)
            
            # Fill the distrater rate for those ports
            port_params['distracter_rate'] = 0
            port_params.loc[
                chosen_distracter_idx, 'distracter_rate'] = stim_distracter_rate
    
        
        ## Index by port
        port_params = port_params.set_index('port')
        
        
        ## Return
        return goal_port, trial_parameters, port_params

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
        box_params : dict, parameters of the box
        task_params : dict, parameters of the task
        mouse_params : dict, parameters of the mouse
        
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
        self.trial_parameter_chooser = TrialParameterChooser.from_task_params(
            port_names=self.port_names,
            task_params=task_params,
            )


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
        self.marshaller = PiMarshaller(
            agent_names=self.pi_names,
            ip_addresses=self.pi_ip_addresses,
            )
        self.marshaller.start()

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
        goal_port, trial_parameters, port_parameters = (
            self.trial_parameter_chooser.choose(self.previously_rewarded_port)
            )

        # Set up new trial index
        if self.current_trial is None:
            self.current_trial = 0
        else:
            self.current_trial += 1

        # Store the goal port (to define correct trials)
        self.goal_port = goal_port

        # Add trial number to trial_parameters
        # TODO: get Pi to store this with each poke
        trial_parameters['trial_number'] = self.current_trial

        # Update which ports have been poked
        self.ports_poked_this_trial = set()
        
        # Set this to None until set
        self.previously_rewarded_port = None

        self.logger.info(
            f'starting trial {self.current_trial}; '
            f'goal port {goal_port}; '
            f'trial parameters\n{trial_parameters}; '
            f'port_parameters:\n{port_parameters}'
            )
        
        # Send the parameters to each pi
        for pi_name in self.pi_names:
            # Make a copy
            pi_params = trial_parameters.copy()
            
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
                    if pi_specific_param in port_parameters.columns:
                        # Add it, keyed by the side
                        pi_params[f'{side}_{pi_specific_param}'] = (
                            port_parameters.loc[port_name, pi_specific_param])
            
            # Send start to each Pi
            self.network_communicator.send_trial_parameters_to_pi(**pi_params)

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
        