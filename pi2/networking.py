"""Functions to set up networking

In order to communicate with the GUI, we create two sockets: 
    poke_socket and json_socket
Both these sockets use different ZMQ contexts and are used in different 
parts of the code, this is why two network ports need to be used 
    * poke_socket: Used to send and receive poke-related information.
        - Sends: Poked Port, Poke Times 
        - Receives: Reward Port for each trial, Commands to Start/Stop the 
        session, Exit command to end program
    * json_socket: Used to strictly receive task parameters from the GUI 
    (so that audio parameters can be set for each trial)
"""

import zmq


## This class is instantiated by HardwareController
class NetworkCommunicator(object):
    """Handles communication with GUI
    
    Methods
    -------
    __init__ : Calls set_up_poke_socket and also creates a Poller and registers
        sockets with it
    set_up_poke_socket : Creates sockets and connects to the GUI
    """
    def __init__(self, identity, pi_identity, gui_ip, poke_port, config_port):
        """Init a new NetworkCommunicator
        
        This object will communicate with the GUI using a DEALER socket called
        poke_socket and a SUB socket called json_socket. The SUB socket
        can only receive information. The DEALER socket can only send 
        information (??)
        
        Arguments
        ---------
        identity : str
        pi_identity : str
            TODO: how does this differ from identity?
        gui_ip : str
            IP address of GUI
        poke_port : str
        config_port : str
        
        Flow
        ----
        * Set up self.poke_socket. This also sends a message to the GUI.
        * Set up self.poller and register the scokets.
        """
        # Store required arguments
        self.pi_identity = pi_identity
        self.gui_ip = gui_ip
        self.poke_port = poke_port
        self.identity = identity
        self.config_port = config_port

        # Set up sockets
        self.set_up_poke_socket()

        # Creating a poller object for both sockets that will be used to 
        # continuously check for incoming messages
        self.poller = zmq.Poller()
        self.poller.register(self.poke_socket, zmq.POLLIN)
    
    def set_up_poke_socket(self):
        """Create `self.poke_socket` and connect to GUI
        
        Flow
        * Create self.poke_context and self.poke_socket (a zmq.DEALER).
          Identity of self.poke_socket is self.pi_identity
          TODO: what does 'identity' of a socket do?
        * Connect to the router IP by combining GUI IP with poke_port
        * Send our identity to the GUI, which also adds this pi to the GUI's
          list of known identities.
        
        This doesn't appear to be blocking: even if there is nothing running
        on the GUI computer, this function will successfully complete.
        """
        ## Create socket
        # Creating a DEALER socket for communication regarding poke and poke times
        self.poke_context = zmq.Context()
        self.poke_socket = self.poke_context.socket(zmq.DEALER)

        # Setting the identity of the socket in bytes
        self.poke_socket.identity = bytes(f"{self.pi_identity}", "utf-8") 


        ## Connect to the server
        # Connecting to the GUI IP address stored in params
        self.router_ip = "tcp://" + f"{self.gui_ip}" + f"{self.poke_port}" 
        self.poke_socket.connect(self.router_ip) 

        # Send the identity of the Raspberry Pi to the server
        self.poke_socket.send_string(f"hello;{self.identity}") 

        # Print acknowledgment
        print(f"Connected to router at {self.router_ip}")  

    def parse_trial_parameters(self, msg):
        """Parse `msg` into left_params and right_params
        
        msg : str
            Should be a list of token separated by semicolons
            Each token should be KEY=VALUE=DTYPE
            where KEY is the key, VALUE is the value, and DTYPE is
            either 'int', 'float', or 'str'
        
        Returns : left_params, right_params, each a dict
        """
        # Parse
        split = msg.replace('set_trial_parameters;', '').split(';')
        params = {}
        for spl in split:
            if spl.strip() == '':
                continue
            
            try:
                key, val, dtyp = spl.strip().split('=')
            except ValueError:
                raise ValueError('unparseable messagse: {}'.format(msg))
            
            try:
                if dtyp == 'int':
                    params[key] = int(val)
                elif dtyp == 'float':
                    params[key] = float(val)
                elif dtyp == 'str':
                    params[key] = val
                elif dtyp == 'bool':
                    params[key] = bool(val)
                else:
                    raise ValueError('unrecognized dtyp: {}'.format(dtyp))
            except ValueError:
                raise ValueError(f'cannot parse: {key}, {val}, {dtyp}')
            
        # Split into left_params and right_params
        left_params = {}
        right_params = {}
        for key, val in params.items():
            if key.startswith('left'):
                left_params[key.replace('left_', '')] = val
            elif key.startswith('right'):
                right_params[key.replace('right_', '')] = val
            else:
                other_params[key] = val
        
        return left_params, right_params, other_params

    def handle_message_on_poke_socket(self, msg, verbose=True):
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
        quit_program = False
        
        self.logger.debug(f'received message: {msg}')
        
        # Different messages have different effects
        if msg == 'exit': 
            # Condition to terminate the main loop
            self.stop_session()
            print("Received exit command. Terminating program.")
            
            # Exit the loop
            stop_running = True
            quit_program = True
        
        elif msg == 'stop':
            # Receiving message from the GUI to stop the current session 
            # Stop all currently active elements and wait for next session
            self.stop_session()
            print("Stop command received. Stopping sequence.")
            
            # Stop running
            stop_running = True

        elif msg.startswith("set_trial_parameters;"):    
            # Log
            self.logger.info(f'trial started: msg={msg}')
            
            # Parse params
            left_params, right_params, other_params = self.parse_trial_parameters(msg)
            
            # Get rewarded port
            # TODO: replace with binary reward or not for several ports
            self.rewarded_port = other_params['rewarded_port']
            
            # Use those params to set the new sounds
            self.sound_chooser.set_audio_parameters(left_params, right_params)
            
            # Empty and refill the queue with new sounds
            self.sound_queuer.empty_queue()
            self.sound_queuer.append_sound_to_queue_as_needed()
            
            # Set session is running if it isn't already
            self.session_is_running = True

        else:
            print("Unknown message received:", msg)

        return stop_running

    def check_poke_socket(self, socks):
        ## Check for incoming messages on poke_socket
        if self.network_communicator.poke_socket in socks and socks[self.network_communicator.poke_socket] == zmq.POLLIN:
            # Waiting to receive message strings that control the main loop
            msg = self.network_communicator.poke_socket.recv_string()  
    
            self.stop_running = self.handle_message_on_poke_socket(msg)

    def close(self):
        """Close all sockets and contexts"""
        self.poke_socket.close()
        
        # Sometimes gets stuck here?
        self.poke_context.term()
