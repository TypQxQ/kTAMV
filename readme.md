# kTAMV - Klipper Tool Alignment (using) Machine Vision

This allows X and Y allignment betwween multiple tools on a 3D printer using a camera that points up towards the nozzle from inside Klipper.

It has one part that runs as a part of Klipper, adding the necesary commands and integration, and one part that does all the io and cpu intensive calculations as a webserver, localy or on any computer for true multithreading. 

It adds the following commands to klipper:

- `KTAMV_CALIB_CAMERA`, moves the toolhead around the current position for camera-movement data
- `KTAMV_FIND_NOZZLE_CENTER`, detects the nozzle in the current nozzle cam image and attempts to move it to the center of the image.
- `KTAMV_SET_ORIGIN`, sets the current X,Y position as origin to use for calibrating from.
- `KTAMV_GET_OFFSET`, Get the offset from the current X,Y position to the origin X,Y position. Prints it to console.
- `KTAMV_MOVE_TO_ORIGIN`, moves the toolhead to the configured center position origin as set with KTAMV_SET_ORIGIN
- `KTAMV_SIMPLE_NOZZLE_POSITION`, checks if a nozzle is detected in the current nozzle cam image and reports whether it is found. The printer will not move.
- `KTAMV_TEST`, debug command to check if the script works and OpenCV versions

!!! !!! !!! !!! !!!
This is alpha software and only meant for advanced users!
Please only use while supervising your printer,
may produce unexpected results,
be ready to hit 'emergency stop' at any time!
!!! !!! !!! !!! !!!

## How to install

Connect to your klipper machine using SSH, run these commands

```bash
cd ~/ && git clone -b dev https://github.com/TypQxQ/kTAMV.git && bash ~/kTAMV/install.sh
```

This will clone the repository and execute the install script.

------ old ------



To enable automatic updates using moonraker, add the following to your moonraker config:

```
[update_manager cv_toolhead_calibration]
type: git_repo
path: ~/klipper_cv_toolhead_calibration
origin: https://github.com/cawmit/klipper_cv_toolhead_calibration.git
install_script: install.sh
requirements: requirements.txt
managed_services: klipper
```

## Configuration

```
[cv_toolhead_calibration]
nozzle_cam_url: http://localhost:8081?action=stream
camera_position: 75,75 # X,Y mm values of the T0 toolhead visible in the center of the nozzle camera
```

## First time running after install

1. Run the `CV_CENTER_TOOLHEAD` command to center the toolhead
2. Connect and open the web page to view the nozzle cam
3. Position the camera so that the nozzle is roughly in the center of the image
4. Run the `CV_SIMPLE_NOZZLE_POSITION` command, this should return your nozzle position in the image
5. If everything works, you can run `CV_CALIB_OFFSET` 

## How it works
One part runs as a Klipper plugin and the second part as a Web Server using Flask and Waitress.
The part running inside Klipper must run inside the enviroment  managed by Klipper and does not need any extra componnts. The Server part meanwhile needs many specific components for image recognition, mathematics, statistics and web server.
It is trully multithreaded because the Webserver runs in it's own Python instance and can ever run on a diffrent machine. Because Klipper needs realtime interaction with the printer mainboards and running as a Python application it cannot be trully multithreaded by itself.





## Special thanks
 - This extension is heavily inspired by TAMV. TAMV is an extension for Duet based printers which also uses computer vision to align toolheads. For more information see: https://github.com/HaythamB/TAMV
 - The user Dorkscript from the DOOMCUBE discord, who tested early versions of the extension and gave very valuable feedback
 - kTAMV builds on TAMV, https://github.com/HaythamB/TAMV and on CVToolheadCalibration that is also a adaptation of TAMV but for IDEX printers.
