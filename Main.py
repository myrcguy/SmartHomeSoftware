import RPi.GPIO as GPIO

import threading 
import drivers
from time import sleep
import time
import datetime
from urllib import request
import Freenove_DHT as DHT
import json

GPIO.setwarnings(False) # Ignore warning for now
GPIO.setmode(GPIO.BOARD) # Use physical pin numbering
station = '75'
appKey = '645daa59-dd6c-43a8-964e-52b6a9e990b0'

#BUTTON SETUP
ButtonPinR = 35

ButtonPinB = 29

ButtonDoor_Window = 16

#Setting pins to PULL UP starting
GPIO.setup(ButtonPinR, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(ButtonPinB, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(ButtonDoor_Window, GPIO.IN, pull_up_down=GPIO.PUD_UP)
DHTPin = 13 #Pin is #13 GPIO 27
ht = DHT.DHT(DHTPin)
display = drivers.Lcd(0x27)
ledPin = 12 # define ledPin
sensorPin = 11 # define sensorPin
timeToStay = 10
timeOfLastMotion = 0
doorWindowStatusBool = 0 #0 If doors and windows are closed, 1 if they are open 
motionStatus = "OFF" #Global Motion Status string to LCD
HVACStatus   = "OFF" #Global status for the AC/HEATER
DoorWindowString = "SAFE" #Global string used for Open/Safe on LCD 
humidity = 50  #Global humidity Status 
WeatherIndex = 76  #Global Feel like temp string to LCD
desiredTemp = 76 #Temperature that we desire to reach
HVACCost = 0 #Total cost in dollars for heater or AC
HVACCostKWH = 0 #Total cost in KWH for heater or AC
DoorWindowBool = 0 #Bool Used for updating the LCD when the door opens/closes
printingThread = None #Thread for updatingLCD
humidityThread = None #Thread for getHumidty
temperatureThread = None #Thread for getTemp
buttonThread = None #Thread for checkingifbuttons are pressed
HVACThread = None #Thread for running/checking HVAC
EnergyBillCalcThread = None #Thread for running and calculating the cost of energy 
def setup():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BOARD) # use PHYSICAL GPIO Numbering
    GPIO.setup(ledPin, GPIO.OUT) # set ledPin to OUTPUT mode
    GPIO.setup(sensorPin, GPIO.IN) # set sensorPin to INPUT mode

def motionLoop(): #Function to detect motion using motion Sensor 
    global timeOfLastMotion
    global motionStatus
    GPIO.output(ledPin,GPIO.LOW) # turn off led
    while True:
        currentTime = time.monotonic(); #Time before light is on 
        if GPIO.input(sensorPin)==GPIO.HIGH:
            #display.lcd_display_string("MOTION DETECTED", 1)
            motionStatus = "ON "
            GPIO.output(ledPin,GPIO.HIGH) # turn on led
            timeOfLastMotion = currentTime  #Time After light is on 
            #print ('led turned on >>>')
        if(currentTime >= timeOfLastMotion + 10):
            #display.lcd_display_string("NO MOTION DETECTED", 1)
            motionStatus = "OFF"
            GPIO.output(ledPin,GPIO.LOW) # turn off led
            #print ('led turned off <<<')
            
def getTemp(): #Function to get the current Temperature from the Dh11 Sensor
    global humidity
    global WeatherIndex
    dht = DHT.DHT(DHTPin)
    sumCnt = 0
    checkCount = 0;
    totalTemp = 0
    while True:
        sumCnt +=1
        chk = dht.readDHT11()
        if(chk is dht.DHTLIB_OK):
            checkCount +=1 #Variable used to get temperature every 3 seconds then reset 
            totalTemp += dht.temperature

        if(checkCount == 3):
            checkCount = 0
            #print("Temperature : %d \n"%((totalTemp/3)*1.8 + 32))
            WeatherIndex = round(totalTemp/3) + .05*humidity
            WeatherIndex = round(WeatherIndex*1.8 + 32)
            print(WeatherIndex)
            totalTemp = 0
        time.sleep(1) #Sleeping 1 second
        
def getHumidity():
    global humidity
    while True:
        date = datetime.datetime.now().strftime('%Y-%m-%d')
        #print(date)
        url = ('http://et.water.ca.gov/api/data?appkey=' + appKey + '&targets=' + station +
               '&startDate=' + date + '&endDate=' + date + '&dataItems=' + 'hly-rel-hum,&unitOfMeasure=M')
        #print(url)
        try:
            content = request.urlopen(url).read().decode('utf-8')
            #print(content)
            data = json.loads(content)
            #print(data)
        except:
            data = None

        if(data is None):
            return None
        else:
            humidityData = data['Data']['Providers'][0]['Records']
            humidity = int(humidityData[(datetime.datetime.now().hour) - 3]['HlyRelHum']['Value'])

def checkHVACButton():
    while True:
        #Checking if buttons are pressed at any time with .3 second split
        GPIO.add_event_detect(ButtonPinB, GPIO.FALLING,callback=decreaseDesiredTemp, bouncetime=200)
        GPIO.add_event_detect(ButtonPinR, GPIO.FALLING,callback=increaseDesiredTemp, bouncetime=200)
        GPIO.add_event_detect(ButtonDoor_Window, GPIO.FALLING,callback=DoorWindowStatus, bouncetime=200)
        time.sleep(.3)
        
def DoorWindowStatus(Desired):
    global doorWindowStatusBool #Boolean logic used to tell when door is open to close, or close to open state 
    global DoorWindowString
    global DoorWindowBool 
    if(doorWindowStatusBool == 0): #When DoorWindowButton Pressed, we either open/close depending on current state
        doorWindowStatusBool = 1
        DoorWindowString = "OPEN" 
        DoorWindowBool = 1 
        print("DOOR OPEN")
        return
    if(doorWindowStatusBool == 1):
        doorWindowStatusBool = 0
        DoorWindowString = "SAFE"
        DoorWindowBool = 1 
        print("DOOR CLOSED")
        return 
def increaseDesiredTemp(Desired): #If increase temp button pressed incresase temp
    global desiredTemp
    desiredTemp += 1
    print(desiredTemp)
    return
    
def decreaseDesiredTemp(Desired):
    global desiredTemp
    desiredTemp -= 1
    print(desiredTemp)
    return


def HVAC():
    global desiredTemp
    global WeatherIndex
    global HVACStatus
    global doorWindowStatusBool
    while True:
      
        if(WeatherIndex < desiredTemp-3 and doorWindowStatusBool == 0): #Using hystersis of 3 to decide if we need to turn HVAC ON
            HVACStatus = "HEAT"
            
        elif(WeatherIndex > desiredTemp+3 and doorWindowStatusBool == 0):
            HVACStatus = "AC"
        
        else:
            HVACStatus = "OFF"
            
def EnergyBillCalc():
    global HVACCostKWH
    global HVACCost
    global HVACStatus
    #print("I AM IN FUNCTION")
    costBool = 0
    ACorHeatBool = 0 #Bool = 1 means we are running AC, bool = -1 means we are running Heater
    while True:
        if(HVACStatus == "AC" and costBool == 0):
            #print("ACISON")
            startTime = time.time()
            costBool = 1
            ACorHeatBool = 1
            
        if(HVACStatus == "HEAT" and costBool == 0):
            #print("HEATISON")
            startTime = time.time()
            costBool = 1
            ACorHeatBool = -1
        if(HVACStatus == "OFF"):
            finishTime = time.time()
            if(costBool == 1 and ACorHeatBool == 1): #IF the AC was just on using our bools logic, calculate AC KWH 
                HVACCostKWH += (((finishTime - startTime)/3600)* 18000)/1000
                print(finishTime - startTime)
                HVACCost += (HVACCostKWH * 50)/100
                print(HVACCostKWH)
                print(HVACCost)
                costBool = 0
            elif(costBool == 1 and ACorHeatBool == -1): #IF the Heater was just on, using our bools logic calculate the Heater in KWH
                HVACCostKWH += (((finishTime - startTime)/3600) * 36000)/1000
                print(finishTime - startTime)
                HVACCost += (HVACCostKWH * 50)/100
                costBool = 0
                print(HVACCostKWH)
                print(HVACCost)
            
            
            
    
def destroy():
    GPIO.cleanup() # Release GPIO resource
    
    
def updateLCD(): #Function Continuously running to update the LCD
    global motionStatus
    global WeatherIndex 
    global desiredTemp
    global HVACStatus
    global HVACCostKWH
    global HVACCost
    global DoorWindowString
    ACorHeatBool = 0
    LCDHVACStatus = 0 #Boolean value used for displaying when AC or Heater is on
    global DoorWindowBool #Boolean value used for checking when the Door Window is closed/Open
    #If status is 1 we stop printing and display AC is on,
    #if Status is -1 we stop printing and display HEAT is on,
    #If Status is >1 or <-1 we do not stop printing,
    #When AC/HEAT turn off we set the variable back to 0 
    while True:
        if(HVACStatus == "AC"):
            LCDHVACStatus += 1
            ACorHeatBool = 1
        elif(HVACStatus == "HEAT"):
            LCDHVACStatus -= 1
            ACorHeatBool = 1
        else:
            LCDHVACStatus = 0
        firstLine = (str(WeatherIndex) + '/' + str(desiredTemp) + '     ' + 'D:' + DoorWindowString)
        secondLine = ('H:' + HVACStatus + '     ' + 'L:' + motionStatus)
        #print("INUPDATELCD")
        #This function is used to keep updating the LCD
        display.lcd_display_string(firstLine, 1)
        display.lcd_display_string(secondLine, 2)
        if(LCDHVACStatus == 1):
            acUpdate()
            time.sleep(3)
            display.lcd_clear()
        elif(LCDHVACStatus == -1):
            heatUpdate()
            time.sleep(3)
            display.lcd_clear()
        elif(LCDHVACStatus == 0 and ACorHeatBool == 1):
            costUpdate()
            time.sleep(3)
            display.lcd_clear()
            ACorHeatBool = 0
        elif(DoorWindowBool == 1):
            if(DoorWindowString == "SAFE"):
                DoorWindowClosed()
                time.sleep(3)
                display.lcd_clear()
                DoorWindowBool = 0
            elif(DoorWindowString == "OPEN"):
                DoorWindowOpen()
                time.sleep(3)
                display.lcd_clear()
                DoorWindowBool = 0

#Functions below are used for updating the LCD when states change
#All LCD printing statements must be used 
def DoorWindowClosed():
    display.lcd_clear()
    display.lcd_display_string("DOOR/WINDOW CLOSE",1)
    display.lcd_display_string("HVAC ON",2)
    return

def DoorWindowOpen():
    display.lcd_clear()
    display.lcd_display_string("DOOR/WINDOW OPEN",1)
    display.lcd_display_string("  HVAC HALTED",2)
def costUpdate():
    global HVACCostKWH
    global HVACCost
    HVACCOSTKWHString = str(round(HVACCostKWH,2))
    HVACCostString = str(round(HVACCost,2))
    display.lcd_clear()
    display.lcd_display_string("Energy: " + HVACCOSTKWHString + "KWh",1)
    display.lcd_display_string("Cost: $" + HVACCostString,2)    
    return
def acUpdate():
    global HVACCostKWH
    global HVACCost
    HVACCOSTKWHString = str(round(HVACCostKWH,2))
    HVACCostString = str(round(HVACCost,2))
    display.lcd_clear()
    display.lcd_display_string("    AC IS ON",1)
    display.lcd_display_string(HVACCOSTKWHString + "KWH, $" + HVACCostString,2)    
    return

def heatUpdate():
    global HVACCostKWH
    global HVACCost
    HVACCOSTKWHString = str(round(HVACCostKWH,2))
    HVACCostString = str(round(HVACCost,2))
    display.lcd_clear()
    display.lcd_display_string("    HEATER IS ON",1)
    display.lcd_display_string(HVACCOSTKWHString + "KWH, $" + HVACCostString,2)
    return
if __name__ == '__main__': 
    print ('Program is starting...')
    setup()
    #Starting the thread for each function that needs to be looped indefinetely 
    printingThread = threading.Thread(target=updateLCD)
    printingThread.setDaemon(True)
    printingThread.start()
    
    humidityThread = threading.Thread(target=getHumidity)
    humidityThread.setDaemon(True)
    humidityThread.start()
    
    temperatureThread = threading.Thread(target=getTemp)
    temperatureThread.setDaemon(True)
    temperatureThread.start()
    
    buttonThread = threading.Thread(target=checkHVACButton)
    buttonThread.setDaemon(True)
    buttonThread.start()
                          
    HVACStatusThread = threading.Thread(target=HVAC)
    HVACStatusThread.setDaemon(True)
    HVACStatusThread.start()
    
    EnergyBillCalcThread = threading.Thread(target=EnergyBillCalc)
    EnergyBillCalcThread.setDaemon(True)
    EnergyBillCalcThread.start()
    
    try:
        motionLoop()
    except KeyboardInterrupt: # Press ctrl-c to end the program.
        destroy()

