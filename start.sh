#!/bin/bash

INVENV=$(python -c 'import sys; print ("1" if hasattr(sys, "real_prefix") else "0")')

WORKING_DIR="${PWD}/"
GUNICORN="${PWD}/bin/gunicorn"
PYTHON="${PWD}/bin/python"

cd $WORKING_DIR

if [[ INVENV == 0 ]]
then
        source bin/acticate
fi

# Start stream daemon
$PYTHON streamdaemon.py
sleep 5

# Start the sync daemon
$PYTHON syncdaemon.py
sleep 10

# Issue start cmd to syncdaemon
/bin/bash ctrl.sh start


if [[ INVENV == 0 ]]
then
        deactivate
fi

cd
