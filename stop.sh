#!/bin/bash

WORKING_DIR="${PWD}/"
PID_FILE="${PWD}/gunicorn.pid"
cd $WORKING_DIR

if [ ! -f $PID_FILE ];then
        echo "No pid file, exiting"
else
        kill -15 `cat ${PID_FILE}`
        echo "Killed process from pid file"
fi
