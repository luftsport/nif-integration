#!/bin/bash

INVENV=$(python -c 'import sys; print ("1" if hasattr(sys, "real_prefix") else "0")')

WORKING_DIR="${PWD}/"
GUNICORN="${PWD}/bin/gunicorn"

cd $WORKING_DIR

if [[ INVENV == 0 ]]
then
        source bin/acticate
fi

$GUNICORN --workers=5 --threads=20 --worker-class=meinheld.gmeinheld.MeinheldWorker -b localhost:9191 run:app --log-level=debug --log-file=unicorn.log --pid gunicorn.pid &

if [[ INVENV == 0 ]]
then
        deactivate
fi

cd