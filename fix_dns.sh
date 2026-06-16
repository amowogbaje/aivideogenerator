#!/bin/sh
# 1. Start with the existing nameserver (127.0.0.11)
# 2. Add Google DNS as a fallback for external resolution
# 3. Use 'options ndots:0' to prevent unnecessary search domain lookups
echo "nameserver 127.0.0.11" > /etc/resolv.conf
echo "options ndots:0" >> /etc/resolv.conf
echo "nameserver 8.8.8.8" >> /etc/resolv.conf
echo "nameserver 8.8.4.4" >> /etc/resolv.conf

# Execute the application
exec "$@"