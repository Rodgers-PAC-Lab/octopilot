import random
import logging
import pandas
import numpy as np
from ..shared.logtools import NonRepetitiveLogger

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
        
        # Default values
        # TODO: handle defaults more sensibly
        param2default = {
            'target_rate': 0,
            'target_temporal_log_std': -3,
            'target_radius': 0,
            'target_center_freq': 5000,
            'target_log_amplitude': -3,
            'distracter_rate': 0,
            'distracter_temporal_log_std': -3,
            'distracter_center_freq': 5000,
            'distracter_log_amplitude': -3,
            'n_distracters': 0,
        }
        
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
                if param in param2default:
                    default_value = param2default[param]
                else:
                    raise ValueError(f'no default value specified for {param}')
                rangeval['min'] = default_value
                rangeval['max'] = default_value
                rangeval['n_choices'] = 1
        
            # Store in kwargs
            kwargs['range_' + param] = rangeval
        
        # Transfer task name
        kwargs['task_name'] = task_params.pop('name')
        
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
        task_name=None,
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
        ## Init logger
        self.logger = NonRepetitiveLogger("test")
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.INFO)

        
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
        ## Log
        self.logger.info(
            f'choosing parameters; excluding {previously_rewarded_port}')
        
        
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
        
        # Never reward the previously rewarded_port (if any)
        port_params.loc[
            port_params['port'] == previously_rewarded_port, 'reward'] = False
        
        # Error check
        assert port_params['reward'].any()
        print(port_params)
        
        ## Choose params for this trial
        trial_parameters = {}
        for param_name, possible_values in self.param2possible_values.items():
            param_value = random.choice(possible_values)
            trial_parameters[param_name] = param_value


        ## Compute port-specific parameters
        # If targets are played, compute the rate at each port
        if self.play_targets:
            # How fast the targets will be at the goal
            target_rate = trial_parameters.pop('target_rate')
            
            # How quickly the rate falls with distance from goal
            target_radius = trial_parameters.pop('target_radius')
            
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
            distracter_rate = trial_parameters.pop('distracter_rate')
            
            # How many ports will play distracters
            n_distracters = trial_parameters.pop('n_distracters')
            
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
