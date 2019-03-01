#!/bin/bash -eu
#
# Script to organize and cleanup backups.
# Should run daily as cronjob.

# Main mysql backup directory
BACKUP_DIR="/content/prod/pa/backup/mysql"

# Daily backup directory
DAILY_DIR=$BACKUP_DIR/daily

# Maximum number of days to keep daily backups
MAX_AGE_DAILY=7

# Weekly backup directory
WEEKLY_DIR=$BACKUP_DIR/weekly

# Maximum number of days to keep weekly backups
MAX_AGE_WEEKLY=30

# Monthly backup directory
MONTHLY_DIR=$BACKUP_DIR/monthly

# Maximum number of days to keep monthly backups
MAX_AGE_MONTHLY=$((365*2))


if [ "`whoami`" != "rasch" ]; then
	echo "Please run as rasch."
	exit 1
fi

if [ ! -d "$BACKUP_DIR" ]; then
	echo "Backup directory $BACKUP_DIR does not exist."
	exit 1
fi

DATE=`date +%Y-%m-%d-%H-%M-%S`

DAY_OF_WEEK=`date +%w`

DAY_OF_MONTH=`date +%d`

HOST=`hostname`
HOST=`echo $HOST | sed 's/\..*//'`

set -x
# If today is Sunday, hard link daily backup
# to weekly backup directory
if [ "$DAY_OF_WEEK" = "0" ]; then
	cp -l $DAILY_DIR/mysql.$HOST*$DATE.sql.bz2 $WEEKLY_DIR
fi

# If this is first of month, hard link daily backup
# to montly backup directory
if [ "$DAY_OF_MONTH" = "01" ]; then
	cp -l $DAILY_DIR/mysql.$HOST*$DATE.sql.bz2 $MONTLY_DIR
fi

# Now clean up old backs from daily, weekly, and monthly
# backup directories
find $DAILY_DIR -type f -name "mysql.$HOST*.sql.bz2" \
	-mtime "+$MAX_AGE_DAILY" | xargs --no-run-if-empty rm -v

find $WEEKLY_DIR -type f -name "mysql.$HOST*.sql.bz2" \
	-mtime "+$MAX_AGE_WEEKLY" | xargs --no-run-if-empty rm -v

find $MONTHLY_DIR -type f -name "mysql.$HOST*.sql.bz2" \
	-mtime "+$MAX_AGE_MONTHLY" | xargs --no-run-if-empty rm -v

# vim: set ts=4:
