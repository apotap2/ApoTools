#!/usr/bin/python

"""
multiplexer/demultiplexer code. can be useful if you have only serial with a device.
with this code it can create pseudoterminal on the device and client sides, and this
pty can be used with gdb server.
"""

import os
import select
import sys
import copy
import binascii
import atexit
import termios

STDIN_FILENO = 0
STDOUT_FILENO = 1
STDERR_FILENO = 2

CHILD = 0

def fork():
    """
    python 2.6 don't have it, so it's copy-pasted here.

    fork() -> (pid, master_fd)
    Fork and make the child a session leader with a controlling terminal.
    """

    try:
        pid, fdes = os.forkpty()
    except (AttributeError, OSError):
        pass
    else:
        if pid == CHILD:
            try:
                os.setsid()
            except OSError:
                # os.forkpty() already set us session leader
                pass
        return pid, fdes

    master_fd, slave_fd = os.openpty()
    pid = os.fork()
    if pid == CHILD:
        # Establish a new session.
        os.setsid()
        os.close(master_fd)

        # Slave becomes stdin/stdout/stderr of child.
        os.dup2(slave_fd, STDIN_FILENO)
        os.dup2(slave_fd, STDOUT_FILENO)
        os.dup2(slave_fd, STDERR_FILENO)
        if slave_fd > STDERR_FILENO:
            os.close(slave_fd)

        # Explicitly open the tty to make it become a controlling tty.
        tmp_fd = os.open(os.ttyname(STDOUT_FILENO), os.O_RDWR)
        os.close(tmp_fd)
    else:
        os.close(slave_fd)

    # Parent and child process.
    return pid, master_fd

COMM_CHAN_ID = '0'

class Demultiplexer:
    """
    Demultiplexer class. It uses a channel with id '0' as a common channel and
    multiplexes/demultiplexes others into/from it. It uses ascii for communication, so
    it should work with serial
    """

    STATE_NOT_MES = 0
    STATE_WAIT_START = 1
    STATE_READ_CHAN_ID = 2
    STATE_IN_MES = 3

    MES_DELIM = '<apotap111>'
    MES_END = '\n'

    def __init__(self):
        self._inputs = []
        self._chans_by_infd = {}
        self._chans_by_id = {}
        self._state = self.STATE_WAIT_START
        self._got_start_len = 0


    def run_loop(self):
        """
        Main loop of demultiplexer. Uses select to work with channels.
        """

        com_chan = self._chans_by_id[COMM_CHAN_ID]

        com_in_fd = com_chan['infd']
        com_out_fd = com_chan['outfd']

        cur_mes = ''
        cur_channel = None
        outputs = []

        while self._inputs:
            readable, _, exceptional = select.select(
                self._inputs, outputs, self._inputs)

            for input_ex in exceptional:
                if input_ex == com_in_fd:
                    raise Exception("Got exception in common channel")
                else:
                    channel = self._chans_by_infd.get(input_ex)
                    if channel:
                        self.remove_channel(channel)

            for input_read in readable:
                if input_read == com_in_fd:
                    if self._state == self.STATE_NOT_MES:
                        one_byte = os.read(com_in_fd, 1)
                        while one_byte != '':
                            if one_byte == self.MES_END:
                                self._state = self.STATE_WAIT_START
                                break
                            one_byte = os.read(com_in_fd, 1)

                    elif self._state == self.STATE_WAIT_START:
                        while self._state == self.STATE_WAIT_START:
                            one_byte = os.read(com_in_fd, 1)
                            if one_byte == '':
                                break
                            if one_byte == self.MES_END:
                                self._state = self.STATE_WAIT_START
                                self._got_start_len = 0
                                break
                            elif one_byte != self.MES_DELIM[self._got_start_len]:
                                self._state = self.STATE_NOT_MES
                                self._got_start_len = 0
                                break
                            else:
                                self._got_start_len += 1
                                if self._got_start_len == len(self.MES_DELIM):
                                    self._state = self.STATE_READ_CHAN_ID
                                    self._got_start_len = 0
                                    break

                    elif self._state == self.STATE_READ_CHAN_ID:
                        one_byte = os.read(com_in_fd, 1)
                        if one_byte != '':
                            if not self._chans_by_id.has_key(one_byte):
                                self._state = self.STATE_NOT_MES
                            else:
                                cur_channel = self._chans_by_id[one_byte]
                                self._state = self.STATE_IN_MES

                    elif self._state == self.STATE_IN_MES:
                        one_byte = os.read(com_in_fd, 1)
                        while one_byte != '':
                            if one_byte == self.MES_END:
                                outfd = cur_channel['outfd']
                                os.write(outfd, binascii.a2b_hex(cur_mes.strip()))

                                self._state = self.STATE_WAIT_START
                                cur_mes = ''
                                break
                            cur_mes += one_byte
                            one_byte = os.read(com_in_fd, 1)

                else:
                    if self._chans_by_infd.has_key(input_read):
                        buf = os.read(input_read, 1024 * 64)
                        if buf != '':
                            channel = self._chans_by_infd[input_read]
                            chan_id = channel['id']
                            buf = binascii.b2a_hex(buf)
                            buf = self.MES_DELIM + chan_id + buf + self.MES_END
                            os.write(com_out_fd, buf)

    def add_channel(self, channel):
        """
        add channel
        """

        infd = channel['infd']
        chan_id = channel['id']

        self._inputs.append(infd)
        self._chans_by_infd[infd] = channel
        self._chans_by_id[chan_id] = channel

    def remove_channel(self, channel):
        """
        remove channel
        """

        infd = channel['infd']
        chan_id = channel['id']

        self._inputs.remove(infd)
        self._chans_by_infd.pop(infd)
        self._chans_by_id.pop(chan_id)


