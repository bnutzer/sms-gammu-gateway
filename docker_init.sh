#!/bin/sh

if  [ ! -z "$MODEM" ] ; then
	echo "Updating gammu device to ${MODEM} ..."
	sed -E "s#^(device\s+=\s*).*#\1${MODEM}#" gammu.config
	echo "Done."
fi

exec python run.py
