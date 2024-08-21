import pigpio

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
    
    nosepoke_l falling : poke_inL
    nosepoke_l rising : poke_detectedL
    
    nosepoke_r falling : poke_inR
    nosepoke_r rising : poke_detectedR
    """
    # Excutes when there is a falling edge on the voltage of the pin (when poke is completed)
    pig.callback(pins['nosepoke_l'], pigpio.FALLING_EDGE, poke_inL) 

    # Executes when there is a rising edge on the voltage of the pin (when poke is detected) 
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
    def __init__(self, pins, params):
        # Store received parameters
        self.pins = pins
        self.params = params

        # Set up pigpio
        # Initialize a pig to use
        self.pig = pigpio.pi()

        # Connect callbacks to pins
        set_up_pi(self.pig, self.pins)
        self.pig.set_mode(led_blue_l, pigpio.OUTPUT)
        self.pig.set_mode(led_blue_r, pigpio.OUTPUT)

        # This object puts frames of audio into a sound queue
        self.sound_queuer = sound.SoundQueuer()
        
        # This object pulls frames of audio from that queue and gives them
        # to a jack.Client that it contains
        # TODO: probably instantiate the jack.Client here and provide it
        self.sound_player = sound.SoundPlayer(
            name='sound_player', 
            sound_queue=self.sound_queuer.sound_queue,
            )
    
    def set_up_networking(self):
        ## Set up networking
        self.poke_socket = networking.set_up_poke_socket()
        self.json_socket = networking.set_up_json_socket()

        # Creating a poller object for both sockets that will be used to 
        # continuously check for incoming messages
        self.poller = zmq.Poller()
        self.poller.register(self.poke_socket, zmq.POLLIN)
        self.poller.register(self.json_socket, zmq.POLLIN)        

    def flash():
        """Flash the blue LEDs whenever a trial is completed"""
        self.pig.write(self.pins['led_blue_l'], 1) # Turning LED on
        self.pig.write(self.pins['led_blue_r'], 1) 
        time.sleep(0.5)
        self.pig.write(self.pins['led_blue_l'], 0) # Turning LED off
        self.pig.write(self.pins['led_blue_r'], 0) 
    
    def stop_session():
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

    def set_acoustic_parameters(**acoustic_kwargs):
        """Use config_data to update acoustic parameters on sound_queuer
        
        Sends acoustic_kwargs to self.sound_queuer
        Then calls set_sound_cycle
        """
        # Update the Sound Queue with the new acoustic parameters
        self.sound_queuer.set_parameters(**acoustic_kwargs)
        
        # Update the sound cycle
        self.sound_queuer.set_sound_cycle()

    def start_flashing(pig, led_pin, pwm_frequency=1, pwm_duty_cycle=50)
        # Writing to the LED pin such that it blinks acc to the parameters 
        pig.set_mode(led_pin, pigpio.OUTPUT)
        pig.set_PWM_frequency(led_pin, pwm_frequency)
        pig.set_PWM_dutycycle(led_pin, pwm_duty_cycle)

    def handle_reward_port_message(msg):
        ## This specifies which port to reward
        # Debug print
        print(msg)
        
        # Extract the integer part from the message
        msg_parts = msg.split()
        if len(msg_parts) != 3 or not msg_parts[2].isdigit():
            print("Invalid message format.")
            continue
        
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
        
    def reward_and_end_trial(sound_queuer, poke_socket):
        # This seems to occur when the GUI detects that the poked
        # port was rewarded. This will be too slow. The reward port
        # should be opened if it knows it is the rewarded pin. 
        # Tried to implement this logic within the Pi itself. 
        # Can work on it more if needed
        
        # Emptying the queue completely
        sound_queuer.running = False
        sound_queuer.set_channel('none')
        sound_queuer.empty_queue()

        # Flashing all lights and opening Solenoid Valve
        flash()
        open_valve(prev_port)
        
        # Updating all the parameters that will influence the next trial
        sound_queuer.update_parameters(
            rate_min, rate_max, irregularity_min, irregularity_max, 
            amplitude_min, amplitude_max, center_freq_min, center_freq_max, 
            bandwidth)
        poke_socket.send_string(
            sound_queuer.update_parameters.parameter_message)
        
        # Turn off the currently active LED
        if current_led_pin is not None:
            pig.write(current_led_pin, 0)
            print("Turning off currently active LED.")
            current_led_pin = None  # Reset the current LED
        else:
            print("No LED is currently active.")

    def handle_message_on_poke_socket(msg, poke_socket, sound_queuer, sound_player):
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
            sound_player.client.deactivate()
            
            # Exit the loop
            stop_running = True  
        
        elif msg == 'stop':
            # Receiving message from the GUI to stop the current session 
            # Stopping all currently active elements and waiting for next session to start
            stop_session()
            
            # Sending stop signal wirelessly to stop update function
            try:
                poke_socket.send_string("stop")
            except Exception as e:
                print("Error stopping session", e)

            print("Stop command received. Stopping sequence.")
            continue

        elif msg == 'start':
            # Communicating with start button to start the next session
            try:
                poke_socket.send_string("start")
            except Exception as e:
                print("Error stopping session", e)
        
        elif msg.startswith("Reward Port:"):    
            handle_reward_port_message(msg)

        elif msg.startswith("Reward Poke Completed"):
            reward_and_end_trial(sound_queuer, poke_socket)
       
        else:
            print("Unknown message received:", msg)

        return stop_running

    def check_json_socket(self):
        ## Check for incoming messages on json_socket
        if json_socket in socks and socks[json_socket] == zmq.POLLIN:
            # If so, use it to update the acoustic parameters
            # Setting up json socket to wait to receive messages from the GUI
            json_data = json_socket.recv_json()

            # Deserialize JSON data
            config_data = json.loads(json_data)
            
            # Use that data to update parameters in sound_queuer
            update_sound_queuer(config_data, sound_queuer, sound_player)        

    def check_poke_socket(self):
        ## Check for incoming messages on poke_socket
        if poke_socket in socks and socks[poke_socket] == zmq.POLLIN:
            # Waiting to receive message strings that control the main loop
            msg = poke_socket.recv_string()  
    
            self.stop_running = handle_message_on_poke_socket(
                msg, poke_socket, sound_queuer, sound_player)        

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
            while True:
                # Wait for events on registered sockets. 
                # Currently polls every 100ms to check for messages 
                socks = dict(poller.poll(100))
                
                # Used to continuously add frames of sound to the 
                # queue until the program stops
                self.sound_queuer.append_sound_to_queue_as_needed()
                
                # Check json_socket for incoming messages about acoustic
                # parameters
                self.check_json_socket()
                
                # Check poke_socket for incoming messages about exit, stop,
                # start, reward, etc
                self.check_poke_socket()
                
                # Check if stop_runnning was set by check_poke_socket
                if self.stop_running:
                    break

        except KeyboardInterrupt:
            # Stops the pigpio connection
            pig.stop()

        finally:
            ## QUITTING ALL NETWORK AND HARDWARE PROCESSES    
            # Close all sockets and contexts
            poke_socket.close()
            poke_context.term()
            json_socket.close()
            json_context.term()
