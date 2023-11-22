#!/bin/bash

CURRENT_DIR=$(dirname "$0")
KLIPPER_PATH="${HOME}/klipper"
EXTENSION_PATH="${CURRENT_DIR}/extension"
SERVER_PATH="${CURRENT_DIR}/server"




PKGLIST="python-opencv"

link_extension()
{
    echo "Linking extension to Klipper..."
    ln -sf "${EXTENSION_PATH}/kTAMV.py" "${KLIPPER_PATH}/klippy/extras/kTAMV.py"
    ln -sf "${EXTENSION_PATH}/kTAMV_pm.py" "${KLIPPER_PATH}/klippy/extras/kTAMV_pm.py"
    ln -sf "${EXTENSION_PATH}/kTAMV_utl.py" "${KLIPPER_PATH}/klippy/extras/kTAMV_utl.py"
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
