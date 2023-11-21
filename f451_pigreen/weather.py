#!/usr/bin/env python3
"""f451 Labs SenseMon application on piRED device.

This application is designed for the f451 Labs piRED device which is also equipped with 
a Sense HAT add-on. The main objective is to continously read environment data (e.g. 
temperature, barometric pressure, and humidity from the Sense HAT sensors and then upload 
the data to the Adafruit IO service.

To launch this application from terminal:

    $ nohup python -u sensemon.py > sensemon.out &

This command launches the 'sensemon' application in the background. The application will 
keep running even after the terminal window is closed. Any output will be redirected to 
the 'sensemon.out' file.    

It's also possible to install this application via 'pip' from Github and one 
can launch the application as follows:

    $ nohup sensemon > sensemon.out &

NOTE: This code is based on the 'luftdaten_combined.py' example from the Enviro+ Python
      example files. Main modifications include support for Adafruit.io, using Python 
      'deque' to manage data queues, moving device support to a separate class, etc.

      Furthermore, this application is designed to get sensor data from the Raspberry 
      Pi Sense HAT which has fewer sensors than the Enviro+, an 8x8 LED, and a joystick.
      
      We also support additional display modes including a screen-saver mode, support 
      for 'settings.toml', and more.

Dependencies:
    - adafruit-io - only install if you have an account with Adafruit IO
    - speedtest-cli - (optional) only used for internet speed tests 
"""

import argparse
import time
import sys
import asyncio

from pathlib import Path
from datetime import datetime
from collections import deque

from . import constants as const

import f451_common.common as f451Common
import f451_logger.logger as f451Logger
import f451_cloud.cloud as f451Cloud

import f451_sensehat.sensehat as f451SenseHat
import f451_sensehat.sensehat_data as f451SenseData

from Adafruit_IO import RequestError, ThrottlingError


# =========================================================
#          G L O B A L    V A R S   &   I N I T S
# =========================================================
APP_VERSION = "0.0.1"
APP_NAME = "f451 piRED - SenseMon"
APP_LOG = "f451-pired-sensemon.log"     # Individual logs for devices with multiple apps
APP_SETTINGS = "settings.toml"          # Standard for all f451 Labs projects
APP_DIR = Path(__file__).parent         # Find dir for this app

APP_DISPLAY_MODES = {
    f451SenseHat.KWD_DISPLAY_MIN: const.MAX_DISPL, 
    f451SenseHat.KWD_DISPLAY_MAX: const.MIN_DISPL
}

# Load settings
CONFIG = f451Common.load_settings(APP_DIR.joinpath(APP_SETTINGS))

# Initialize device instance which includes all sensors
# and LED display on Sense HAT
SENSE_HAT = f451SenseHat.SenseHat(CONFIG)

# Initialize logger and IO cloud
LOGGER = f451Logger.Logger(CONFIG, LOGFILE=APP_LOG)
UPLOADER = f451Cloud.Cloud(CONFIG)

# Verify that feeds exist
try:
    FEED_TEMPS = UPLOADER.aio_feed_info(CONFIG.get(const.KWD_FEED_TEMPS, None))
    FEED_PRESS = UPLOADER.aio_feed_info(CONFIG.get(const.KWD_FEED_PRESS, None))
    FEED_HUMID = UPLOADER.aio_feed_info(CONFIG.get(const.KWD_FEED_HUMID, None))

except RequestError as e:
    LOGGER.log_error(f"Application terminated due to REQUEST ERROR: {e}")
    sys.exit(1)


# We use these timers to track when to upload data and/or set
# display to sleep mode. Normally we'd want them to be local vars 
# inside 'main()'. However, since we need them reset them in the 
# button actions, they need to be global.
timeUpdate = time.time()
displayUpdate = timeUpdate


