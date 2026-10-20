#!/bin/bash

# Ensure an IP address argument was provided
if [ -z "$1" ]; then
	echo "Error: Missing IP address argument."
	echo "Usage: $0 <IP_ADDRESS>"
	exit 1
fi

TARGET_IP="$1"

# Verify dig is installed on the system
if ! command -v dig &> /dev/null; then
	echo "Error: 'dig' command line tool is not installed. Please install 'dnsutils' or 'bind-utils'."
	exit 1
fi

# Extract nameservers from /etc/resolv.conf and loop through them
awk '/nameserver/ {print $2}' /etc/resolv.conf | while read -r ns; do
	echo "========================================="
	echo "Querying Nameserver: $ns"
	echo "========================================="

	# Run the reverse lookup
	RESULT=$(dig @"$ns" -x "$TARGET_IP" +short)

	if [ -z "$RESULT" ]; then
		echo "No reverse DNS record found (NXDOMAIN / Timeout)."
	else
		echo "Result: $RESULT"
	fi
	echo ""
done
