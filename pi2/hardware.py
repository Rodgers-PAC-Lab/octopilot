import time
import pigpio
import zmq
from . import sound
from . import networking
from logging_utils.logging_utils import NonRepetitiveLogger
import logging
import numpy as np

class Nosepoke(object):
    def __init__(self, name, poke_pin, poke_sense, solenoid_pin, 
        red_pin, green_pin, blue_pin):
        """Init a new Nosepoke"""
        self.name
        self.poke_pin = poke_pin
        self.poke_sense = poke_sense
        self.red_pin = red_pin
        self.green_pin = green_pin
        self.blue_pin = blue_pin
        
        self.handles_poke_in = []
        self.handles_poke_out = []
        self.handles_reward = []
        
        # Set up pig direction
        pigpio.set_mode(self.poke_pin, pigpio.INPUT)
        pigpio.set_mode(self.solenoid_pin, pigpio.OUTPUT)
        pigpio.set_mode(self.red_pin, pigpio.OUTPUT)
        pigpio.set_mode(self.green_pin, pigpio.OUTPUT)
        pigpio.set_mode(self.blue_pin, pigpio.OUTPUT)
        
        # Set up pig call backs
        if poke_sense:
            pig.callback(self.poke_pin, pigpio.RISING_EDGE, self.poke_in) 
        else:
            pig.callback(self.poke_pin, pigpio.FALLING_EDGE, self.poke_in) 
    
    def reward(self, duration=.050):
        """Open the solenoid valve for port to deliver reward
        *port : port number to be rewarded (1,2,3..etc.)
        *reward_value: how long the valve should be open (in seconds) [imported from task parameters sent to the pi] 
        """
        # TODO: thread this instead of sleeping
        pig.write(valve_l, 1) # Opening valve
        time.sleep(duration)
        pig.write(valve_l, 0) # Closing valve
    
    def poke_in(self):
        dt_now = datetime.datetime.now()
        
        # Determine whether to reward
        # TODO: use lock here to prevent multiple rewards
        do_reward = False
        if self.reward_armed:
            self.reward_armed = False
            do_reward = True
        
        # Handle the pokes
        for handle in self.handles_poke_in:
            handle(self.name, dt_now)

        # The actual reward is slow so do it last
        if do_reward:
            for handle in self.handles_reward:
                handle(self.name, dt_now)

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
    def __init__(self, pins, params, start_networking=False, dummy_sound_queuer=False):
        # Store received parameters
        self.pins = pins
        self.params = params

        # Set up pigpio
        # Initialize a pig to use
        self.pig = pigpio.pi()

        # Connect callbacks to pins
        set_up_pig(self.pig, self.pins)
        self.set_up_dio()

        # Name my ports
        # TODO: take this from params
        self.identity = self.params['identity']
        self.left_port_name = f'{identity}_L'
        self.right_port_name = f'{identity}_R'

        # This object generates frames of audio
        # TODO: figure out whether to init sound_chooser first (in 
        # which case how to know blocksize?) or init sound_player first
        # (in which case it needs to be ready to go without sound_chooser)
        # I think the best thing to do is store blocksize and fs in
        # params, and use that also to start jackd
        self.sound_chooser = sound.SoundChooser_IntermittentBursts(
            blocksize=1024,
            fs=192000,
            )
        
        # Set
        self.sound_chooser.set_audio_parameters(
            left_params={'silenced': True,}, right_params={'silenced': True},
            )
        
        # This object uses those frames to top up sound_player
        self.sound_queuer = sound.SoundQueuer(
            sound_chooser=self.sound_chooser)
        
        # This is used to know if the sesion is running (e.g. if any
        # trial parameters have ever been sent
        self.session_is_running = False
        
        # Fill the queue before we instantiate sound_player
        self.sound_queuer.append_sound_to_queue_as_needed()
        
        # This object pulls frames of audio from that queue and gives them
        # to a jack.Client that it contains
        # TODO: probably instantiate the jack.Client here and provide it
        # Note that it will immediately start asking for frames of audio, but
        # sound_queuer doesn't have anything to play yet
        self.sound_player = sound.SoundPlayer(
            name='sound_player', 
            sound_queuer=self.sound_queuer,
            )
        
        # Set up networking
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
        else:
            self.network_communicator = None

        # Set up nosepokes
        # TODO: don't activate callbacks until explicitly told to do so
        self.left_nosepoke = Nosepoke(
            name=self.left_port_name,
            poke_pin=self.pins['left_nosepoke'], 
            poke_sense=True, 
            solenoid_pin=self.pins['left_solenoid'],
            red_pin=self.pins['left_led_red'], 
            green_pin=self.pins['left_led_green'], 
            blue_pin=self.pins['left_led_blue'], 
            )
        
        self.left_nosepoke.handles_poke_in.append(self.report_poke)
        self.left_nosepoke.handles_reward.append(self.report_reward)
        
        self.right_nosepoke = Nosepoke(
            name=self.right_port_name,
            poke_pin=self.pins['right_nosepoke'], 
            poke_sense=True, 
            solenoid_pin=self.pins['right_solenoid'],
            red_pin=self.pins['right_led_red'], 
            green_pin=self.pins['right_led_green'], 
            blue_pin=self.pins['right_led_blue'], 
            )            

        self.right_nosepoke.handles_poke_in.append(self.report_poke)
        self.right_nosepoke.handles_reward.append(self.report_reward)


        ## Init logger
        self.logger = NonRepetitiveLogger("test")
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.INFO)
    
    def stop_session(self):
        """Runs when a session is stopped
        
        Flow
        ----
        * It turns off all active LEDs, 
        * resets all the variables used for tracking to None, 
        * stops playing sound,
        * and empties the queue.
        """
        # Flash
        self.flash()
        
        # Reset flags
        self.current_led_pin = None
        self.prev_port = None
        
        # Turn off pins
        self.pig.write(self.pins['led_red_l'], 0)
        self.pig.write(self.pins['led_red_r'], 0)
        self.pig.write(self.pins['led_green_l'], 0)
        self.pig.write(self.pins['led_green_r'], 0)
        
        # Empty the queue of sound
        self.sound_queuer.empty_queue()

    def handle_reward(self):
        # TODO: open valve here
        
        # Silence sound generation
        self.sound_chooser.set_audio_parameters(
            left_params={'silenced': True},
            right_params={'silenced': True},
            )
        
        # Empty the queue of already generated sound
        self.sound_queuer.empty_queue()        
    
    def check_if_session_is_running(self):
        return self.session_is_running

    def main_loop(self):
        """Loop forever until told to stop, then exit
        
        """
        try:
            ## Loop forever
            self.stop_running = False
            print('starting mainloop')
            
            while True:
                # Wait for events on registered sockets. 
                # Currently polls every 100ms to check for messages 
                if self.network_communicator is not None:
                    socks = dict(self.network_communicator.poller.poll(100))
                
                # Used to continuously add frames of sound to the 
                # queue until the program stops
                self.sound_queuer.append_sound_to_queue_as_needed()
                
                # Check poke_socket for incoming messages about exit, stop,
                # start, reward, etc
                if self.network_communicator is not None:
                    self.check_poke_socket(socks)
                
                # Check if stop_runnning was set by check_poke_socket
                if self.stop_running:
                    break
                
                # Randomly send messages
                # TODO: move this to Nosepoke
                if self.check_if_session_is_running():
                    if np.random.random() < 0.1:
                        choose_poke = random.choice(
                            [self.left_port_name, self.right_port_name])
                        self.network_communicator.poke_socket.send_string(
                            f'poke;{choose_poke}')
                        if choose_poke == self.rewarded_port:
                            self.network_communicator.poke_socket.send_string(
                                f'reward;{choose_poke}')
                        
                        time.sleep(.1)
                else:
                    self.logger.info('waiting for session to start')
                
                
                # If there's nothing in the main loop, not even a sleep,
                # then for some reason this leads to XRun errors
                # Perhaps the interpreter is optimizing away the mainloop
                # time.sleep(0) prevents this from happening
                time.sleep(0)

        except KeyboardInterrupt:
            print('KeyboardInterrupt received, shutting down')
            
        finally:
            ## QUITTING ALL NETWORK AND HARDWARE PROCESSES    
            # Deactivating the Sound Player before closing the program
            self.sound_player.client.deactivate()
            
            # Stop jack
            self.sound_player.client.close()
            
            # Stops the pigpio connection
            self.pig.stop()
            
            # Close all sockets and contexts
            if self.network_communicator is not None:
                self.network_communicator.close()