# =========================================================
#              H E L P E R   F U N C T I O N S
# =========================================================
def debug_config_info(cliArgs):
    """Print/log some basic debug info."""

    LOGGER.log_debug("-- Config Settings --")
    LOGGER.log_debug(f"DISPL ROT:   {SENSE_HAT.displRotation}")
    LOGGER.log_debug(f"DISPL MODE:  {SENSE_HAT.displMode}")
    LOGGER.log_debug(f"DISPL PROGR: {SENSE_HAT.displProgress}")
    LOGGER.log_debug(f"SLEEP TIME:  {SENSE_HAT.displSleepTime}")
    LOGGER.log_debug(f"SLEEP MODE:  {SENSE_HAT.displSleepMode}")
    LOGGER.log_debug(f"IO DEL:      {CONFIG.get(const.KWD_DELAY, const.DEF_DELAY)}")
    LOGGER.log_debug(f"IO WAIT:     {CONFIG.get(const.KWD_WAIT, const.DEF_WAIT)}")
    LOGGER.log_debug(f"IO THROTTLE: {CONFIG.get(const.KWD_THROTTLE, const.DEF_THROTTLE)}")

    # Display Raspberry Pi serial and Wi-Fi status
    LOGGER.log_debug(f"Raspberry Pi serial: {f451Common.get_RPI_serial_num()}")
    LOGGER.log_debug(f"Wi-Fi: {(f451Common.STATUS_YES if f451Common.check_wifi() else f451Common.STATUS_UNKNOWN)}")

    # Display CLI args
    LOGGER.log_debug(f"CLI Args:\n{cliArgs}")
    LOGGER.log_debug("-- // --\n")


def init_cli_parser():
    """Initialize CLI (ArgParse) parser.

    Initialize the ArgParse parser with the CLI 'arguments' and
    return a new parser instance.

    Returns:
        ArgParse parser instance
    """
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description=f"{APP_NAME} [v{APP_VERSION}] - read sensor data from Enviro+ HAT and upload to Adafruit IO and/or Arduino Cloud.",
        epilog="NOTE: This application requires active accounts with corresponding cloud services.",
    )

    parser.add_argument(
        "-V",
        "--version",
        action="store_true",
        help="display script version number and exit",
    )
    parser.add_argument(
        "-d",
        "--debug", 
        action="store_true", 
        help="run script in debug mode"
    )
    parser.add_argument(
        "--cron",
        action="store_true",
        help="use when running as cron job - run script once and exit",
    )
    parser.add_argument(
        "--noDisplay",
        action="store_true",
        default=False,
        help="do not display output on LED",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="show upload progress bar on LED",
    )
    parser.add_argument(
        "--log",
        action="store",
        type=str,
        help="name of log file",
    )
    parser.add_argument(
        "--uploads",
        action="store",
        type=int,
        default=-1,
        help="number of uploads before exiting",
    )

    return parser


async def upload_sensor_data(*args, **kwargs):
    """Send sensor data to cloud services.
    
    This helper function parses and sends enviro data to 
    Adafruit IO and/or Arduino Cloud.

    NOTE: This function will upload specific environment 
          data using the following keywords:

          'temperature' - temperature data
          'pressure'    - barometric pressure
          'humidity'    - humidity

    Args:
        args:
            User can provide single 'dict' with data
        kwargs:
            User can provide individual data points as key-value pairs
    """
    # We combine 'args' and 'kwargs' to allow users to provide a 'dict' with
    # all data points and/or individual data points (which could override 
    # values in the 'dict').
    data = {**args[0], **kwargs} if args and isinstance(args[0], dict) else kwargs

    sendQ = []

    # Send temperature data ?
    if data.get(const.KWD_DATA_TEMPS, None) is not None:
        sendQ.append(UPLOADER.aio_send_data(FEED_TEMPS.key, data.get(const.KWD_DATA_TEMPS)))

    # Send barometric pressure data ?
    if data.get(const.KWD_DATA_PRESS, None) is not None:
        sendQ.append(UPLOADER.aio_send_data(FEED_PRESS.key, data.get(const.KWD_DATA_PRESS)))

    # Send humidity data ?
    if data.get(const.KWD_DATA_HUMID, None) is not None:
        sendQ.append(UPLOADER.aio_send_data(FEED_HUMID.key, data.get(const.KWD_DATA_HUMID)))

    # deviceID = SENSE_HAT.get_ID(DEF_ID_PREFIX)

    await asyncio.gather(*sendQ)


def btn_up(event):
    """SenseHat Joystick UP event
    
    Rotate display by -90 degrees and reset screen blanking
    """
    global displayUpdate

    if event.action != f451SenseHat.BTN_RELEASE:
        SENSE_HAT.display_rotate(-1)
        displayUpdate = time.time()


def btn_down(event):
    """SenseHat Joystick DOWN event
    
    Rotate display by +90 degrees and reset screen blanking
    """
    global displayUpdate

    if event.action != f451SenseHat.BTN_RELEASE:
        SENSE_HAT.display_rotate(1)
        displayUpdate = time.time()


def btn_left(event):
    """SenseHat Joystick LEFT event
    
    Switch display mode by 1 mode and reset screen blanking
    """
    global displayUpdate

    if event.action != f451SenseHat.BTN_RELEASE:
        SENSE_HAT.update_display_mode(-1)
        displayUpdate = time.time()


