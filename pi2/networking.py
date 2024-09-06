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


The pi can receive the following messages from the GUI:
    set_trial_parameters
    stop
    exit

The pi can send the following messages to the GUI:
    poke
    reward

"""

import zmq
from logging_utils.logging_utils import NonRepetitiveLogger
import logging
import datetime

## This class is instantiated by HardwareController
class NetworkCommunicator(object):
    """Handles communication with GUI
    
    This object sets up sockets to communicate with GUI, receives messages
    from the GUI, and can be set to call specific methods upon receiving
    specific messages.
    
    Generally, this object is instantiated by and contained by a 
    HardwareController, which provides its own methods to be called upon
    receiving specific messages.
    
    This object should focus on network communication (sockets etc) and
    parsing messages, not on task-specific logic. 
    
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
        ## Store required arguments
        self.pi_identity = pi_identity
        self.gui_ip = gui_ip
        self.poke_port = poke_port
        self.identity = identity
        self.config_port = config_port
        

        ## Init logger
        self.logger = NonRepetitiveLogger("test")
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.DEBUG)
        

        ## Set up the method to call on each command
        self.command2method = {}
        

        ## Set up sockets
        self.init_socket()

        # Creating a poller object for both sockets that will be used to 
        # continuously check for incoming messages
        self.poller = zmq.Poller()
        self.poller.register(self.poke_socket, zmq.POLLIN)
    
    def init_socket(self):
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

    def check_socket(self, socks):
        # Get time
        dt_now = datetime.datetime.now().isoformat()
        
        # Check for incoming messages on poke_socket
        self.logger.debug(f'checking poke socket')
        if self.poke_socket in socks and socks[self.poke_socket] == zmq.POLLIN:
            # Waiting to receive message strings that control the main loop
            # Is this blocking?
            # I think the 'if' is only satisfied if there is something to
            # receive, so it doesn't matter if it's blocking
            msg = self.poke_socket.recv_string()  
            
            # Receive message
            self.logger.debug(f'{dt_now} - Received message {msg} on poke socket')
    
            #self.stop_running = self.handle_message_on_poke_socket(msg)

            # Handle message
            self.handle_message(msg)
    
    def handle_message(self, msg):
        """Handle a message received on poke_socket
        
        Arguments
        ---------
        msg : str
            A ';'-separated list of strings
            The first string is the "command"
            The remaining strings should be in the format {KEY}={VALUE}={DTYP}
            The method self.command2method[command] is called with a dict
            of arguments formed from the remaining strings.
        """
        # Log
        self.logger.debug(f'received message: {msg}')
        
        # Split on semicolon
        tokens = msg.strip().split(';')
        
        # The command is the first token
        # This will always run, but command could be ''
        command = tokens[0]
        
        # Get the params
        # This will always run, but could return {}
        msg_params = self.parse_params(tokens[1:])
        
        # Find associated method
        meth = None
        try:
            meth = self.command2method[command]
        except KeyError:
            self.logger.error(
                f'unrecognized command: {command}. '
                f'I only recognize: {list(self.command2method.keys())}'
                )
        
        # Call the method
        if meth is not None:
            self.logger.debug(f'calling method {meth} with params {msg_params}')
            meth(msg_params)

    def parse_params(self, token_l):
        """Parse `token_l` into a dict
        
        Iterates over strings in token_l, parses them as KEY=VALUE=DTYPE,
        and stores in a dict to return. Raises ValueError if unparseable.
        
        TODO: replace this with json
        
        token_l : list
            Each entry should be a str, '{KEY}={VALUE}={DTYPE}'
            where KEY is the key, VALUE is the value, and DTYPE is
            either 'int', 'float', or 'str'
        
        Returns : dict d
            d[KEY] will be VALUE of type DTYPE
        """
        # Parse each token
        params = {}
        for tok in token_l:
            # Strip
            strip_tok = tok.strip()
            split_tok = strip_tok.split('=')
            
            # Skip if empty
            if strip_tok == '':
                # This happens if the message ends with a semicolon,
                # which is fine
                continue
            
            # Error if it's not KEY=VAL=DTYP
            try:
                key, val, dtyp = split_tok
            except ValueError:
                raise ValueError('unparseable token: {}'.format(tok))
            
            # Convert value
            if dtyp == 'int':
                conv_val = int(val)
            elif dtyp == 'float':
                conv_val = float(val)
            elif dtyp == 'str':
                conv_val = val
            elif dtyp == 'bool':
                conv_val = bool(val)
            else:
                # Error if DTYP unrecognized
                raise ValueError('unrecognized dtyp: {}'.format(dtyp))
            
            # Store
            params[key] = conv_val
        
        return params

    def send_goodbye(self):
        """Send goodbye message to GUI
        
        """
        self.logger.info('sending goodbye')
        self.poke_socket.send_string(f"goodbye;{self.identity}") 
    
    def close(self):
        """Close all sockets and contexts"""
        self.poke_socket.close()
        
        # Sometimes gets stuck here?
        self.poke_context.term()
