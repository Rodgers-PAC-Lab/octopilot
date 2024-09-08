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
    start
    stop
    exit
    alive

The pi can send the following messages to the GUI:
    poke
    reward
    sound
    alive
    goodbye

"""

import zmq
from ..shared.logtools import NonRepetitiveLogger
import logging
import datetime


## Shared methods
def parse_params(token_l):
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

## Instantiated by Dispatcher
class DispatcherNetworkCommunicator(object):
    """Handles communication with the Pis"""
    def __init__(self, worker_port, expected_identities):
        """Initialize object to communicate with the Pis.
        
        Arguments
        ---------
        worker_port : str
            Taken from params['worker_port']
        expected_identies : list of str
            Each entry is the identity of a Pi
            The session can't start until all expected identities connect
        
        Flow
        ----
        * Create context and socket using zmq.ROUTER
        * Bind to tcp://*{worker_port}
        * Initialize empty self.connected_pis
        """
        ## Init logger
        self.logger = NonRepetitiveLogger("test")
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.DEBUG)


        # Store provided params
        # This is who we expect to connect
        self.expected_identities = expected_identities

        # Set of identities of all pis connected to that instance of ther GUI 
        self.connected_pis = set() 
        
        # Set up the method to call on each command
        self.command2method = {}
        
        # Set up sockets
        self.init_socket(worker_port)
    
    def init_socket(self, worker_port):
        ## Set up ZMQ
        # Setting up a ZMQ socket to send and receive information about 
        # poked ports 
        # (the DEALER socket on the Pi initiates the connection and then 
        # the ROUTER 
        # manages the message queue from different dealers and sends 
        # acknowledgements)
        self.context = zmq.Context()
        self.zmq_socket = self.context.socket(zmq.ROUTER)
        
        # Making it bind to the port used for sending poke related information
        self.zmq_socket.bind(f"tcp://*{worker_port}")
    
    def check_if_all_pis_connected(self):
        """"Returns True if all pis in self.expected_identies are connected"""
        # Iterate over identies
        # Return False if any is missing
        all_connected = True
        for identity in self.expected_identities:
            if identity not in self.connected_pis:
                all_connected = False
                break
        
        return all_connected
    
    def send_message_to_all(self, msg):
        """"Send msg to all identities in self.connected_pis"""
        self.logger.info(f'sending message to all connecting pis: {msg}')
        
        # Convert to bytes
        msg_bytes = bytes(msg, 'utf-8')
        
        # Send to all
        for identity in self.connected_pis:
            identity_bytes = bytes(identity, 'utf-8')
            self.zmq_socket.send_multipart([identity_bytes, msg_bytes])
    
        self.logger.info(f'above message was sent to {self.connected_pis}')    
    
    def send_start(self):
        self.logger.info('sending start message to all connected pis')
        self.send_message_to_all('start')
    
    def send_trial_parameters(self, **kwargs):
        """Encode a set_trial_parameters message and send to all Pis
        
        The message will begin with "set_trial_parameters;"
        Each keyword argument will be converted into "{key}={value}={dtyp}"
        (dtyp is inferred from value)
        
        TODO: do this with json instead
        
        Then it is sent to all Pis.
        """
        msg = "set_trial_parameters;"
        for key, value in kwargs.items():
            # Infer dtyp
            if hasattr(value, '__len__'):
                dtyp = 'str'
            elif isinstance(value, bool):
                # Note that bool is an instance of int
                dtyp = 'bool'
            elif isinstance(value, int):
                # https://stackoverflow.com/a/48940855/1676378
                dtyp = 'int'
            else:
                dtyp = 'float'
            
            # Append
            msg += f"{key}={value}={dtyp};"
        
        self.logger.info(msg)
        
        self.send_message_to_all(msg)
    
    def check_for_messages(self):
        """Check self.zmq_socket for messages.
        
        If a message is available: return identity, messages
        Otherwise: return None
        """
        ## Check for messages
        message_received = True
        try:
            # Without NOBLOCK, this will hang until a message is received
            # TODO: use Poller here?
            identity, message = self.zmq_socket.recv_multipart(
                flags=zmq.NOBLOCK)
        except zmq.error.Again:
            message_received = False

        # If there's no message received, there is nothing to do
        if message_received:
            self.handle_message(identity, message)
    
    def handle_message(self, identity, message):
        """Handle a message received on poke_socket
        
        In the present design, it seems that these messages are handled
        sequentially, so there is no need for a thread lock. To test,
        put a time.sleep(10) in a handling function.
        
        Arguments
        ---------
        msg : str
            A ';'-separated list of strings
            The first string is the "command"
            The remaining strings should be in the format {KEY}={VALUE}={DTYP}
            The method self.command2method[command] is called with a dict
            of arguments formed from the remaining strings.
        """        
        # Debug print identity and message
        self.logger.debug(f'received from {identity}: {message}')
        
        # Decode the message
        # TODO: in the future support bytes
        identity_str = identity.decode('utf-8')
        message_str = message.decode('utf-8')

        # Keep track of the identities
        if identity_str not in self.connected_pis:
            self.add_identity_to_connected(identity_str, message_str)

        # Split on semicolon
        tokens = message_str.strip().split(';')
        
        # The command is the first token
        # This will always run, but command could be ''
        command = tokens[0]
        
        # Get the params
        # This will always run, but could return {}
        msg_params = parse_params(tokens[1:])
        
        # Insert identity into msg_params
        msg_params['identity'] = identity_str
        
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
            meth(**msg_params)

    def add_identity_to_connected(self, identity_str, message_str):
        # This better be a hello message
        if not message_str.startswith('hello'):
            self.logger.warn(
                f'warning: first message from new identity {identity_str} '
                f'was not hello but rather {message_str}'
                )
        
        else:
            self.logger.info(
                f'first message from new identity {identity_str} '
                f'is {message_str}')
        
        # Check whether it's expected
        if identity_str in self.expected_identities:
            # Keep track of it
            self.connected_pis.add(identity_str)
        
        else:
            self.logger.warn(
                f'warning: {identity_str} is not in expected_identities '
                'but it attempted to connect'
                )
    
    def remove_identity_from_connected(self, identity):
        if identity not in self.connected_pis:
            self.logger.error(f'{identity} said goodbye but it was not connected')
        
        self.connected_pis.remove(identity)

