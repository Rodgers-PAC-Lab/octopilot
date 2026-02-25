"""Defines PiController and eventually other agents running on the Pi.

Presently the only agent that is defined is PiController. This object
is instantiated on the Pi by either the CLI or GUI. Its job is to run
the task on the Pi side. It contains objects to play sounds (SoundPlayer,
SoundQueuer, SoundGenerator, etc), to control hardware (Nosepoke, etc),
and to talk to the Dispatcher agent running on the desktop
(NetworkCommunicator). 

Eventually, we may need to define distinct PiController for different kinds
of tasks. Most of the task-specific logic should be contained within this
object. Other objects should be mostly agnostic to the task rules. 

TODO: remove NonRepetitiveLogger where possible
"""

import datetime
import logging
import socket
import time
import random 
import numpy as np
import pigpio
from . import hardware
from . import sound
from ..shared.networking import PiNetworkCommunicator
from ..shared.logtools import NonRepetitiveLogger

class Agent(object):
    """Parent object that runs behavioral sessions on the Pi.
    
    This object is never instantiated directly. One of its child classes
    that implements a specific task is instantiated instead.
    
    This object waits to be told what types of sound to play (e.g., rate,
    amplitude, etc) and it can read and write pins through pigpio. It can
    also send messages to the GUI about events that occur (e.g., pokes.
    It should not be concerned with session-level task logic like what
    port to reward next.
    
    The generation of audio is handled by self.SoundQueuer, and the playing
    of sound by self.SoundPlayer. The role of HardwareController in audio
    is to instantiate these objects, provide acoustic parameters to 
    SoundQueuer at the beginning of each trial, and to tell SoundQueuer
    when to stop at the end of the trial.
    """
    def __init__(self, params, start_networking=True):
        """Initialize a new Agent
        
        Arguments
        ---------
        params : dict
            Data about pi parameters. For documentation, see 
            ..shared.load_params.load_pi_params
        start_networking : bool
            If False, don't use any networking
            This would mainly be useful in setting up a new task without
            also having to figure out the networking and Dispatcher at the 
            same time.
        
        Flow
        ----
        * Initialize self.logger
        * Store self.params, self.pig, self.identity, etc
        * Set up alive timers
        * Set up sound generator, sound queuer, sound player
        * Optionally start networking
        """
        
        ## Init logger
        self.logger = NonRepetitiveLogger("test")
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.DEBUG)
        
        
        ## Set attributes
        # Store received parameters
        self.params = params

        # Set up pigpio
        # Initialize a pig to use
        self.pig = pigpio.pi()

        # Name self by hostname
        self.identity = socket.gethostname()

        # Whether the session is running
        self.session_running = False
        
        # Hard code this as -1 instead of None, so that pokes reported before
        # the first trial don't break the sending protocol by sending None
        # as an int
        self.trial_number = -1
        
        # This object will keep running (in self.main_loop) until either of
        # these values is set True
        self.shutdown = False
        self.critical_shutdown = False
    
        # Use this timer to handle alive requests
        self.alive_timer = None
        self.last_alive_request_received = datetime.datetime.now()
        self.alive_timer_test_interval = 5
        self.alive_timer_agent_crash_threshold = 45
        
        # Variable to save params for each trial
        self.prev_trial_params = None
        
        
        ## Initialize sound_generator
        # This object generates frames of audio
        # We need to have it ready to go before initializing the sound queuer
        # TODO: tell daemons.py to use the params for this pi
        self.sound_generator = sound.SoundGenerator_IntermittentBursts(
            blocksize=1024,
            fs=192000,
            report_method=self.report_sound_plan,
            attenuation_file='/home/pi/attenuation.csv',
            )
        
        # Set to no sound at first
        self.sound_generator.set_audio_parameters(
            left_params={},
            right_params={},
            )
        
        
        ## Initialize sound_queuer
        # This object uses those frames to top up sound_player
        self.sound_queuer = sound.SoundQueuer(
            sound_generator=self.sound_generator)
        
        # Fill the queue before we instantiate sound_player
        self.sound_queuer.append_sound_to_queue_as_needed()
        
        
        ## Initialize sound_player
        # This object pulls frames of audio from that queue and gives them
        # to a jack.Client that it contains
        # TODO: probably instantiate the jack.Client here and provide it
        # Note that it will immediately start asking for frames of audio, so
        # sound_queuer has to be ready to go
        # TODO: add a start() method to sound_player
        self.sound_player = sound.SoundPlayer(
            name='sound_player', 
            sound_queuer=self.sound_queuer,
            report_method=self.report_sound,
            pigpio_handle=self.pig,
            )
        
        # Initialize this output pin for sound reporting
        self.pig.set_mode(23, pigpio.OUTPUT)
        
        
        ## Optionally set up networking
        if start_networking:
            # Instantiates self.network_communicator
            # This will also connect to the Dispatcher
            self.network_communicator = PiNetworkCommunicator(
                identity=self.identity, 
                gui_ip=self.params['gui_ip'], 
                zmq_port=self.params['zmq_port'],
                bonsai_ip = self.params['bonsai_ip'],
                bonsai_port = self.params['bonsai_port'],
                )
            
            # Set up hooks
            # These methods will be called when these commands are received
            self.network_communicator.command2method = {
                'set_trial_parameters': self.set_trial_parameters,
                'silence': self.stop_sounds,
                'stop': self.stop_session,
                'exit': self.exit,
                'start': self.start_session,
                'are_you_alive': self.recv_alive_request,
                }            
            
            # Send hello
            self.network_communicator.send_hello()

    def recv_alive_request(self):
        """Respond to Dispatcher's request to know if we are alive
        
        Log when this happens. If it doesn't happen frequently enough
        and a sessions is running, conclude that the Dispatcher has crashed
        and initiate critical shutdown.
        """
        dt_now = datetime.datetime.now()
        self.logger.debug(f'{dt_now}: received alive from dispatcher; will respond')
        self.last_alive_request_received = datetime.datetime.now()
        self.network_communicator.send_alive()
        dt_now = datetime.datetime.now()
        self.logger.debug(f'{dt_now}: responded to dispatcher alive request')

    def start_session(self):
        """Called whenever a new session is started by Dispatcher
        
        Currently there is no explicit "start" message. Instead, we use
        the first set_trial_parameters call if self.session_running is False
        as the trigger to know a session has started. 
        """
        # Log
        self.logger.info('starting session')
        
        # Set session_running
        self.session_running = True
        
        # Set up timer to test if the Dispatcher is still running and
        # sending are_you_alive requests
        self.alive_timer = hardware.RepeatedTimer(
            self.alive_timer_test_interval,
            self.check_for_alive_requests,
            )
        
        # Mark the last alive time as now, the time the timer was started
        self.last_alive_request_received = datetime.datetime.now()
    
    def check_for_alive_requests(self):
        """Periodically called during a session to see if the Dispatcher running
        
        alive_timer_test_interval : 
            Seconds between calls to this function
            This sets the speed with which problems are detected
            Can be somewhat frequent because this call is fast
        
        alive_timer_agent_crash_threshold : 
            Seconds before deciding that the dispatcher has crashed
            Must be longer than alive_timer_send_interval
            If this is too short, we might false-positive crash
            If this is too long, it will take a while for agents to shut down
        
        alive_timer_send_interval : On Dispatcher
            Seconds between sending of 'alive' requests
            If this is too frequent, we waste time (and potentially increase
            risk of zmq threading crash)
            If this is too slow, we won't know when a crash happens
        
        alive_timer_dispatcher_crash_threshold : On Dispatcher
            Seconds before deciding that the agents have crashed
            Must be longer than alive_timer_send_interval
        
        """
        # Set the threshold as alive_timer_crash_threshold seconds ago
        dt_now = datetime.datetime.now()
        threshold = dt_now - datetime.timedelta(
            seconds=self.alive_timer_agent_crash_threshold)
        
        # If the last received request was before that, then shut down
        if self.last_alive_request_received < threshold:
            self.logger.critical('dispatcher has crashed; shutting down')
            self.critical_shutdown = True
    
    def report_trial_start(self, dt):
        """Called by Agent when new trial. Reports to GUI by ZMQ.
        
        dt : str, isoformatted time of synchronization flash
        """
        # Send to GUI
        self.network_communicator.poke_socket.send_string(
            f'flash;'
            f'trial_number={self.trial_number}=int;'
            f'flash_time={dt}=str'
            )          
    
    def exit(self):
        """Shut down objects
        
        This is in a finally in the mainloop
        """
        self.logger.info('beginning exit')
        self.stop_session()
        
        # Deactivating the Sound Player before closing the program
        self.sound_player.client.deactivate()
        
        # Stop jack
        self.sound_player.client.close()
        
        # Stops the pigpio connection
        self.pig.stop()
        
        # Close all sockets and contexts
        if self.network_communicator is not None:
            self.network_communicator.send_goodbye()
            self.network_communicator.close()   
        
        self.logger.info('done exit')

    def main_loop(self):
        """Loop forever until told to stop, then exit
        
        This method is called by start_cli. It will loop until told to stop. 
        All other methods of this object are called asynchronously.
        
        On each loop, it will:
        * self.sound_queuer.append_sound_to_queue_as_needed
        * self.network_communicator.check_socket
        * Check the values of self.critical_shutdown and self.shutdown
        
        It will stop looping once
        * self.critical_shutdown is set True (this triggers an exception)
        * self.shutdown is set True
        * KeyboardInterrupt is received (only works in CLI mode)
        
        After exiting the loop it will
        * Call self.exit
        """
        try:
            self.logger.info('starting mainloop')

            ## Loop until KeyboardInterrupt or exit message received
            last_hello_time = datetime.datetime.now()
            while True:
                # Initial bonsai monitoring 
                # TODO: move this somewhere else
                # self.monitor_bonsai("decrease")
    
                # Used to continuously add frames of sound to the 
                # queue until the program stops
                self.sound_queuer.append_sound_to_queue_as_needed()
                
                # start, reward, etc
                if self.network_communicator is not None:
                    self.network_communicator.check_socket()

                if self.critical_shutdown:
                    self.logger.critical('critical shutdown')
                    raise ValueError('critical shutdown')
                
                if self.shutdown:
                    self.logger.info('shutdown detected')
                    break
                
                # If there's nothing in the main loop, not even a sleep,
                # then for some reason this leads to XRun errors
                # Perhaps the interpreter is optimizing away the mainloop
                # time.sleep(0) prevents this from happening
                time.sleep(0)

        except KeyboardInterrupt:
            print('KeyboardInterrupt received, shutting down')
            
        finally:
            # Shut down all network, sound, and hardware
            self.exit()
            self.logger.info('agent done')

