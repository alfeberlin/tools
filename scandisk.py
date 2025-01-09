#!/usr/bin/env python3
#
# scandisk takes a disk device as argument and tries to read (write)
#          to many parts of it to find i/o errors quickly.
#

import sys, time, random, math, os, array

class Protocol(object):
    def __init__(self, size, chunk_size):
        self.size       = size
        self.chunk_size = chunk_size
        # protocol: one character for each chunk
        # '_': untested
        # '+': good chunk
        # 'X': bad chunk
        self.protocol = ['_'] * ((size+chunk_size-1) // chunk_size)
        # display: one character for a bunch of chunks
        self.display = ['_'] * 79
        # chars to be used to display test results (1 block known, .. 100%)
        #self.display_chars  = '-+*#@'
        self.display_chars  = '_' + ('abcdefghijklmnopqrstuvwxyz'
                                     'ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        # colors in a raising value order (from dark to light):
        self.display_colors = [ '',  # nothing
                                '\x1b[0;30m', # black
                                '\x1b[0;34m', # blue
                                '\x1b[0;31m', # red
                                '\x1b[0;35m', # purple
                                '\x1b[0;32m', # green
                                '\x1b[0;36m', # cyan
                                '\x1b[0;33m', # yellow
                                # do not use: '\x1b[0;37m', # white
                                ]
        # if no chunk is bad (yet):
        #   char =^= percentage of tested chunks per slice
        #   color = black
        # else (at least one chunk is bad):
        #   char will be inverted
        #   char =^= percentage of good chunks per slice
        #   color =^= percentage of bad chunks per tested (from dark to light)

    def get_percentage_element(self, elements, value, sum):
        if value == sum:
            return elements[-1]
        if value == 0:
            return elements[0]
        return elements[1 + (value * (len(elements)-2) // sum)]
 
    def display_pos2protocol_slice(self, display_pos):
        return slice( display_pos    * len(self.protocol) // 79,
                     (display_pos+1) * len(self.protocol) // 79)

    def update_display(self, protocol_pos):
        display_pos = protocol_pos * 79 // len(self.protocol)
        count_good     = 0
        count_bad      = 0
        count_untested = 0
        protocol_slice = self.display_pos2protocol_slice(display_pos)
        protocol_slice_length = protocol_slice.stop - protocol_slice.start
        for protocol_element in self.protocol[protocol_slice]:
            if   protocol_element == '+':  # good?
                count_good     += 1
            elif protocol_element == 'X':  # bad?
                count_bad      += 1
            elif protocol_element == '_':  # untested?
                count_untested += 1
            else:
                raise Exception('internal error: %r' %
                                self.protocol[protocol_pos])
        if count_bad == 0:
            self.display[display_pos] = self.get_percentage_element(
                self.display_chars, count_good, protocol_slice_length)
        else:
            self.display[display_pos] = self.get_percentage_element(
                self.display_colors, count_bad, count_bad + count_good)
            self.display[display_pos] += '\x1b[7m'  # inverse on
            self.display[display_pos] += self.get_percentage_element(
                self.display_chars, count_good + count_bad,
                protocol_slice_length)
            self.display[display_pos] += '\x1b[0m'  # reset

    def set_pos_good(self, pos):
        protocol_pos = pos // self.chunk_size
        self.protocol[protocol_pos] = '+'
        self.update_display(protocol_pos)

    def set_pos_bad(self, pos):
        protocol_pos = pos // self.chunk_size
        self.protocol[protocol_pos] = 'X'
        self.update_display(protocol_pos)

    def get_display(self):
        return ''.join(self.display)


chunk_size = 1 << 20  # one megabyte

usage = '''
usage: %s [options] <device>
       options include:
         -w      do a write test also
         -s <n>  use a chunk size of <n> (defaults to %d)
         -m <m>  set method: l: linear, s: spread, lc: linear coarse
         -k <#>  skip the first <#> chunks (simulate testing them only)
''' % (sys.argv[0], chunk_size)

write_test = 0
method = 's'  # spread
skip_count = 0
try:  # argument parsing
    while sys.argv[1].startswith('-'):
        if   sys.argv[1] == '-w':
            del sys.argv[1]
            write_test = 1
        elif sys.argv[1] == '-s':
            del sys.argv[1]
            chunk_size = long(sys.argv.pop(1))
        elif sys.argv[1] == '-m':
            del sys.argv[1]
            method = sys.argv.pop(1)
        elif sys.argv[1] == '-k':
            del sys.argv[1]
            skip_count = long(sys.argv.pop(1))
        else:
            raise Exception("Bad option: %r" % sys.argv[1])
    dev = sys.argv.pop(1)
    if len(sys.argv) > 1:
        raise Exception("Too many arguments given")
except Exception as problem:
    print(usage)
    print("Error:", problem)
    sys.exit(1)

try:  # find out whether fd 3 is open for us to dump progress info
    os.write(3, "# scandisk progress info starting at %s\n" % time.ctime())
    os.write(3, "%f %f\n" % (time.time()/86400.0, 0.0))
except:
    progressinfo = False
else:
    progressinfo = True

# open the device
if write_test:
    f = open(dev, 'r+b')
else:
    f = open(dev, 'rb')

# find out the size of the device
f.seek(0, 2)  # eof
size = f.tell()

protocol = Protocol(size, chunk_size)

class Progress_Predicter(object):
    def __init__(self):
        self.values = []
        self.last_toas = None
        self.last_toa_pos = 0
        #self.floating_toa = None

    def add_new_value(self, max, pos):
        #if len(self.values) > 1000:  # smaller the list
        #    x = []
        #    for i in range(0, len(self.values), 10):
        #        x.append(self.values[i])
        #    self.values = x
        if len(self.values) > 200:  # smaller the list
            del self.values[0:100]
            if progressinfo:
                os.write(3, '%f %.5f\n' %
                         (time.time()/86400.0, pos * 100.0 / max))
        self.values.append((time.time(), max, pos))

    def get_toa(self):
        (start_time, start_max, start_pos) = self.values[0]
        ( last_time,  last_max,  last_pos) = self.values[-1]
        time_passed = last_time - start_time
        pos_passed  = last_pos  - start_pos
        if pos_passed == 0:
            return time.time() + 1  # cheap version to avoid div-by-zero
        predicted_end_time = (time_passed * (last_max - start_pos) /
                              pos_passed + start_time)
        if self.last_toas is None:
            self.last_toas = [ predicted_end_time ] * 300
        else:
            self.last_toas[self.last_toa_pos] = predicted_end_time
            self.last_toa_pos += 1
            self.last_toa_pos %= len(self.last_toas)
        return sum(self.last_toas) // len(self.last_toas)
        #if self.floating_toa is None:
        #    self.floating_toa = predicted_end_time
        #else:
        #    self.floating_toa = (self.floating_toa * 299 +
        #                         predicted_end_time) / 300
        #return self.floating_toa

pos_count = 0
progress_predicter = Progress_Predicter()
def display_pos(pos, max, style=None, pos_count_inc=1):
    global pos_count, progress_predicter, skip_count
    progress_predicter.add_new_value(max, pos_count)
    if style is None:
        style = 'graphic' if int(time.time() * 2) & 2 else 'numbers'
    if   style == 'numbers':
        sys.stderr.write('\r%s%d/%d%s (%.5f%%) 0x%012x'
                         ' == %14s (TOA: %s)\x1b[K' %
                         (('(' if skip_count > 0 else ""),
                          pos_count, max,
                          (')' if skip_count > 0 else ""),
                          pos_count * 100.0 / max, pos, pos,
                          time.ctime(progress_predicter.get_toa())[4:19]))
    elif style == 'graphic':
        sys.stderr.write('\r' + protocol.get_display())
    else:
        raise Exception('internal error %r' % style)
    sys.stdout.flush()
    pos_count += pos_count_inc
    #print
    #print ''.join(protocol.protocol[0:78])
    #print

class DifferenceFound(Exception):  pass

pattern1 = b'\xaa' * chunk_size
pattern2 = b'\x55' * chunk_size

def check_pos(pos):
    ## debug code:
    #sys.stdin.readline()
    #if random.randint(0, 1000) > int(400 - 700 * math.cos(pos * 15.0 / size)):
    #    protocol.set_pos_good(pos)
    #else:
    #    protocol.set_pos_bad(pos)
    #return
    global chunk_size, write_test, pattern1, pattern2, protocol, skip_count
    attempt = 'attempting nothing yet'
    try:
        if skip_count > 0:
            skip_count -= 1
        else:
            attempt = 'first reading'
            f.seek(pos);  original = f.read(chunk_size)
            if write_test:
                try:
                    attempt = 'writing pattern 1'
                    f.seek(pos);  f.write(pattern1);
                    attempt = 'reading pattern 1'
                    f.seek(pos);  read_pattern1 = f.read(chunk_size)
                    if read_pattern1 != pattern1:
                        print(" difference found at write pattern1!")
                    attempt = 'writing pattern 2'
                    f.seek(pos);  f.write(pattern2);
                    attempt = 'reading pattern 2'
                    f.seek(pos);  read_pattern2 = f.read(chunk_size)
                    if read_pattern2 != pattern2:
                        print(" difference found at write pattern2!")
                finally:
                    attempt = 'writing original'
                    f.seek(pos);  f.write(original);
                attempt = 'second reading'
                f.seek(pos);  second_original = f.read(chunk_size)
                if second_original != original:
                    raise DifferenceFound(pos)
    except KeyboardInterrupt as e:
        raise e  # do not catch KeyboardInterrupt, but anything else (below)
    except DifferenceFound as e:
        display_pos(pos, size/chunk_size, style='numbers', pos_count_inc=0)
        print(" difference found at re-read of original!")
        protocol.set_pos_bad(pos)
    except Exception as e:
        display_pos(pos, size/chunk_size, style='numbers', pos_count_inc=0)
        print("\nCaught Exception %s\n"
              "at pos 0x%012x == %s\tduring %s" % (e, pos, pos, attempt))
        protocol.set_pos_bad(pos)
    else:
        protocol.set_pos_good(pos)

def linear_coarse(size, max=100000):
    for i in range(max):
        pos = size * i // max
        display_pos(pos, max)
        check_pos(pos)

def linear(chunk_size, size):
    global skip_count
    #for pos in range(0, size, chunk_size):
    start = skip_count * chunk_size
    skip_count = 0
    for pos in range(start, size, chunk_size):
        display_pos(pos, size // chunk_size)
        check_pos(pos)

def spread(pos, width, size):
    if width < size:
        spread(pos, width << 1, size)
        if pos + width < size:
            spread(pos + width, width << 1, size)
    else:
        display_pos(pos, size // chunk_size)
        check_pos(pos)

try:
    if   method == 's':
        spread(0, chunk_size, size)
    elif method == 'l':
        linear(chunk_size, size)
    elif method == 'lc':
        linear_coarse(size)
    else:
        raise Exception("Bad method (%s).  Consult usage." % method)
    display_pos(0, size // chunk_size, style='graphic')
except KeyboardInterrupt:
    print
    print(" aborted")
human_size = size
suffixes = ' kMGT'
while human_size >= 1<<10 and len(suffixes) > 1:
    human_size >>= 10
    suffixes = suffixes[1:]
print
print("protocol:")
print("chunk_size =", chunk_size, " size =", size, \
      "(%d%s)" % (human_size, suffixes[0]), \
      " chunks (+ good, X bad, _ untested):")
f = os.popen('od -t c -w64 -Ax | sed "s/   //g"', 'w')
f.write(''.join(protocol.protocol))  # better have a large scrollbuffer!
f.close()
