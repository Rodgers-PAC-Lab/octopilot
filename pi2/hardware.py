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

# TODO: document this function
def flash():
    """
    Flashing all the LEDs whenever a trial is completed 
    """
    pig.set_mode(led_blue_l, pigpio.OUTPUT)
    pig.write(led_blue_l, 1) # Turning LED on
    pig.set_mode(led_blue_r, pigpio.OUTPUT)
    pig.write(led_blue_r, 1) 
    time.sleep(0.5)
    pig.write(led_blue_l, 0) # Turning LED off
    pig.write(led_blue_r, 0)  


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