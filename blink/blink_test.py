# zmq_blink_module.py

import zmq
import time

blink_state = None

class BlinkTest:
    def __init__(self, address="tcp://*:5567"):
        #self.blink_state = blink_state
        
        # Making a context to send blink state information to all Pis
        self.blink_context = zmq.Context()
        self.blink_socket = self.blink_context.socket(zmq.PUB)
        self.blink_socket.bind(address)

    def send_message(self, msg):
        if msg == "blink":
            self.blink_socket.send_string("blink")
            print(f"Sent 'blink' to Pis")

        elif msg == "waiting":
            self.blink_socket.send_string("waiting")
            print(f"Sent 'waiting' to Pis")

    # def set_blink_state(self, state = blink_state):
    #     self.blink_state = state
    #     print(f"Blink state set to {self.blink_state}")

# controller = BlinkTest()
# running = True
# try:
#     while running == True:
#         if blink_state == True:
#             controller.send_message("blink")
#         elif blink_state == False:
#             controller.send_message("waiting")
#         controller.send_message("blink")
#         time.sleep(1)
# except KeyboardInterrupt:
#     running = False
#     print("Shutting down.")
#     controller.blink_socket.close()
#     controller.blink_context.term()

# def main():
#     controller = BlinkTest()
#     try:
#         while True:
#             controller.set_blink_state(blink_state)
#             controller.send_message()
#             time.sleep(1)
#     except KeyboardInterrupt:
#         print("Shutting down.")
#         controller.blink_socket.close()
#         controller.blink_context.term()

# main()


# # Entry point for running the module as a script
# if __name__ == "__main__":
#     controller = BlinkTest()
    
#     # Example usage (replace with your own logic to control the flow)
#     try:
#         while True:
#             controller.send_message()
#             time.sleep(1)

#     except KeyboardInterrupt:
#         print("Shutting down.")
     
#     finally:
#         controller.blink_socket.close()
#         controller.blink_context.term()
