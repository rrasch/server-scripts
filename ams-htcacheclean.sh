#!/bin/bash
#
# Clean AMS Apache cache using htcacheclean

set -u

#MAX_SIZE=200M
MAX_SIZE=2000M

APACHE_HOME=/apps/adobe/ams/Apache2.4

CLEAN=$APACHE_HOME/bin/htcacheclean

#CACHE_ROOT=$APACHE_HOME/cacheroot
CACHE_ROOT=/data/adobe/ams/cacheroot

LOGFILE=/var/log/htcacheclean.log

APACHE_USER=ams

TIMESTAMP=`date "+%Y-%m-%d %H:%M:%S"`

if [ ! -f "$LOGFILE" ]; then
    touch $LOGFILE
fi

chown ams.dlib $LOGFILE

echo "----- $TIMESTAMP -----" >> $LOGFILE

# Run as user running apache because root can't
# write to thumper
su - -c "$CLEAN -v -p $CACHE_ROOT -n -t -l $MAX_SIZE" \
    $APACHE_USER >> $LOGFILE 2>&1

