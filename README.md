# ApoTools

My tools

if you have a device with python and serial (and most probably minicom), next can be useful:
Python:
fcopy.py - uuencode analogue. encodes file with binascii and saves it to out.txt
fres.py - uudecode analogue. read from stdin, decodes into file

analogue here is in terms of usage case. there is often python (sometimes 2.6) but no 
uuencode or base64 stuff and you need to send files.
fcopy, fres and minicom's ascii send or copy-paste can be used.

demul.py - multiplexer/demultiplexer code. can be useful if you have only serial with a device.
with this code it can create pseudoterminal on the device and client sides, and this
pty can be used with gdb server. You will run it without arguments on the server side (or you can pass 
nopost) exit from minicom and use one serial for bash and gdbserver.

