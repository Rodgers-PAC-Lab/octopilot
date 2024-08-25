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

## INITIALIZING NETWORK CONNECTION
import zmq


## This class is instantiated by HardwareController
class NetworkCommunicator(object):
    """Handles communication with GUI"""
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
        * Set up self.poke_socket and self.json_socket
        * Set up self.poller
        """
        # Store required arguments
        self.pi_identity = pi_identity
        self.gui_ip = gui_ip
        self.poke_port = poke_port
        self.identity = identity
        self.config_port = config_port

        # Set up sockets
        self.set_up_poke_socket()
        self.set_up_json_socket()

        # Creating a poller object for both sockets that will be used to 
        # continuously check for incoming messages
        self.poller = zmq.Poller()
        self.poller.register(self.poke_socket, zmq.POLLIN)
        self.poller.register(self.json_socket, zmq.POLLIN)        
    
    def set_up_poke_socket(self):
        """Connect to poke_socket"""
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
        self.poke_socket.send_string(f"{self.identity}") 

        # Print acknowledgment
        print(f"Connected to router at {self.router_ip}")  

    def set_up_json_socket(self):
        """Connect to json_socket"""
        ## Create socket
        # Creating a SUB socket and socket for receiving task parameters 
        # (stored in json files)
        self.json_context = zmq.Context()
        self.json_socket = self.json_context.socket(zmq.SUB)

        
        ## Connect
        self.router_ip2 = "tcp://" + f"{self.gui_ip}" + f"{self.config_port}"
        self.json_socket.connect(self.router_ip2) 

        # Subscribe to all incoming messages containing task parameters 
        self.json_socket.subscribe(b"")

        # Print acknowledgment
        print(f"Connected to router at {self.router_ip2}")

    def close(self):
        """Close all sockets and contexts"""
        self.poke_socket.close()
        self.poke_context.term()
        self.json_socket.close()
        self.json_context.term()
    