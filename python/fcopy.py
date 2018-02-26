#!/usr/bin/python

"""
uuencode analogue. encodes file with binascii and saves it to out.txt
"""

import binascii
import sys

def main():
    """
    main function
    """

    out_file = open('out.txt', 'w')

    with open(sys.argv[1], "rb") as binary_file:
        # Read the whole file at once
        data = binary_file.read()
        total = len(data)
        i = 0
        while i < total:
            left = total - i
            encode_now = min(left, 2000)
            encoded = binascii.b2a_hex(data[i:i+encode_now])
            out_file.write(encoded)
            out_file.write('\n')
            i += encode_now

    out_file.close()

if __name__ == '__main__':
    main()
