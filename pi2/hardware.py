import time
import pigpio
import zmq
from . import sound
from . import networking
from logging_utils.logging_utils import NonRepetitiveLogger
import logging
import threading
import numpy as np
import datetime

class RepeatedTimer(object):
    # https://stackoverflow.com/questions/474528/how-to-repeatedly-execute-a-function-every-x-seconds
    def __init__(self, interval, function, *args, **kwargs):
        self._timer = None
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        self.next_call = time.time()
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
        if not self.is_running:
            self.next_call += self.interval
        self._timer = threading.Timer(self.next_call - time.time(), self._run)
        self._timer.start()
        self.is_running = True

    def stop(self):
        self._timer.cancel()
        self.is_running = False

class Nosepoke(object):
    def __init__(self, name, pig, poke_pin, poke_sense, solenoid_pin, 
        red_pin, green_pin, blue_pin):
        """Init a new Nosepoke
        
        Arguments
        ---------
        name : str
            How it refers to itself in messages. Typical piname_L etc
        pig : pigpio.pi
        poke_pin, solenoid_pin, {red|green|blue}_pin : pin numbers 0-53
        poke_sense : bool
            True if we should call the callback on a RISING_EDGE,
            False if we should call the callback on a FALLING_EDGE
            TODO: which is 901 and which is 903
        """
        ## Init logger
        self.logger = NonRepetitiveLogger("test")
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.INFO)
        
        
        ## Save attributes
        self.name = name
        self.pig = pig
        self.poke_pin = poke_pin
        self.poke_sense = poke_sense
        self.solenoid_pin = solenoid_pin
        self.red_pin = red_pin
        self.green_pin = green_pin
        self.blue_pin = blue_pin
        
        # Whether to reward
        self.reward_armed = False
        
        # Whether to autopoke
        self.rt = None
        
        ## Set up lists of handles to call on events
        self.handles_poke_in = []
        self.handles_poke_out = []
        self.handles_reward = []
        
        # Set up pig direction
        # TODO: use locks in these functions
        self.pig.set_mode(self.poke_pin, pigpio.INPUT)
        self.pig.set_mode(self.solenoid_pin, pigpio.OUTPUT)
        self.pig.set_mode(self.red_pin, pigpio.OUTPUT)
        self.pig.set_mode(self.green_pin, pigpio.OUTPUT)
        self.pig.set_mode(self.blue_pin, pigpio.OUTPUT)
        
        # Set up pig call backs
        if poke_sense:
            self.pig.callback(self.poke_pin, pigpio.RISING_EDGE, self.poke_in) 
        else:
            self.pig.callback(self.poke_pin, pigpio.FALLING_EDGE, self.poke_in) 
    
    def autopoke_start(self, rate=0.5, interval=0.1):
        """Create spurious pokes at a rate of `rate` per second.
        
        rate : float
            Expected rate of pokes
        interval : float
            How often the timer is called, in seconds. Higher numbers offer more 
            precision but take more processing time.
        """
        # Calculate the probability to use to achieve the rate
        prob = rate * interval
        
        # Set up a RepeatedTimer to run every `interval` seconds
        self.rt = RepeatedTimer(interval, self._autopoke, prob=prob)
    
    def autopoke_stop(self):
        if self.rt is not None:
            self.rt.stop()
    
    def _autopoke(self, prob=1):
        self.logger.debug('autopoke')
        if np.random.random() < prob:
            self.poke_in()
    
    def reward(self, duration=.050):
        """Open the solenoid valve for port to deliver reward
        *port : port number to be rewarded (1,2,3..etc.)
        *reward_value: how long the valve should be open (in seconds) [imported from task parameters sent to the pi] 
        """
        # TODO: thread this instead of sleeping
        #self.pig.write(valve_l, 1) # Opening valve
        time.sleep(duration)
        #self.pig.write(valve_l, 0) # Closing valve
        self.logger.info('reward delivered')
    
    def poke_in(self):
        # Get time right away
        dt_now = datetime.datetime.now()
        
        # Determine whether to reward
        # If so, immediately disarm
        # TODO: use lock here to prevent multiple rewards
        if self.reward_armed:
            self.reward_armed = False
            do_reward = True
        else:
            do_reward = False
        
        # Any handles associated with pokes
        # This almost always includes HardwareController.report_poke
        for handle in self.handles_poke_in:
            handle(self.name, dt_now)

        if do_reward:
            # Actually deliver the reward
            self.reward()
            
            # Any handles associated with reward
            # This almost always includes HardwareController.report_reward
            for handle in self.handles_reward:
                handle(self.name, dt_now)

        self.logger.info('poke detected')

    def poke_out(self):
        # Handle the pokes
        for handle in self.handles_poke_out:
            handle(self.name, dt_now)        

    def start_flashing(self, led_pin, pwm_frequency=1, pwm_duty_cycle=50):
        # Writing to the LED pin such that it blinks acc to the parameters 
        self.pig.set_mode(led_pin, pigpio.OUTPUT)
        self.pig.set_PWM_frequency(led_pin, pwm_frequency)
        self.pig.set_PWM_dutycycle(led_pin, pwm_duty_cycle)

