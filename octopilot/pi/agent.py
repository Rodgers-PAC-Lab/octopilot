"""Defines PiController and eventually other agents running on the Pi.

Presently the only agent that is defined is PiController. This object
is instantiated on the Pi by either the CLI or GUI. Its job is to run
the task on the Pi side. It contains objects to play sounds (SoundPlayer,
SoundQueuer, SoundChooser, etc), to control hardware (Nosepoke, etc),
and to talk to the Dispatcher agent running on the desktop
(NetworkCommunicator). 

Eventually, we may need to define distinct PiController for different kinds
of tasks. Most of the task-specific logic should be contained within this
object. Other objects should be mostly agnostic to the task rules. 
"""

import datetime
import logging
import time
import pigpio
from . import hardware
from . import sound
from ..shared.networking import PiNetworkCommunicator
from ..shared.logtools import NonRepetitiveLogger

class Agent(object):
    """Object to control the flow of behavioral sessions
    
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
    def __init__(self, params, start_networking=True, dummy_sound_queuer=False):
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
        dummy_sound_queuer : bool
            If True, use a dummy queuer that never provides any audio
            TODO: remove?
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

        # Name my ports
        # Currently this is hardcoded. Otherwise it would have to be matched
        # with the port names in the gui config
        self.identity = self.params['identity']
        self.left_port_name = f'{self.identity}_L'
        self.right_port_name = f'{self.identity}_R'

        # Whether the session is running
        self.session_running = False
        
        # It will keep running until this is set by self.exit() and then 
        # it is noticed by self.mainloop()
        self.shutdown = False
    
        # How long it's been since we received an alive request
        self.alive_timer = None
        self.last_alive_request_received = datetime.datetime.now()
        self.critical_shutdown = False
        

        ## Initialize sound_chooser
        # This object generates frames of audio
        # We need to have it ready to go before initializing the sound queuer
        # TODO: tell daemons.py to use the params for this pi
        self.sound_chooser = sound.SoundChooser_IntermittentBursts(
            blocksize=self.params['jack_blocksize'],
            fs=self.params['jack_sample_rate'],
            )
        
        # Set
        self.sound_chooser.set_audio_parameters(
            left_params={'silenced': True,}, right_params={'silenced': True},
            )
        
        
        ## Initialize sound_queuer
        # This object uses those frames to top up sound_player
        self.sound_queuer = sound.SoundQueuer(
            sound_chooser=self.sound_chooser)
        
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
            )
        
        ## Set up nosepokes
        # TODO: don't activate callbacks until explicitly told to do so
        # Init left nosepoke
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

        
        ## Optionally set up networking
        if start_networking:
            # Instantiates self.network_communicator
            # This will also connect to the Dispatcher
            self.network_communicator = PiNetworkCommunicator(
                identity=self.params['identity'], 
                pi_identity=self.params['identity'], 
                gui_ip=self.params['gui_ip'], 
                poke_port=self.params['poke_port'], 
                config_port=self.params['config_port'],
                )
            
            # Set up hooks
            # These methods will be called when these commands are received
            self.network_communicator.command2method = {
                'set_trial_parameters': self.set_trial_parameters,
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
        self.logger.debug('received alive from dispatcher; will respond')
        self.last_alive_request_received = datetime.datetime.now()
        self.network_communicator.send_alive()

    def start_session(self):
        """Called whenever a new session is started by Dispatcher
        
        Currently there is no explicit "start" message. Instead, we use
        the first set_trial_parameters call if self.session_running is False
        as the trigger to know a session has started. 
        """
        # Log
        self.logger.info('starting session')
        
        # Add handles to report pokes and rewards
        # Hook up the poke in and reward callbacks
        # TODO: add a callback that terminates the audio upon reward
        # TODO: add a callback that plays an error sound upon incorrect poke
        self.left_nosepoke.handles_poke_in.append(self.report_poke)
        self.left_nosepoke.handles_reward.append(self.report_reward)
        self.right_nosepoke.handles_poke_in.append(self.report_poke)
        self.right_nosepoke.handles_reward.append(self.report_reward)
        
        # Set session_running
        self.session_running = True
        
        # Set up timer to test if the Dispatcher is still running and
        # sending are_you_alive requests
        alive_interval = 5
        self.alive_timer = hardware.RepeatedTimer(
            alive_interval, self.check_for_alive_requests)
    
    def check_for_alive_requests(self):
        """Periodically called during a session to see if the Dispatcher running
        
        """
        dt_now = datetime.datetime.now()
        threshold1 = dt_now - datetime.timedelta(seconds=5)
        threshold2 = dt_now - datetime.timedelta(seconds=15)
        
        if self.last_alive_request_received >= threshold1:
            self.logger.debug('dispatcher is alive')
        
        elif self.last_alive_request_received >= threshold2:
            self.logger.error('dispatcher has crashed')
        
        else:
            self.logger.critical('dispatcher has crashed; shutting down')
            self.critical_shutdown = True
    
    def set_trial_parameters(self, **msg_params):
        """Called upon receiving set_trial_parameters from GUI
        
        """
        # Log
        # TODO: why is this message never showing up in the log?
        self.logger.debug(f'setting trial parameters: {msg_params}')
        
        # If not running, issue error
        # Because this might indicate that something has gone wrong
        if not self.session_running:
            self.logger.error(
                f'received trial parameters but session is not running')
            return
        
        # Split into left_params and right_params
        left_params = {}
        right_params = {}
        other_params = {}
        
        for key, val in msg_params.items():
            if key.startswith('left'):
                left_params[key.replace('left_', '')] = val
            elif key.startswith('right'):
                right_params[key.replace('right_', '')] = val
            else:
                other_params[key] = val
        
        # Get rewarded port
        # TODO: replace with binary reward or not for several ports
        if other_params['rewarded_port'] == self.left_nosepoke.name:
            self.logger.info(f'arming left nosepoke for reward')
            self.left_nosepoke.reward_armed = True

        elif other_params['rewarded_port'] == self.right_nosepoke.name:
            self.logger.info(f'arming right nosepoke for reward')
            self.right_nosepoke.reward_armed = True
        
        else:
            self.logger.info(f'disarming all nosepokes')
            self.left_nosepoke.reward_armed = False
            self.right_nosepoke.reward_armed = False
        
        # Use those params to set the new sounds
        self.logger.info(f'setting audio parameters: {left_params} {right_params}')
        self.sound_chooser.set_audio_parameters(left_params, right_params)
        
        # Empty and refill the queue with new sounds
        self.sound_queuer.empty_queue()
        self.sound_queuer.append_sound_to_queue_as_needed()
    
    def report_poke(self, port_name, poke_time):
        """Called by Nosepoke upon poke. Reports to GUI by ZMQ.
        
        """
        self.logger.info(f'reporting poke on {port_name} at {poke_time}')
        # Send 'poke;poke_name' to GUI
        self.network_communicator.poke_socket.send_string(
            f'poke;port_name={port_name}=str;poke_time={poke_time}=str')
    
    def report_reward(self, port_name, poke_time):
        """Called by Nosepoke upon reward. Reports to GUI by ZMQ.
        
        """
        self.logger.info(f'reporting reward on {port_name} at {poke_time}')
        
        # Send 'reward;poke_name' to GUI
        self.network_communicator.poke_socket.send_string(
            f'reward;port_name={port_name}=str;poke_time={poke_time}=str')
    
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
        self.sound_chooser.set_audio_parameters(
            left_params={'silenced': True},
            right_params={'silenced': True},
            )
        
        # Empty the queue of sound
        self.sound_queuer.empty_queue()
        
        # Stop running
        self.session_running = False

        # Mark as shutdown for next mainloop
        self.shutdown = True

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
        
        # Stops any nosepoke autopoking
        self.left_nosepoke.autopoke_stop()
        self.right_nosepoke.autopoke_stop()
        
        # Close all sockets and contexts
        if self.network_communicator is not None:
            self.network_communicator.send_goodbye()
            self.network_communicator.close()   
        
        self.logger.info('done exit')

    def handle_reward(self):
        # TODO: open valve here
        
        # Silence sound generation
        self.sound_chooser.set_audio_parameters(
            left_params={'silenced': True},
            right_params={'silenced': True},
            )
        
        # Empty the queue of already generated sound
        self.sound_queuer.empty_queue()        
    
    def main_loop(self):
        """Loop forever until told to stop, then exit"""
        try:
            self.logger.info('starting mainloop')

            ## Loop until KeyboardInterrupt or exit message received
            last_hello_time = datetime.datetime.now()
            while True:
                # Used to continuously add frames of sound to the 
                # queue until the program stops
                self.sound_queuer.append_sound_to_queue_as_needed()
                
                # Check poke_socket for incoming messages about exit, stop,
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
