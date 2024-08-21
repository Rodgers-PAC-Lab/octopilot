# zmq_blink_module.py

import zmq
import time

blink_state = False

class BlinkTest:
    def __init__(self, address="tcp://*:5555"):
        self.blink_state = blink_state
        
        # Making a context to send blink state information to all Pis
        self.blink_context = zmq.Context()
        self.blink_socket = self.blink_context.socket(zmq.PUB)
        self.blink_socket.bind(address)

    def send_message(self):
        if self.blink_state == True:
            self.blink_socket.sendstring("blink")
            print(f"Sent 'blink' to Pis")

        elif self.blink_state == False or self.blink_state == None:
            pass

    # def set_blink_state(self, state):
    #     self.blink_state = state
    #     print(f"Blink state set to {self.blink_state}")

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
