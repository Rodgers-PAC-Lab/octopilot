import pigpio
import time
from . import sound
from . import networking

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

        # This object puts frames of audio into a sound queue
        if dummy_sound_queuer:
            self.sound_queuer = sound.DummySoundQueuer()
        else:
            # TODO: tell sound_queuer to start providing silence
            self.sound_queuer = sound.SoundQueuer()
        
        # This object pulls frames of audio from that queue and gives them
        # to a jack.Client that it contains
        # TODO: probably instantiate the jack.Client here and provide it
        # Note that it will immediately start asking for frames of audio, but
        # sound_queuer doesn't have anything to play yet
        self.sound_player = sound.SoundPlayer(
            name='sound_player', 
            sound_queue=self.sound_queuer.sound_queue,
            )
        
        # Set up networking
        if start_networking:
            self.set_up_networking()
        else:
            self.network_communicator = None
    
    def set_up_dio(self):
        """Set up output DIO lines as OUTPUT
        
        TODO: add all pins not just blue ones
        """
        self.pig.set_mode(self.pins['led_blue_l'], pigpio.OUTPUT)
        self.pig.set_mode(self.pins['led_blue_r'], pigpio.OUTPUT)        
    
    def set_up_networking(self):
        ## Set up networking
        self.network_communicator = networking.NetworkCommunicator(
            identity=self.params['identity'], 
            pi_identity=self.params['identity'], 
            gui_ip=self.params['gui_ip'], 
            poke_port=self.params['poke_port'], 
            config_port=self.params['config_port'],
            )

    def flash(self):
        """Flash the blue LEDs whenever a trial is completed"""
        self.pig.write(self.pins['led_blue_l'], 1) # Turning LED on
        self.pig.write(self.pins['led_blue_r'], 1) 
        time.sleep(0.5)
        self.pig.write(self.pins['led_blue_l'], 0) # Turning LED off
        self.pig.write(self.pins['led_blue_r'], 0) 
    
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
        self.pig.write(pins['led_red_l'], 0)
        self.pig.write(pins['led_red_r'], 0)
        self.pig.write(pins['led_green_l'], 0)
        self.pig.write(pins['led_green_r'], 0)
        
        # Empty the queue of sound
        self.sound_queuer.empty_queue()

    def set_acoustic_parameters(self, **acoustic_kwargs):
        """Use config_data to update acoustic parameters on sound_queuer
        
        Sends acoustic_kwargs to self.sound_queuer
        Then calls set_sound_cycle
        """
        # Update the Sound Queue with the new acoustic parameters
        self.sound_queuer.set_parameters(**acoustic_kwargs)
        
        # Update the sound cycle
        self.sound_queuer.set_sound_cycle()

    def start_flashing(self, led_pin, pwm_frequency=1, pwm_duty_cycle=50):
        # Writing to the LED pin such that it blinks acc to the parameters 
        self.pig.set_mode(led_pin, pigpio.OUTPUT)
        self.pig.set_PWM_frequency(led_pin, pwm_frequency)
        self.pig.set_PWM_dutycycle(led_pin, pwm_duty_cycle)

    def handle_reward_port_message(self, msg):
        ## This specifies which port to reward
        # Debug print
        print(msg)
        
        # Extract the integer part from the message
        msg_parts = msg.split()
        if len(msg_parts) != 3 or not msg_parts[2].isdigit():
            raise ValueError("Invalid message format: {}".format(msg))
        
        # Assigning the integer part to a variable
        value = int(msg_parts[2])  
        
        # Turn off the previously active LED if any
        if current_led_pin is not None:
            pig.write(current_led_pin, 0)
        
        # Depending on value, either start playing left, start playing right,
        # or 
        if value == int(params['nosepokeL_id']):
            # Start playing and flashing
            start_playing(sound_queuer, 'left')
            start_flashing(pins['led_green_l'])

            # Keep track of which port is rewarded and which pin
            # is rewarded
            prev_port = value
            current_led_pin = pins['led_green_l']

        elif value == int(params['nosepokeR_id']):
            # Start playing and flashing
            start_playing(sound_queuer, 'right')
            start_flashing(led_green_r)
            
            # Keep track of which port is rewarded and which pin
            # is rewarded
            prev_port = value
            current_led_pin = led_pin
        
        else:
            # In what circumstance would this happen?
            # Current Reward Port
            prev_port = value
            print(f"Current Reward Port: {value}")
        
        prev_port = value
        
    def reward_and_end_trial(self, sound_queuer, poke_socket):
        # This seems to occur when the GUI detects that the poked
        # port was rewarded. This will be too slow. The reward port
        # should be opened if it knows it is the rewarded pin. 
        # Tried to implement this logic within the Pi itself. 
        # Can work on it more if needed
        
        # Emptying the queue completely
        self.sound_queuer.running = False
        self.sound_queuer.set_channel('none')
        self.sound_queuer.empty_queue()

        # Flashing all lights and opening Solenoid Valve
        self.flash()
        self.open_valve(prev_port)
        
        # Updating all the parameters that will influence the next trial
        self.sound_queuer.update_parameters(
            rate_min, rate_max, irregularity_min, irregularity_max, 
            amplitude_min, amplitude_max, center_freq_min, center_freq_max, 
            bandwidth)
        self.networking_communicator.poke_socket.send_string(
            self.sound_queuer.update_parameters.parameter_message)
        
        # Turn off the currently active LED
        if current_led_pin is not None:
            pig.write(current_led_pin, 0)
            print("Turning off currently active LED.")
            current_led_pin = None  # Reset the current LED
        else:
            print("No LED is currently active.")

    def handle_message_on_poke_socket(self, msg, poke_socket, sound_queuer, sound_player):
        """Handle a message received on poke_socket
        
        poke_socket handles messages received from the GUI that are used 
        to control the main loop. 
        The functions of the different messages are as follows:
        'exit' : terminates the program completely whenever received and 
            closes it on all Pis for a particular box
        'stop' : stops the current session and sends a message back to the 
            GUI to stop plotting. The program waits until it can start next session 
        'start' : used to start a new session after the stop message pauses 
            the main loop
        'Reward Port' : this message is sent by the GUI to set the reward port 
            for a trial.
        The Pis will receive messages of ports of other Pis being set as the 
            reward port, however will only continue if the message contains 
            one of the ports listed in its params file
        'Reward Poke Completed' : Currently 'hacky' logic used to signify the 
            end of the trial. If the string sent to the GUI matches the 
            reward port set there it clears all sound parameters and opens 
            the solenoid valve for the assigned reward duration. The LEDs 
            also flash to show a trial was completed 
        """
        stop_running = False
        
        # Different messages have different effects
        if msg == 'exit': 
            # Condition to terminate the main loop
            stop_session()
            print("Received exit command. Terminating program.")
            
            # Deactivating the Sound Player before closing the program
            self.sound_player.client.deactivate()
            
            # Exit the loop
            stop_running = True  
        
        elif msg == 'stop':
            # Receiving message from the GUI to stop the current session 
            # Stopping all currently active elements and waiting for next session to start
            stop_session()
            
            # Sending stop signal wirelessly to stop update function
            try:
                self.network_communicator.poke_socket.send_string("stop")
            except Exception as e:
                print("Error stopping session", e)

            print("Stop command received. Stopping sequence.")
            stop_running = True

        elif msg == 'start':
            # Communicating with start button to start the next session
            try:
                self.network_communicator.poke_socket.send_string("start")
            except Exception as e:
                print("Error stopping session", e)
        
        elif msg.startswith("Reward Port:"):    
            handle_reward_port_message(msg)

        elif msg.startswith("Reward Poke Completed"):
            reward_and_end_trial(
                self.sound_queuer, 
                self.network_communicator.poke_socket,
                )
       
        else:
            print("Unknown message received:", msg)

        return stop_running

    def check_json_socket(self, socks):
        ## Check for incoming messages on json_socket
        if self.network_communicator.json_socket in socks and socks[self.network_communicator.json_socket] == zmq.POLLIN:
            # If so, use it to update the acoustic parameters
            # Setting up json socket to wait to receive messages from the GUI
            json_data = self.network_communicator.json_socket.recv_json()

            # Deserialize JSON data
            config_data = json.loads(json_data)
            
            # Use that data to update parameters in sound_queuer
            update_sound_queuer(
                config_data, 
                self.sound_queuer, 
                self.sound_player,
                )

    def check_poke_socket(self, socks):
        ## Check for incoming messages on poke_socket
        if self.network_communicator.poke_socket in socks and socks[self.network_communicator.poke_socket] == zmq.POLLIN:
            # Waiting to receive message strings that control the main loop
            msg = self.network_communicator.poke_socket.recv_string()  
    
            self.stop_running = handle_message_on_poke_socket(
                msg, 
                self.network_communicator.poke_socket, 
                self.sound_queuer, 
                self.sound_player)        

    def main_loop(self):
        """Loop forever until told to stop, then exit
        
        """
        try:
            ## TODO: document these variables and why they are tracked
            # Initialize led_pin to set what LED to write to
            self.led_pin = None
            
            # Variable used to track the pin of the currently blinking LED 
            self.current_led_pin = None  
            
            # Tracking the reward port for each trial; does not update 
            # until reward is completed 
            self.prev_port = None
            
            
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
                
                # Check json_socket for incoming messages about acoustic
                # parameters
                if self.network_communicator is not None:
                    self.check_json_socket(socks)
                
                # Check poke_socket for incoming messages about exit, stop,
                # start, reward, etc
                if self.network_communicator is not None:
                    self.check_poke_socket(socks)
                
                # Check if stop_runnning was set by check_poke_socket
                if self.stop_running:
                    break
                
                # If there's nothing in the main loop, not even a sleep,
                # then for some reason this leads to XRun errors
                # Perhaps the interpreter is optimizing away the mainloop
                # time.sleep(0) prevents this from happening
                time.sleep(0)

        except KeyboardInterrupt:
            print('KeyboardInterrupt received, shutting down')
            
        finally:
            ## QUITTING ALL NETWORK AND HARDWARE PROCESSES    
            # Stop jack
            self.sound_player.client.close()
            
            # Stops the pigpio connection
            self.pig.stop()
            
            # Close all sockets and contexts
            if self.network_communicator is not None:
                self.network_communicator.close()