## This class is instantiated by HardwareController
class PiNetworkCommunicator(object):
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
        self.socket_is_open = False
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

        # Set LINGER to 100 ms
        # During context.term(), this is how long it will wait to send 
        # remaining messages before closing. The default value is to wait
        # forever, which means that whenever the server is closed first,
        # then closing the Pi will hang.
        # https://github.com/zeromq/pyzmq/issues/102
        self.poke_socket.setsockopt(zmq.LINGER, 100)


        ## Connect to the server
        # Connecting to the GUI IP address stored in params
        self.router_ip = "tcp://" + f"{self.gui_ip}" + f"{self.poke_port}" 
        self.poke_socket.connect(self.router_ip) 

        # Print acknowledgment
        self.socket_is_open = True
        print(f"Connected to router at {self.router_ip}")  

    def send_hello(self):
        # Send the identity of the Raspberry Pi to the server
        self.logger.debug('sending hello')
        self.poke_socket.send_string(f"hello") 

    def check_socket(self):
        # Get time
        dt_now = datetime.datetime.now().isoformat()

        # Wait for events on registered sockets. 
        # Currently polls every 100ms to check for messages 
        self.logger.debug('checking poke socket')
        socks = dict(self.poller.poll(100))

        # Check for incoming messages on poke_socket
        if self.poke_socket in socks and socks[self.poke_socket] == zmq.POLLIN:
            # Waiting to receive message strings that control the main loop
            # Is this blocking?
            # I think the 'if' is only satisfied if there is something to
            # receive, so it doesn't matter if it's blocking
            msg = self.poke_socket.recv_string()  
            
            # Receive message
            self.logger.debug(
                f'{dt_now} - Received message {msg} on poke socket')
    
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
        msg_params = parse_params(tokens[1:])
        
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
            meth(**msg_params)

    def send_goodbye(self):
        """Send goodbye message to GUI
        
        """
        self.logger.info('sending goodbye')
        self.poke_socket.send_string(f"goodbye") 
    
    def send_alive(self):
        """Send alive message to Dispatcher"""
        if self.socket_is_open:
            self.logger.debug('sending alive')
            self.poke_socket.send_string('alive')
        else:
            self.logger.error('alive requested but socket is closed')
    
    def close(self):
        """Close all sockets and contexts"""
        # Prevent sending
        self.socket_is_open = False
        
        # Close
        self.poke_socket.close()
        
        # Gets stuck here if the GUI was closed and more messages were sent
        self.poke_context.term()
