#!/bin/bash

WORKING_DIR="${PWD}/"
STREAM_PID_FILE="${PWD}/streamdaemon.pid"
SYNC_PID_FILE="${PWD}/syncdaemon.pid"

cd $WORKING_DIR

if [ ! -f $PID_FILE ];then
        echo "No pid file, exiting"
else
        /bin/bash ctrl.sh halt
        sleep 20m
        kill -15 `cat ${STREAM_PID_FILE}`

        kill -15 `cat ${SYNC_PID_FILE}`
        echo "Killed process from pid file"
fi
