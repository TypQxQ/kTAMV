# kTAMV - Klipper Tool Alignment (using) Machine Vision
kTAMV builds on TAMV, https://github.com/HaythamB/TAMV and on CVToolheadCalibration that is also a adaptation of TAMV but for IDEX printers.

This is a non working development as of 14/11/2023.


TODO: Add more indo based on below and TAMV.

# Automatic toolhead offset calibration using computer vision for Klipper

CVToolheadCalibration is an extension for IDEX printers running klipper that adds functionality to calibrate toolhead offset using a USB microscope/webcam. With this extension you can easily calibrate the toolhead offsets. 

Adds the following commands to klipper:
  - `KTAMV_CALIB_CAMERA`, moves the current active toolhead around the current position to calibrate movement data
  - `KTAMV_FIND_NOZZLE_CENTER`, detects the nozzle in the current nozzle cam image and atempts to move it to the center of the image.
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

```
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

## Special thanks
 - This extension is heavily inspired by TAMV. TAMV is an extension for Duet based printers which also uses computer vision to align toolheads. For more information see: https://github.com/HaythamB/TAMV
 - The user Dorkscript from the DOOMCUBE discord, who tested early versions of the extension and gave very valuable feedback