def btn_right(event):
    """SenseHat Joystick RIGHT event
    
    Switch display mode by 1 mode and reset screen blanking
    """
    global displayUpdate

    if event.action != f451SenseHat.BTN_RELEASE:
        SENSE_HAT.update_display_mode(1)
        displayUpdate = time.time()


def btn_middle(event):
    """SenseHat Joystick MIDDLE (down) event
    
    Turn display on/off
    """
    global displayUpdate

    if event.action != f451SenseHat.BTN_RELEASE:
        # Wake up?
        if SENSE_HAT.displSleepMode:
            SENSE_HAT.update_sleep_mode(False)
            displayUpdate = time.time()
        else:    
            SENSE_HAT.update_sleep_mode(True)


APP_JOYSTICK_ACTIONS = {
    f451SenseHat.KWD_BTN_UP: btn_up,
    f451SenseHat.KWD_BTN_DWN: btn_down,
    f451SenseHat.KWD_BTN_LFT: btn_left,
    f451SenseHat.KWD_BTN_RHT: btn_right,
    f451SenseHat.KWD_BTN_MDL: btn_middle,
}


# =========================================================
#      M A I N   F U N C T I O N    /   A C T I O N S
# =========================================================
def main(cliArgs=None):
    """Main function.

    This function will goes through the setup and then runs the
    main application loop.

    NOTE:
     -  Application will exit with error level 1 if invalid Adafruit IO
        or Arduino Cloud feeds are provided

     -  Application will exit with error level 0 if either no arguments 
        are entered via CLI, or if arguments '-V' or '--version' are used. 
        No data will be uploaded will be sent in that case.

    Args:
        cliArgs:
            CLI arguments used to start application
    """
    global LOGGER
    global SENSE_HAT
    global timeUpdate
    global displayUpdate

    cli = init_cli_parser()

    # Show 'help' and exit if no args
    cliArgs, unknown = cli.parse_known_args(cliArgs)
    if (not cliArgs and len(sys.argv) == 1):
        cli.print_help(sys.stdout)
        sys.exit(0)

    if cliArgs.version:
        print(f"{APP_NAME} (v{APP_VERSION})")
        sys.exit(0)

    # Initialize Sense HAT joystick and LED display
    SENSE_HAT.joystick_init(**APP_JOYSTICK_ACTIONS)
    SENSE_HAT.display_init(**APP_DISPLAY_MODES)
    SENSE_HAT.update_sleep_mode(cliArgs.noDisplay)

    if cliArgs.progress:
        SENSE_HAT.displProgress(True)

    # Get core settings
    ioFreq = CONFIG.get(const.KWD_FREQ, const.DEF_FREQ)
    ioDelay = CONFIG.get(const.KWD_DELAY, const.DEF_DELAY)
    ioWait = CONFIG.get(const.KWD_WAIT, const.DEF_WAIT)
    ioThrottle = CONFIG.get(const.KWD_THROTTLE, const.DEF_THROTTLE)
    ioRounding = CONFIG.get(const.KWD_ROUNDING, const.DEF_ROUNDING)
    ioUploadAndExit = cliArgs.cron

    # Initialize core data queues
    tempCompFactor = CONFIG.get(f451Common.KWD_TEMP_COMP, f451Common.DEF_TEMP_COMP_FACTOR)
    cpuTempsQMaxLen = CONFIG.get(f451Common.KWD_MAX_LEN_CPU_TEMPS, f451Common.MAX_LEN_CPU_TEMPS)
    cpuTempsQ = deque([SENSE_HAT.get_CPU_temp(False)] * cpuTempsQMaxLen, maxlen=cpuTempsQMaxLen)

    senseData = f451SenseData.SenseData(1, SENSE_HAT.widthLED)

    # Update log file or level?
    if cliArgs.log is not None:
        LOGGER.set_log_file(CONFIG.get(f451Logger.KWD_LOG_LEVEL, f451Logger.LOG_NOTSET), cliArgs.log)

    if cliArgs.debug:
        LOGGER.set_log_level(f451Logger.LOG_DEBUG)

    # -- Main application loop --
    timeSinceUpdate = 0
    timeUpdate = time.time()
    displayUpdate = timeUpdate
    uploadDelay = ioDelay       # Ensure that we do NOT upload first reading
    maxUploads = int(cliArgs.uploads)
    numUploads = 0
    exitNow = False

    debug_config_info(cliArgs)
    LOGGER.log_info("-- START Data Logging --")

    try:
        while not exitNow:
            timeCurrent = time.time()
            timeSinceUpdate = timeCurrent - timeUpdate
            SENSE_HAT.update_sleep_mode(
                (timeCurrent - displayUpdate) > SENSE_HAT.displSleepTime,
                cliArgs.noDisplay
            )

            # Get raw temp from sensor
            tempRaw = SENSE_HAT.get_temperature()

            # Get current CPU temp, add to queue, and calculate new average
            #
            # NOTE: This feature relies on the 'vcgencmd' which is found on
            #       RPIs. If this is not run on a RPI (e.g. during testing),
            #       then we need to neutralize the 'cpuTemp' compensation. 
            cpuTempsQ.append(SENSE_HAT.get_CPU_temp(False))
            cpuTempAvg = sum(cpuTempsQ) / float(cpuTempsQMaxLen)

            # Smooth out with some averaging to decrease jitter
            tempComp = tempRaw - ((cpuTempAvg - tempRaw) / tempCompFactor)
            LOGGER.log_debug(f"TempComp: {round(tempComp, 1)} - AvgTempCPU: {round(cpuTempAvg, 1)} - TempRaw: {round(tempRaw, 1)}")

            pressRaw = SENSE_HAT.get_pressure()
            humidRaw = SENSE_HAT.get_humidity()

            # Is it time to upload data?
            if timeSinceUpdate >= uploadDelay:
                try:
                    asyncio.run(upload_sensor_data(
                        temperature = round(tempComp, ioRounding), 
                        pressure = round(pressRaw, ioRounding), 
                        humidity = round(humidRaw, ioRounding), 
                        deviceID = f451Common.get_RPI_ID(f451Common.DEF_ID_PREFIX)
                    ))

                except RequestError as e:
                    LOGGER.log_error(f"Application terminated: {e}")
                    sys.exit(1)

                except ThrottlingError:
                    # Keep increasing 'ioDelay' each time we get a 'ThrottlingError'
                    uploadDelay += ioThrottle
                    
                else:
                    # Reset 'uploadDelay' back to normal 'ioFreq' on successful upload
                    numUploads += 1
                    uploadDelay = ioFreq
                    exitNow = (exitNow or ioUploadAndExit)
                    LOGGER.log_info(f"Uploaded: TEMP: {round(tempComp, ioRounding)} - PRESS: {round(pressRaw, ioRounding)} - HUMID: {round(humidRaw, ioRounding)}")

                finally:
                    timeUpdate = timeCurrent
                    exitNow = ((maxUploads > 0) and (numUploads >= maxUploads))

            # Check display mode. Each mode corresponds to a data type
            if SENSE_HAT.displMode == const.IDX_TEMP:           # type = "temperature"
                senseData.temperature.data.append(tempComp)
                SENSE_HAT.display_as_graph(senseData.temperature.as_dict())

            elif SENSE_HAT.displMode == const.IDX_PRESS:        # type = "pressure"
                senseData.pressure.data.append(pressRaw)
                SENSE_HAT.display_as_graph(senseData.pressure.as_dict())

            elif SENSE_HAT.displMode == const.IDX_HUMID:        # type = "humidity"
                senseData.humidity.data.append(humidRaw)
                SENSE_HAT.display_as_graph(senseData.humidity.as_dict())
                    
            else:                                               # Display sparkles
                SENSE_HAT.display_sparkle()

            # Let's rest a bit before we go through the loop again
            if cliArgs.debug and not ioUploadAndExit:
                sys.stdout.write(f"Time to next update: {uploadDelay - int(timeSinceUpdate)} sec \r")
                sys.stdout.flush()

            # Update progress bar as needed and rest a bit 
            # before we do this all over again :-)
            SENSE_HAT.display_progress(timeSinceUpdate / uploadDelay)
            time.sleep(ioWait)

    except KeyboardInterrupt:
        exitNow = True

    # A bit of clean-up before we exit
    LOGGER.log_info("-- END Data Logging --")
    SENSE_HAT.display_reset()
    SENSE_HAT.display_off()
    
    now = datetime.now()
    print(f"\n{APP_NAME} [v{APP_VERSION}] - finished.\n")
    print(f"Num uploads: {numUploads}")
    print(f"Date:        {now:%a %b %-d, %Y}")
    print(f"Time:        {now:%-I:%M:%S %p}")
    print("---- [ END ] ----\n")


# =========================================================
#            G L O B A L   C A T C H - A L L
# =========================================================
if __name__ == "__main__":
    main()  # pragma: no cover
