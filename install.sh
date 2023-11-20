#!/bin/bash

KLIPPER_PATH="${HOME}/klipper"
EXTENSION_PATH="${HOME}/kTAMV"

PKGLIST="python-opencv"

link_extension()
{
    echo "Linking extension to Klipper..."
    ln -sf "${EXTENSION_PATH}/kTAMV.py" "${KLIPPER_PATH}/klippy/extras/kTAMV.py"
    ln -sf "${EXTENSION_PATH}/kTAMV_cv.py" "${KLIPPER_PATH}/klippy/extras/kTAMV_cv.py"
    ln -sf "${EXTENSION_PATH}/kTAMV_io.py" "${KLIPPER_PATH}/klippy/extras/kTAMV_io.py"
    ln -sf "${EXTENSION_PATH}/kTAMV_pm.py" "${KLIPPER_PATH}/klippy/extras/kTAMV_pm.py"
    ln -sf "${EXTENSION_PATH}/kTAMV_DetectionManager.py" "${KLIPPER_PATH}/klippy/extras/kTAMV_DetectionManager.py"

}

restart_klipper()
{
    echo "Restarting Klipper..."
    sudo systemctl restart klipper
}

verify_ready()
{
    if [ "$EUID" -eq 0 ]; then
        echo "This script must not run as root"
        exit -1
    fi
}

# Force script to exit if an error occurs
set -e

# Parse command line arguments
while getopts "k:" arg; do
    case $arg in
        k) KLIPPER_PATH=$OPTARG;;
    esac
done

verify_ready
link_extension
restart_klipper
