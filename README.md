# Instructions for f451-piGREEN v0.0.0

## Custom application settings in SETTINGS.TOML

The 'settings.toml' file holds various custom application settings and secrets (e.g. Adafruit IO keys, etc.) and this file should **NOT** be included in 'git' commits.

It is recommended to copy the '*settings.example*' to '*settings.toml*' and then customize the values in '*settings.toml*' as needed for the specific device that the application is running on.

### Adafruit IO settings

- **AIO_USERNAME**: 'string' - Adafruit IO username
- **AIO_KEY**: 'string' - Adafruit IO key
- **AIO_UPLOAD**: 'string' - yes | force | no
    - "yes" - *upload if feed available*
    - "force" - *exit if feed invalid*
    - "no" - *do not upload data*

- **FEED_TEMPS**: 'string' - Adafruit IO feed key for 'temperature' feed
- **FEED_PRESS**: 'string' - Adafruit IO feed key for 'pressure' feed
- **FEED_HUMID**: 'string' - Adafruit IO feed key for 'humidity' feed

### Misc. Settings for Data Management

- **TODO - UNITS_TEMPS**: 'string' - temperature sensor reads in "C", but data can also be converted to other units for display and upload.
    - "C" - *Celsius*
    - "F" - *Fahrenheit - data will be converted from Celsius to Fahrenheit*
    - "K" - *Kelvin - data will be converted from Celsius to Kelvin*

    - *Example: "F" means temperature data will be converted from Celsius to Fahrenheit before it is uploaded or displayed.*

### Misc. Application Defaults

- **TODO - ROTATION**: 'int' - 0 | 90 | 180 | 270 degrees to turn 8x8 LED display
    - 90 | 270 - *top of LED will point toward/away RPI HDMI*
    - 0 | 180 - *top of LED will point away/toward RPI USB*

- **TODO - DISPLAY**: 'int' - 0..3
    - 1..3 - *display modes with single data point (e.g. temperature, etc.) and scrolling bar graph*
    - 0 - *display is 'sparkle' mode where data is collected and uploaded but not displayed*

- **TODO - DELAY**: 'int' - delay in seconds between uploads to Adafruit IO.
    - Smaller number means more freq uploads and higher data rate
- **TODO - WAIT**: 'int' - delay in seconds between sensor reads
- **TODO - THROTTLE**: 'int' - additional delay in seconds to be applied on Adafruit IO 'ThrottlingError'

- **TODO - PROGRESS**: 'string' - on | off
    - "on" - *show 'wait for upload' progress bar on LED*
    - "off" - *do not show progress bar*

- **TODO - SLEEP**: 'int' - delay in seconds until LED is blanked for "screen saver" mode

- **LOGLVL**: 'string' - debug | info | error
    - *Logging levels (see: [Python docs](https://docs.python.org/3/library/logging.html#logging-levels) for more info)*

- **LOGFILE**: 'string' - path and file name for log file

## Dependencies

The following special libraries are required:

- [adafruit-io](https://pypi.org/project/adafruit-io/) - only install if you have physical Sense HAT
- [speedtest-cli](https://pypi.org/project/speedtest-cli/) - (optional) only used for internet speed tests 