class SoundSeekingAgent(Agent):
    """Child of Agent that instantiates the sound-seeking task on a single Pi.
    
    """
    def __init__(self, *args, **kwargs):
        """Initialize a new OctagonTask
        
        Flow
        * Calls Agent.__init__. See that method for arguments.
        * Initializes self.left_nosepoke and self.right_nosepoke
        """

        ## Call Agent.__init___
        super().__init__(*args, **kwargs)
    
        
        ## Set up nosepokes
        # Name my ports
        # Currently this is hardcoded here and in load_params.load_box_params
        self.left_port_name = f'{self.identity}_L'
        self.right_port_name = f'{self.identity}_R'

        # Init left nosepoke
        # The callbacks aren't set until start_session
        self.left_nosepoke = hardware.Nosepoke(
            name=self.left_port_name,
            pig=self.pig,
            poke_pin=self.params['left_nosepoke'], 
            poke_sense=True, 
            solenoid_pin=self.params['left_solenoid'],
            red_pin=self.params['left_led_red'], 
            green_pin=self.params['left_led_green'], 
            blue_pin=self.params['left_led_blue'], 
            )
        
        # Init right_nosepoke
        self.right_nosepoke = hardware.Nosepoke(
            name=self.right_port_name,
            pig=self.pig,
            poke_pin=self.params['right_nosepoke'], 
            poke_sense=True, 
            solenoid_pin=self.params['right_solenoid'],
            red_pin=self.params['right_led_red'], 
            green_pin=self.params['right_led_green'], 
            blue_pin=self.params['right_led_blue'], 
            )            

        # Autopoke
        # This simulates the presence of a mouse, which may be poking before
        # the session actually starts
        self.left_nosepoke.autopoke_start(rate=0)
        self.right_nosepoke.autopoke_start(rate=0)    

    def start_session(self):
        """Start a new session in the sound-seeking task.
        
        Flow
        ---
        * Calls Agent.start_session
        * Sets up the handles in the nosepokes for reporting pokes and rewards
        """
        # Call Agent.start_session
        super().start_session()
        
        # Add handles to report pokes and rewards
        # Hook up the poke in and reward callbacks
        # TODO: add a callback that plays an error sound upon incorrect poke
        self.left_nosepoke.handles_poke_in.append(self.report_poke)
        self.left_nosepoke.handles_reward.append(self.report_reward)
        self.right_nosepoke.handles_poke_in.append(self.report_poke)
        self.right_nosepoke.handles_reward.append(self.report_reward)

    def report_poke(self, port_name, poke_time):
        """Called by Nosepoke upon poke. Reports to Dispatcher by ZMQ.
        
        """
        # Log
        self.logger.info(f'reporting poke on {port_name} at {poke_time}')
        
        # Report to Dispatcher
        self.network_communicator.poke_socket.send_string(
            f'poke;'
            f'trial_number={self.trial_number}=int;'
            f'port_name={port_name}=str;'
            f'poke_time={poke_time}=str'
            )
    
    def report_reward(self, port_name, poke_time):
        """Called by Nosepoke upon reward. Reports to Dispatcher by ZMQ.
        
        """
        # Log
        self.logger.info(f'reporting reward on {port_name} at {poke_time}')
        
        # Report to Dispatcher
        self.network_communicator.poke_socket.send_string(
            f'reward;'
            f'trial_number={self.trial_number}=int;'
            f'port_name={port_name}=str;'
            f'poke_time={poke_time}=str'
            )            

    def report_sound(self, data, last_frame_time, frames_since_cycle_start, dt):
        """Called by SoundPlayer when audio is played. Reports to Dispatcher.
        
        Arguments
        ---
        data : 2d array
            The actual sound that is played
        last_frame_time, frames_since_cycle_start : int
            Timing data from jack.client
        dt: str
            Isoformat string when the sound was played
        """
        # This is only an approximate hash because it excludes the
        # middle of the data
        data_hash = hash(str(data))
        
        # Determine which channel is playing sound
        data_left = data[:, 0].std()
        data_right = data[:, 1].std()
        
        # Report to Dispatcher
        self.network_communicator.poke_socket.send_string(
            f'sound;'
            f'trial_number={self.trial_number}=int;'
            f'data_left={data_left}=float;'
            f'data_right={data_right}=float;'
            f'last_frame_time={last_frame_time}=int;'
            f'frames_since_cycle_start={frames_since_cycle_start}=int;'
            f'data_hash={data_hash}=int;'
            f'dt={dt}=str'
            )  

    def report_sound_plan(self, sound_plan):
        """Called by SoundGenerator when new plan made. Reports to Dispatcher.
        
        sound_plan : DataFrame
            Plan for sound to play
        """
        # The first time this is called, the network_communicator hasn't
        # been instantiated yet
        try:
            self.network_communicator
        except AttributeError:
            return
        
        # Report to Dispatcher
        self.network_communicator.poke_socket.send_string(
            f'sound_plan;'
            f'trial_number={self.trial_number}=int;'
            f'sound_plan={sound_plan.to_csv(index=None)}=str'
            )  
    
    def set_trial_parameters(self, **msg_params):
        """Called upon receiving set_trial_parameters from GUI
        
        This function sets everything in motion for a new trial.
        
        Arguments
        ---
        A dict of msg_params, which may include:
            'trial_number' :
            'left_reward', 'right_reward' : if True, arm the port
                Defaults to False
            'left_*', 'right_*' : sound parameters
        
        Flow
        ---
        * Flash the LEDs
        * Update self.trial_number
        * self.report_trial_start
        * Optionally arm ports for reward
        * Parse any sound parameters and send to 
          self.sound_generator.set_audio_parameters
        """
        
        ## Flash an LED
        # Use this to determine when the flash was done in local timebase
        timestamp = datetime.datetime.now().isoformat()

        # Log the time of the flash
        # Do this after the flash itself so that we don't jitter
        self.left_nosepoke.turn_on_red_led()
        self.right_nosepoke.turn_on_red_led()
        time.sleep(.3)
        self.left_nosepoke.turn_off_red_led()
        self.right_nosepoke.turn_off_red_led()


        ## Log
        self.logger.debug(f'setting trial parameters: {msg_params}')

        
        ## If not running, issue error
        # Because this might indicate that something has gone wrong
        if not self.session_running:
            self.logger.error(
                f'received trial parameters but session is not running')
            return


        ## Update trial number
        # Do this first, because some of the sound functions need to know
        # the correct trial number
        self.trial_number = msg_params['trial_number']
        
    
        ## Log trial start (after trial number update)
        # Report trial start
        self.report_trial_start(timestamp)
        
        
        ## Use 'left_reward' and 'right_reward' in msg_params to arm pokes
        # TODO: disarm all nosepokes immediately upon reward, not just
        # the one that was rewarded

        # Pop left reward out separately, with default False
        if 'left_reward' in msg_params:
            left_reward = msg_params.pop('left_reward')
        else:
            left_reward = False

        # Optionally arm left reward
        if left_reward:
            self.logger.info(f'arming left nosepoke for reward')
            self.left_nosepoke.reward_armed = True
        else:
            self.left_nosepoke.reward_armed = False
        
        # Pop right reward out separately, with default False
        if 'right_reward' in msg_params:
            right_reward = msg_params.pop('right_reward')
        else:
            right_reward = False
        
        # Optionally arm right reward
        if right_reward:
            self.logger.info(f'arming right nosepoke for reward')
            self.right_nosepoke.reward_armed = True
        else:
            self.right_nosepoke.reward_armed = False
        
        
        ## Split into left_params and right_params
        # TODO: make this more flexible
        # Right now it's hard coded that each port can only play one type
        # of sound, which must be target or distracter
        if 'left_target_rate' in msg_params and msg_params['left_target_rate'] > 0:
            left_params = {
                'rate': msg_params['left_target_rate'],
                'temporal_log_std': msg_params['target_temporal_log_std'],
                'center_freq': msg_params['target_center_freq'],
                'log_amplitude': msg_params['target_log_amplitude'],
                'bandwidth': msg_params['target_bandwidth'],
                }
        elif 'left_distracter_rate' in msg_params and msg_params['left_distracter_rate'] > 0:
            left_params = {
                'rate': msg_params['left_distracter_rate'],
                'temporal_log_std': msg_params['distracter_temporal_log_std'],
                'center_freq': msg_params['distracter_center_freq'],
                'log_amplitude': msg_params['distracter_log_amplitude'],
                }
        else:
            left_params = {}
    
        if 'right_target_rate' in msg_params and msg_params['right_target_rate'] > 0:
            right_params = {
                'rate': msg_params['right_target_rate'],
                'temporal_log_std': msg_params['target_temporal_log_std'],
                'center_freq': msg_params['target_center_freq'],
                'log_amplitude': msg_params['target_log_amplitude'],
                'bandwidth': msg_params['target_bandwidth'],
                }
        elif 'right_distracter_rate' in msg_params and msg_params['right_distracter_rate'] > 0:
            right_params = {
                'rate': msg_params['right_distracter_rate'],
                'temporal_log_std': msg_params['distracter_temporal_log_std'],
                'center_freq': msg_params['distracter_center_freq'],
                'log_amplitude': msg_params['distracter_log_amplitude'],
                }
        else:
            right_params = {}
    
    
        ## Use those params to set the new sounds
        self.logger.info(
            'setting audio parameters. '
            f'LEFT={left_params}. RIGHT={right_params}')
        self.sound_generator.set_audio_parameters(left_params, right_params)
        
        # Saving these params to be modified by other methods
        self.prev_trial_params = msg_params
        
        # Empty and refill the queue with new sounds
        self.sound_queuer.empty_queue()
        self.sound_queuer.append_sound_to_queue_as_needed()   

    def stop_sounds(self):
        """Silence the sounds
        
        This is triggered by the ZMQ command 'silence', which is issued
        by the Dispatcher during the ITI. 
        
        It is also called by self.stop_session.
        """
        # Silence sound generation
        self.sound_generator.set_audio_parameters(
            left_params={},
            right_params={},
            )
        
        # Empty the queue of sound
        self.sound_queuer.empty_queue()        

    def stop_session(self):
        """Runs when a session is stopped
        
        Flow
        ----
        * It turns off all active LEDs, 
        * resets all the variables used for tracking to None, 
        * stops playing sound,
        * and empties the queue.
        """
        self.logger.info('beginning stop_session')

        # Stops any nosepoke autopoking
        self.left_nosepoke.autopoke_stop()
        self.right_nosepoke.autopoke_stop()
        
        # Remove all handles from nose pokes
        try:
            self.left_nosepoke.handles_poke_in.remove(self.report_poke)
        except ValueError:
            self.logger.error('stop received but handle not in list')
        
        try:
            self.left_nosepoke.handles_reward.remove(self.report_reward)
        except ValueError:
            self.logger.error('stop received but handle not in list')
        
        try:
            self.right_nosepoke.handles_poke_in.remove(self.report_poke)
        except ValueError:
            self.logger.error('stop received but handle not in list')
        
        try:
            self.right_nosepoke.handles_reward.remove(self.report_reward)
        except ValueError:
            self.logger.error('stop received but handle not in list')
        
        # Stop checking for alive requests
        if self.alive_timer is None:
            self.logger.error('stop received but alive_timer is None')
        else:
            self.alive_timer.stop()

        # Silence sound generation
        self.stop_sounds()
        
        # Stop running
        self.session_running = False

        # Mark as shutdown for next mainloop
        self.shutdown = True