SAVED_TERMS = {}

def reset_terminals():
    """
    reset terminal settings from SAVED_TERMS
    """

    for fdes, attr in SAVED_TERMS.items():
        termios.tcsetattr(fdes, termios.TCSANOW, attr)


def conf_bash_pty(pty_fd, main_term):
    """
    configure terminal that is used for bash
    """

    attr = termios.tcgetattr(pty_fd)

    if main_term and not SAVED_TERMS.has_key(pty_fd):
        SAVED_TERMS[pty_fd] = copy.deepcopy(attr)

    if not main_term:
        attr[1] &= ~termios.OPOST
    else:
        attr[3] &= ~termios.ECHO

    termios.tcsetattr(pty_fd, termios.TCSANOW, attr)


def conf_binary_pty(pty_fd):
    """
    configure terminal that is used for binary interrogation
    """

    attr = termios.tcgetattr(pty_fd)

    attr[3] &= ~(termios.ECHO | termios.ICANON)
    attr[1] &= ~termios.OPOST

    termios.tcsetattr(pty_fd, termios.TCSANOW, attr)

def create_channel(infd, outfd, chan_id):
    """
    create channel structure
    """

    result = {}
    result['id'] = chan_id
    result['infd'] = infd
    result['outfd'] = outfd

    return result

def demul_server(nopost):
    """
    run as a server, difference between server and client is that a server
    creates bash and session.
    """

    print "server"

    try:
        conf_bash_pty(sys.stdin.fileno(), True)
    except:
        pass

    pty_pid, pty_fd = fork()

    if pty_pid == CHILD:
        if nopost:
            conf_bash_pty(sys.stdin.fileno(), False)

        os.execlp("bash", "bash")
    else:
        demultiplexer = Demultiplexer()
        common_chan = create_channel(sys.stdin.fileno(), sys.stdout.fileno(), '0')

        pty2_master_fd, pty2_slave_fd = os.openpty()
        conf_binary_pty(pty2_master_fd)
        conf_binary_pty(pty2_slave_fd)

        bash_chan = create_channel(pty_fd, pty_fd, '1')
        second_chan = create_channel(pty2_master_fd, pty2_master_fd, '2')

        print "pty is " + os.ttyname(pty2_slave_fd)

        demultiplexer.add_channel(common_chan)
        demultiplexer.add_channel(second_chan)
        demultiplexer.add_channel(bash_chan)

        demultiplexer.run_loop()


def demul_client(fname, fname2=None):
    """
    run as a client
    """

    print "client"

    demultiplexer = Demultiplexer()

    if not fname2:
        fdes = os.open(fname, os.O_RDWR)
        fdes2 = fdes
    else:
        fdes = os.open(fname, os.O_RDONLY)
        fdes2 = os.open(fname2, os.O_WRONLY)

    pty_master_fd, pty_slave_fd = os.openpty()
    conf_binary_pty(pty_master_fd)
    conf_binary_pty(pty_slave_fd)

    print "first(bash) pty is " + os.ttyname(pty_slave_fd)

    pty2_master_fd, pty2_slave_fd = os.openpty()
    conf_binary_pty(pty2_master_fd)
    conf_binary_pty(pty2_slave_fd)

    print "second pty is " + os.ttyname(pty2_slave_fd)

    common_chan = create_channel(fdes, fdes2, '0')
    bash_chan = create_channel(pty_master_fd, pty_master_fd, '1')
    second_chan = create_channel(pty2_master_fd, pty2_master_fd, '2')

    demultiplexer.add_channel(common_chan)
    demultiplexer.add_channel(second_chan)
    demultiplexer.add_channel(bash_chan)

    demultiplexer.run_loop()

if __name__ == '__main__':
    atexit.register(reset_terminals)

    if len(sys.argv) == 1:
        demul_server(False)
    elif len(sys.argv) == 2 and sys.argv[1] == 'nopost':
        demul_server(True)
    elif len(sys.argv) == 2:
        demul_client(sys.argv[1])
    else:
        demul_client(sys.argv[1], sys.argv[2])
