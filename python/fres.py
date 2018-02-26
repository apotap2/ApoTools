#!/usr/bin/python
"""
uudecode analogue. read from stdin, decodes into file
"""


import binascii

import sys

def main():
    """
    main function
    """

    out_file = open(sys.argv[1], 'wb')

    decoded = ''

    while True:
        buf = sys.stdin.readline(1024*1024)
        if not buf:
            break
        stripped = buf.strip()
        print len(stripped)
        decoded = binascii.a2b_hex(stripped)
        out_file.write(decoded)

    out_file.close()

if __name__ == '__main__':
    main()