class BonsaiOctagonTask(SoundSeekingAgent):
    """Version with Bonsai closed-loop volume control
    
    """
    def __init__(self):
        # Randomly choosing to manipulate sound in trial
        self.manipulation_probability = 0.5
        self.is_manipulation_trial = None

    def set_trial_parameters(self, **msg_params):
        super().set_trial_parameters()

        # Get the trigger trial
        self.is_manipulation_trial = msg_params['trigger_trial']

        
        # Making it so that the first 1-2 trials are not trigger trials 
        if self.trial_number == 0 or self.trial_number == 1:
            self.is_manipulation_trial = False
        else:
            pass

        
        # Determine association with True or False based on probability
        if self.is_manipulation_trial == True:
            self.logger.info(f'Trial {self.trial_number} will change sound')
        else:
            self.logger.info(f'Trial {self.trial_number} will not change sound')        

    def increase_volume(self):
        ## Note: Multiplying log amplitude decreases volume and dividing increases it 
        volume = "increase"
        volume_time = datetime.datetime.now()
        
        if self.prev_trial_params is not None:
            # Left Parameters
            if 'left_target_rate' in self.prev_trial_params and self.prev_trial_params['left_target_rate'] > 0:
                left_params = {
                    'rate': self.prev_trial_params['left_target_rate'],
                    'temporal_log_std': self.prev_trial_params['target_temporal_log_std'],
                    'center_freq': self.prev_trial_params['target_center_freq'],
                    'log_amplitude': 0.25 * self.prev_trial_params['target_log_amplitude'],
                    }
            else:
                left_params = {}
            
            if 'right_target_rate' in self.prev_trial_params and self.prev_trial_params['right_target_rate'] > 0:
                right_params = {
                    'rate': self.prev_trial_params['right_target_rate'],
                    'temporal_log_std': self.prev_trial_params['target_temporal_log_std'],
                    'center_freq': self.prev_trial_params['target_center_freq'],
                    'log_amplitude': 0.25 * self.prev_trial_params['target_log_amplitude'],
                    }
            else:
                right_params = {}
            
            # Empty and refill the queue with new sounds
            self.sound_queuer.empty_queue()
            
            ## Use those params to set the new sounds
            self.logger.info(
                'setting audio parameters. '
                f'LEFT={left_params}. RIGHT={right_params}')
            self.sound_generator.set_audio_parameters(left_params, right_params)
            print('Increasing Volume')
            self.report_volume_change(volume, volume_time)
            self.sound_queuer.append_sound_to_queue_as_needed()
        else:
            pass
    
    def normal_volume(self):
        volume = "normal"
        volume_time = datetime.datetime.now()
        
        if self.prev_trial_params is not None:
            # Left Parameters
            if 'left_target_rate' in self.prev_trial_params and self.prev_trial_params['left_target_rate'] > 0:
                left_params = {
                    'rate': self.prev_trial_params['left_target_rate'],
                    'temporal_log_std': self.prev_trial_params['target_temporal_log_std'],
                    'center_freq': self.prev_trial_params['target_center_freq'],
                    'log_amplitude': self.prev_trial_params['target_log_amplitude'],
                    }
            else:
                left_params = {}
            
            if 'right_target_rate' in self.prev_trial_params and self.prev_trial_params['right_target_rate'] > 0:
                right_params = {
                    'rate': self.prev_trial_params['right_target_rate'],
                    'temporal_log_std': self.prev_trial_params['target_temporal_log_std'],
                    'center_freq': self.prev_trial_params['target_center_freq'],
                    'log_amplitude': self.prev_trial_params['target_log_amplitude'],
                    }
            else:
                right_params = {}
            
            # Empty and refill the queue with new sounds
            self.sound_queuer.empty_queue()
            
            ## Use those params to set the new sounds
            self.logger.info(
                'setting audio parameters. '
                f'LEFT={left_params}. RIGHT={right_params}')
            self.sound_generator.set_audio_parameters(left_params, right_params)
            print('Returning Volume to Normal Level')
            self.report_volume_change(volume, volume_time)
            self.sound_queuer.append_sound_to_queue_as_needed()
        else:
            pass
    
    def decrease_volume(self):
        volume = "decrease"
        volume_time = datetime.datetime.now()
        
        if self.prev_trial_params is not None:
            # Left Parameters        
            #~ if 'left_target_rate' in self.prev_trial_params and self.prev_trial_params['left_target_rate'] > 0:
                #~ left_params = {
                    #~ 'rate': self.prev_trial_params['left_target_rate'],
                    #~ 'temporal_log_std': self.prev_trial_params['target_temporal_log_std'],
                    #~ 'center_freq': self.prev_trial_params['target_center_freq'],
                    #~ 'log_amplitude': 0,
                    #~ }
            #~ else:
            left_params = {}

            #~ if 'right_target_rate' in self.prev_trial_params and self.prev_trial_params['right_target_rate'] > 0:
                #~ right_params = {
                    #~ 'rate': self.prev_trial_params['right_target_rate'],
                    #~ 'temporal_log_std': self.prev_trial_params['target_temporal_log_std'],
                    #~ 'center_freq': self.prev_trial_params['target_center_freq'],
                    #~ 'log_amplitude': 0,
                    #~ }
            #~ else:
            right_params = {}
            
            # Empty and refill the queue with new sounds
            self.sound_queuer.empty_queue()
        
            ## Use those params to set the new sounds
            self.logger.info(
                'setting audio parameters. '
                f'LEFT={left_params}. RIGHT={right_params}')
            self.sound_generator.set_audio_parameters(left_params, right_params)
            print('Decreasing Volume')
            self.report_volume_change(volume, volume_time)
            self.sound_queuer.append_sound_to_queue_as_needed()
        
        else:
            pass
    
    def monitor_bonsai(self, task):
        # Initial bonsai monitoring 
        self.network_communicator.check_bonsai_socket()
        
        if self.is_manipulation_trial == True:
            if self.network_communicator.prev_bonsai_state == None:
                if self.network_communicator.bonsai_state == "True":
                    if task == "decrease":
                        self.decrease_volume()
                    elif task == "increase":
                        self.increase_volume() 
                elif self.network_communicator.bonsai_state == "False" or None:
                    pass
                
            # Logic to interact with bonsai (not working through method)
            if self.network_communicator.bonsai_state == "True":
                if self.network_communicator.prev_bonsai_state == "False" or self.network_communicator.prev_bonsai_state == None:
                    if task == "decrease":
                        self.decrease_volume()
                    elif task == "increase":
                        self.increase_volume()                    
                    self.network_communicator.prev_bonsai_state = self.network_communicator.bonsai_state
                else:
                    self.network_communicator.prev_bonsai_state = self.network_communicator.bonsai_state
            
            elif self.network_communicator.bonsai_state == "False":
                if self.network_communicator.prev_bonsai_state == "True":
                    self.normal_volume()
                    self.network_communicator.prev_bonsai_state = self.network_communicator.bonsai_state
                else:
                    self.network_communicator.prev_bonsai_state = self.network_communicator.bonsai_state
        else:
            pass
 
    def report_volume_change(self, volume, volume_time):
        """Called by agent when volume is changed. Reports to GUI by ZMQ.
        """
        self.logger.info(f'reporting volume {volume} at {volume_time}')
        # Send 'poke;poke_name' to GUI
        self.network_communicator.poke_socket.send_string(
            f'volume_change;'
            f'trial_number={self.trial_number}=int;'
            f'volume={volume}=str;'
            f'volume_time={volume_time}=str'
            )

