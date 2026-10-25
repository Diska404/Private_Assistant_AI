"""Isolated install helper: prefer IPv4 for this process on this laptop's network."""
import socket
import sys

from pip._vendor.urllib3.util import connection
connection.allowed_gai_family = lambda: socket.AF_INET
from pip._internal.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
