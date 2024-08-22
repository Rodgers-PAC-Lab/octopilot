# zmq_blink_module.py

import zmq
import time

blink_state = False

class BlinkTest:
    def __init__(self, address="tcp://*:5560"):
        self.blink_state = blink_state
        
        # Making a context to send blink state information to all Pis
        self.blink_context = zmq.Context()
        self.blink_socket = self.blink_context.socket(zmq.PUB)
        self.blink_socket.bind(address)

    def send_message(self, msg=None):
        if self.blink_state == True:
            msg = "blink"
            self.blink_socket.send_string(msg)
            print(f"Sent 'blink' to Pis")

        elif self.blink_state == False or self.blink_state == None:
            msg = "waiting"
            self.blink_socket.send_string(msg)
            pass

# Entry point for running the module as a script
if __name__ == "__main__":
    controller = BlinkTest()
    
    # Example usage (replace with your own logic to control the flow)
    try:
        while True:
            controller.send_message()
            time.sleep(1)

    except KeyboardInterrupt:
        print("Shutting down.")
     
    finally:
        controller.blink_socket.close()
        controller.blink_context.term()