class WheelTask(Agent):
    """Version of Agent that runs the WheelTask"""
    
    def __init__(self, *args, **kwargs):
        ## Call Agent.__init___
        super().__init__(*args, **kwargs)
    
        
        ## Set up Wheel
        self.wheel_listener = hardware.WheelListener(self.pig)
        

        ## Set up reward
        self.solenoid_pin = 6
        
        # The default is INPUT, so only outputs have to be set
        self.pig.set_mode(self.solenoid_pin, pigpio.OUTPUT)

        
        ## Wheel and reward size parameters
        # Activate continuous balancing
        self.sound_player.continuous_balancing = True
        
        # This is the size of a regular reward
        self.max_reward = .05

        # As time_since_last_reward increases, reward gets exponentially smaller
        # When time_since_last_reward == reward_decay, the reward size
        # is 63.7% of full. 
        # As reward_decay increases, mouse has to wait longer 
        # 300 clicks is about 20 deg (easy)
        self.reward_for_spinning = False
        self.reward_decay = 0.5
        self.wheel_reward_thresh = 300 
        
        # This defines the range in which turning the wheel changes the sound
        # Every trial starts at either max or min
        # 1000 clicks is about 60 deg
        self.wheel_max = 1000
        self.wheel_min = -1000
        
        # This is how close the mouse has to get to the reward zone
        # This can be small, just not so small that the mouse spins right 
        # through it before it checks, which is probably pretty hard to do
        # 100 clicks is about 6 deg
        self.reward_range = 100

        
        ## These are initialized later
        self.last_rewarded_position = None
        self.last_reported_time = None
        self.last_reward_time = None
        self.clipped_position = 0
        self.last_raw_position = 0
        self.reward_delivered = False
    
    def start_session(self):
        # Call Agent.start_session
        super().start_session()
        
        # Start wheel listening
        self.wheel_listener.report_callback = self.report_wheel

        # Initialize wheel parameters
        self.last_rewarded_position = 0
        self.last_reported_time = datetime.datetime.now()
        self.last_reward_time = datetime.datetime.now()
        
    def report_wheel(self):
        """Called by self.wheel_listener every time the wheel moves"""
        
        ## Get time
        now = datetime.datetime.now()        
        
        
        ## Update wheel positions
        # At the beginning of each trial
        # self.last_raw_position = self.wheel_listener.position
        # self.clipped_position = random
        
        # Get actual wheel position
        wheel_position = self.wheel_listener.position
        
        # Compute movement since last_raw_position and update it
        diff = wheel_position - self.last_raw_position
        self.last_raw_position = wheel_position
        
        # Clip the new position
        self.clipped_position += diff
        
        if self.clipped_position > self.wheel_max:
            self.clipped_position = self.wheel_max
        
        if self.clipped_position < self.wheel_min:
            self.clipped_position = self.wheel_min
        
        
        ## Update lr_weight
        # Compute the weight within the min/max range
        position_within_range = (
            (self.clipped_position - self.wheel_min) / 
            (self.wheel_max - self.wheel_min))
        
        # Clip to [0, 1], just in case we left the clipped range somehow
        if position_within_range < 0:
            position_within_range = 0
        elif position_within_range > 1:
            position_within_range = 1
        
        def convert_position_to_weight(position, max_db=40):
            # Map this onto (R-L) in dB [-10, 10]
            db_diff = (position - 0.5) * 2 * max_db
            
            # Map this db_diff onto a R/L ratio
            lr_ratio = 10 ** (db_diff / 20)
            
            # Map R/L ratio onto weight of R
            weight = lr_ratio / (lr_ratio + 1)
            
            return weight
        
        weight = convert_position_to_weight(position_within_range)
        
        # Update the weight in sound player, using the range [0, 1]
        # TODO: this should be done with a multiprocessing.Event or similar
        self.sound_player.lr_weight = weight
        
        
        ## Report to Dispatcher
        if np.mod(wheel_position, 100) == 0:
            self.network_communicator.poke_socket.send_string(
                f'wheel;'
                f'trial_number={self.trial_number}=int;'
                f'wheel_position={wheel_position}=int;'
                f'clipped_position={self.clipped_position}=int;'
                f'weight={weight}=float;'
                f'wheel_time={now.isoformat()}=str'
                )

        
        ## Reward conditions
        if (np.abs(self.clipped_position) < self.reward_range) and not self.reward_delivered:
            # Within target range
            # Reward and end trial
            self.reward(self.max_reward)

        elif self.reward_for_spinning and np.abs(wheel_position - 
                self.last_rewarded_position) > self.wheel_reward_thresh:
            
            # Shaping stage: reward if it's moved far enough
            # Set last rewarded position to current position
            self.last_rewarded_position = wheel_position
            
            # Update reward size using temporal discounting
            time_since_last_reward = (
                now - self.last_reward_time).total_seconds()
            reward_size = self.max_reward * (
                1 - np.exp(-time_since_last_reward / self.reward_decay))
            self.last_reward_time = now
            
            # Reward but do not end trial
            self.reward(reward_size, report=False)

    def reward(self, reward_size, report=True):
        """Open the reward port and optionally report to Dispatcher
        
        reward_size : numeric
            Duration that the solenoid is open, in ms
        
        report : bool
            If True, call self.report_reward
            This likely triggers the trial to end, which we may not want
        """
        # Get current time
        reward_time = datetime.datetime.now()
        
        # Log
        self.logger.info(f'{[reward_time]} rewarding for {reward_size} s')
        
        # Issue reward
        # TODO: rewrite with threading to avoid delay
        self.pig.write(self.solenoid_pin, 1)
        time.sleep(reward_size)
        self.pig.write(self.solenoid_pin, 0)
        
        # Report
        if report:
            # This prevents multiple rewards per trial (excluding non-reported 
            # rewards)
            self.reward_delivered = True

            self.report_reward(reward_time)
    
    def report_reward(self, reward_time):
        """Called by WheelController upon reward. Reports to Dispatcher by ZMQ.
        
        """
        # Log
        self.logger.info(f'reporting reward at {reward_time}')
        
        # Report to Dispatcher
        self.network_communicator.poke_socket.send_string(
            f'reward;'
            f'trial_number={self.trial_number}=int;'
            f'reward_time={reward_time}=str'
            )  
    
    def report_sound_plan(self, *args, **kwargs):
        # Currently required by parent class
        pass
    
    def report_sound(self, *args, **kwargs):
        # Currently required by parent class
        pass

    def stop_sounds(self, *args, **kwargs):
        # Currently required by something
        pass
    
    def set_trial_parameters(self, **msg_params):
        ## Flash an LED
        # Use this to determine when the flash was done in local timebase
        timestamp = datetime.datetime.now().isoformat()

        #~ # Log the time of the flash
        #~ # Do this after the flash itself so that we don't jitter
        #~ self.left_nosepoke.turn_on_red_led()
        #~ self.right_nosepoke.turn_on_red_led()
        #~ time.sleep(.3)
        #~ self.left_nosepoke.turn_off_red_led()
        #~ self.right_nosepoke.turn_off_red_led()


        ## Log
        self.logger.debug(f'setting trial parameters: {msg_params}')

        
        ## If not running, issue error
        # Because this might indicate that something has gone wrong
        if not self.session_running:
            self.logger.error(
                f'received trial parameters but session is not running')
            return


        ## Update trial number
        # Do this first, because some of the sound functions need to know
        # the correct trial number
        self.trial_number = msg_params['trial_number']
        
        
        ## Log trial start (after trial number update)
        # Report trial start
        self.report_trial_start(timestamp)
        
        
        ## Split into left_params and right_params
        # For the wheel task, we use left sound only, and reweight it later
        left_params = {
            'rate': 4, #msg_params['left_target_rate'],
            'temporal_log_std': -1, #msg_params['target_temporal_log_std'],
            'center_freq': 10000, #msg_params['target_center_freq'],
            'log_amplitude': -2, #msg_params['target_log_amplitude'],
            'bandwidth': 3000, #msg_params['target_bandwidth'],
            }

        right_params = {
            }
    
    
        ## Use those params to set the new sounds
        self.logger.info(
            'setting audio parameters. '
            f'LEFT={left_params}. RIGHT={right_params}')
        self.sound_generator.set_audio_parameters(left_params, right_params)
        
        # Set lr weight back to center
        self.sound_player.lr_weight = 0.5
        
        # Saving these params to be modified by other methods
        self.prev_trial_params = msg_params
        
        # Empty and refill the queue with new sounds
        self.sound_queuer.empty_queue()
        self.sound_queuer.append_sound_to_queue_as_needed()   
        
        
        ## Update other trial parameters
        # Starting position - TODO get from Dispatcher
        if np.random.random() < 0.5:
            self.clipped_position = self.wheel_min
        else:
            self.clipped_position = self.wheel_max

        # Everything should be locked to raw position at the start of the trial
        self.last_raw_position = self.wheel_listener.position
        
        # Prevents multiple rewards
        self.reward_delivered = False
    
    def stop_session(self):
        """Runs when a session is stopped
        
        This is triggered by the 'stop' command sent to NetworkCommunicator.
        """
        # Log
        self.logger.info('beginning stop_session')
        
        # TODO: remove handles from wheel here

        # Stop checking for alive requests
        if self.alive_timer is None:
            self.logger.error('stop received but alive_timer is None')
        else:
            self.alive_timer.stop()

        # Silence sound generation
        self.stop_sounds()
        
        # Stop running
        self.session_running = False

        # Mark as shutdown for next mainloop
        self.shutdown = True