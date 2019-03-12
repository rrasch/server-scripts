#!/bin/bash

AMS_HOME=/apps/adobe/ams

APACHE_HOME=$AMS_HOME/Apache2.4

export LD_LIBRARY_PATH=$AMS_HOME:$APACHE_HOME/lib

cd $APACHE_HOME

$APACHE_HOME/bin/httpd \
	-f $APACHE_HOME/conf/httpd.conf \
	-d $APACHE_HOME \
	-t

