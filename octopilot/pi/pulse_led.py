import pigpio
import time

pig = pigpio.pi()
pin = 26
pig.set_mode(pin, pigpio.OUTPUT)
pig.set_PWM_frequency(pin, 8000) # 8KHz is fastest with default pigpio
print(pig.get_PWM_frequency(pin))

flash_dur = 0.1
try:
    while True:
        #pig.set_PWM_dutycycle(pin, 128)
        pig.write(pin, 1)
        time.sleep(flash_dur)
        pig.write(pin, 0)

        time.sleep(0.5 - flash_dur)

except KeyboardInterrupt:
    pig.write(pin, 0)    
    print("CTRL+C received")

