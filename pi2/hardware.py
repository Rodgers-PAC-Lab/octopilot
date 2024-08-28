import time
import pigpio
import zmq
from . import sound
from . import networking
from logging_utils.logging_utils import NonRepetitiveLogger
import logging
import numpy as np

## TODO: all of these should be in class Nosepoke, and HC should have a nosepoke
# Callback functions for nosepoke pin (When the nosepoke is detected)
# Poke at Left Port 
def poke_detectedL(pin, level, tick): 
    global count, left_poke_detected, current_port_poked
    count += 1
    left_poke_detected = True
    print("Poke Completed (Left)")
    print("Poke Count:", count)
    nosepoke_idL = nosepoke_pinL  # Set the left nosepoke_id here according to the pi 
    current_port_poked = nosepoke_idL
    
    # Making red LED turn on when a poke is detected for troubleshooting
    pig.set_mode(led_red_l, pigpio.OUTPUT)
    if params['nosepokeL_type'] == "901":
        pig.write(led_red_l, 0)
    elif params['nosepokeL_type'] == "903":
        pig.write(led_red_l, 1)
        
    # Sending nosepoke_id to the GUI wirelessly
    try:
        print(f"Sending nosepoke_id = {nosepoke_idL}") 
        poke_socket.send_string(str(nosepoke_idL))
    except Exception as e:
        print("Error sending nosepoke_id:", e)

# Poke at Right Port
def poke_detectedR(pin, level, tick): 
    global count, right_poke_detected, current_port_poked
    count += 1
    right_poke_detected = True
    print("Poke Completed (Right)")
    print("Poke Count:", count)
    nosepoke_idR = nosepoke_pinR  # Set the right nosepoke_id here according to the pi
    current_port_poked = nosepoke_idR
    
    # Making red LED turn on when a poke is detected for troubleshooting
    pig.set_mode(led_red_r, pigpio.OUTPUT)
    if params['nosepokeR_type'] == "901":
        pig.write(led_red_r, 0)
    elif params['nosepokeR_type'] == "903":
        pig.write(led_red_r, 1)

    # Sending nosepoke_id to the GUI wirelessly
    try:
        print(f"Sending nosepoke_id = {nosepoke_idR}") 
        poke_socket.send_string(str(nosepoke_idR))
    except Exception as e:
        print("Error sending nosepoke_id:", e)

# Callback function for nosepoke pin (When the nosepoke is completed)
def poke_inL(pin, level, tick):
    global left_poke_detected
    if left_poke_detected:
        # Write to left pin
        print("Left poke detected!")
        pig.set_mode(led_red_l, pigpio.OUTPUT)
        if params['nosepokeL_type'] == "901":
            pig.write(led_red_l, 1)
        elif params['nosepokeL_type'] == "903":
            pig.write(led_red_l, 0)
    # Reset poke detected flags
    left_poke_detected = False

# Callback function for nosepoke pin (When the nosepoke is completed)
def poke_inR(pin, level, tick):
    global right_poke_detected
    if right_poke_detected:
        # Write to right pin
        print("Right poke detected!")
        pig.set_mode(led_red_r, pigpio.OUTPUT)
        if params['nosepokeR_type'] == "901":
            pig.write(led_red_r, 1)
        elif params['nosepokeR_type'] == "903":
            pig.write(led_red_r, 0)
            
    # Reset poke detected flags
    right_poke_detected = False

def open_valve(port):
    """Open the solenoid valve for port to deliver reward
    *port : port number to be rewarded (1,2,3..etc.)
    *reward_value: how long the valve should be open (in seconds) [imported from task parameters sent to the pi] 
    """
    reward_value = config_data['reward_value']
    if port == int(nosepoke_pinL):
        pig.set_mode(valve_l, pigpio.OUTPUT)
        pig.write(valve_l, 1) # Opening valve
        time.sleep(reward_value)
        pig.write(valve_l, 0) # Closing valve
    
    if port == int(nosepoke_pinR):
        pig.set_mode(valve_r, pigpio.OUTPUT)
        pig.write(valve_r, 1)
        time.sleep(reward_value)
        pig.write(valve_r, 0)

# This uses functions defined above
def set_up_pig(pig, pins):
    """Connect callbacks to pins
    
    Connects the following events to the following functions
        nosepoke_l falling : poke_inL
        nosepoke_l rising : poke_detectedL
        nosepoke_r falling : poke_inR
        nosepoke_r rising : poke_detectedR
    
    The poke_detected is called when the poke starts
    And the poke_in is called when the poke ends
    
    TODO: this should be set by type 901 or 903
    """
    pig.callback(pins['nosepoke_l'], pigpio.FALLING_EDGE, poke_inL) 
    pig.callback(pins['nosepoke_l'], pigpio.RISING_EDGE, poke_detectedL) 
    pig.callback(pins['nosepoke_r'], pigpio.FALLING_EDGE, poke_inR)
    pig.callback(pins['nosepoke_r'], pigpio.RISING_EDGE, poke_detectedR)


## MAIN LOOP
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


        ## Init logger
        self.logger = NonRepetitiveLogger("test")
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.INFO)
    
    def set_up_dio(self):
        """Set up output DIO lines as OUTPUT
        
        TODO: add all pins not just blue ones
        """
        self.pig.set_mode(self.pins['led_blue_l'], pigpio.OUTPUT)
        self.pig.set_mode(self.pins['led_blue_r'], pigpio.OUTPUT)        
    
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

    def start_flashing(self, led_pin, pwm_frequency=1, pwm_duty_cycle=50):
        # Writing to the LED pin such that it blinks acc to the parameters 
        self.pig.set_mode(led_pin, pigpio.OUTPUT)
        self.pig.set_PWM_frequency(led_pin, pwm_frequency)
        self.pig.set_PWM_dutycycle(led_pin, pwm_duty_cycle)

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