class HardwareController(object):
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
    def __init__(self, pins, params, start_networking=True, dummy_sound_queuer=False):
        """Initialize a new HardwareController
        
        Arguments
        ---------
        pins : dict
            Data about pin numbers. Loaded from a pins json. 
            Keys:
                left_nosepoke, right_nosepoke : input pin for poke
                left_led_{red|green|blue}, right_led_{red|green|blue}:
                    LED output pins
                left_solenoid, right_solenoid : solenoid output pins
                TODO: are these BOARD or BCM?
        params : dict
            Data about pi parameters. Loaded from a params json. 
            Keys:
                identity : str
                    The name of this pi. Must match what the GUI is waiting for.
            TODO: document rest of keys
        start_networking : bool
            If False, don't use any networking
            This was only for troubleshooting. TODO: remove?
        dummy_sound_queuer : bool
            If True, use a dummy queuer that never provides any audio
            TODO: remove?
        """
        ## Init logger
        self.logger = NonRepetitiveLogger("test")
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.INFO)
        
        
        ## Set attributes
        # Store received parameters
        self.pins = pins
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
        
        
        ## Set up networking
        if start_networking:
            # Instantiates self.network_communicator
            # This will also connect to the GUI
            self.network_communicator = networking.NetworkCommunicator(
                identity=self.params['identity'], 
                pi_identity=self.params['identity'], 
                gui_ip=self.params['gui_ip'], 
                poke_port=self.params['poke_port'], 
                config_port=self.params['config_port'],
                )
            
            # Set up hooks
            self.network_communicator.command2method['set_trial_parameters'] = (
                self.set_trial_parameters)
            self.network_communicator.command2method['stop'] = (
                self.stop_session)
            self.network_communicator.command2method['exit'] = (
                self.exit)            
        
        else:
            self.network_communicator = None

        
        ## Set up nosepokes
        # TODO: don't activate callbacks until explicitly told to do so
        # Init left nosepoke
        self.left_nosepoke = Nosepoke(
            name=self.left_port_name,
            pig=self.pig,
            poke_pin=self.pins['left_nosepoke'], 
            poke_sense=True, 
            solenoid_pin=self.pins['left_solenoid'],
            red_pin=self.pins['left_led_red'], 
            green_pin=self.pins['left_led_green'], 
            blue_pin=self.pins['left_led_blue'], 
            )
        
        # Init right_nosepoke
        self.right_nosepoke = Nosepoke(
            name=self.right_port_name,
            pig=self.pig,
            poke_pin=self.pins['right_nosepoke'], 
            poke_sense=True, 
            solenoid_pin=self.pins['right_solenoid'],
            red_pin=self.pins['right_led_red'], 
            green_pin=self.pins['right_led_green'], 
            blue_pin=self.pins['right_led_blue'], 
            )            

        # Hook up the poke in and reward callbacks
        # TODO: add these to a start_session() method that is called upon
        # set_trial_parameters(), and add the reverse to a stop_session()
        # TODO: add a callback that terminates the audio upon reward
        # TODO: add a callback that plays an error sound upon incorrect poke
        self.left_nosepoke.handles_poke_in.append(self.report_poke)
        self.left_nosepoke.handles_reward.append(self.report_reward)
        self.right_nosepoke.handles_poke_in.append(self.report_poke)
        self.right_nosepoke.handles_reward.append(self.report_reward)
        
        
        ## Autopoke
        self.left_nosepoke.autopoke_start()
        self.right_nosepoke.autopoke_start()
    
    def set_trial_parameters(self, **msg_params):
        """Called upon receiving set_trial_parameters from GUI
        
        """
        self.logger.debug(f'setting trial parametesr: {msg_params}')
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
        # TODO: disable nosepokes here
        
        # Empty the queue of sound
        self.sound_queuer.empty_queue()

    def exit(self):
        """Shut down objects"""
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
            while True:
                # Used to continuously add frames of sound to the 
                # queue until the program stops
                self.sound_queuer.append_sound_to_queue_as_needed()
                
                # Check poke_socket for incoming messages about exit, stop,
                # start, reward, etc
                if self.network_communicator is not None:
                    self.network_communicator.check_socket()
                
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
