#!/usr/bin/env python3

"""\
directories -- a module for mangling directories, files, and trees of them
               Copyright by Alfe 2007-Feb-2
"""

import inspect

import stat, os, time, sys, select, array, heapq, random
import termios, fcntl, struct  # for get_window_size()

CHUNK_SIZE = (1 << 16)  # used for reading/copying
CHUNK_SIZE = int(os.getenv('DIRECTORIES_CHUNK_SIZE', str(CHUNK_SIZE)))

# for Ancestry instances:
TIMES_CACHE_SIZE = int(os.getenv('DIRECTORIES_TIMES_CACHE_SIZE', '200'))
# ^^^ number of times memorized in each Ancestry element
TIMES_CACHE_CHUNK = int(os.getenv('DIRECTORIES_TIME_CACHE_CHUNK', '50'))
# ^^^ number of times forgotten on overflow of cache
TIMES_MIN_DISTANCE = float(os.getenv('DIRECTORIES_TIMES_MIN_DISTANCE', '1.0'))
# ^^^ number of seconds at least between entries

class kmg:
  """
  class kilo-mega-giga (a kind of int with more semantics) supported
  perfixes: Kilo, Mega, Giga, Tera, Peta, Exa, Zetta, Yotta
  This class uses powers of two, so it is not SI compatible.
  """

  chars = 'KMGTPEZY'

  def __init__(self, text):
    if not isinstance(text, str):
      text = "%s" % text
    for i in range(len(self.chars)):
      if text.lower().endswith(self.chars[i].lower()):
        factor = 1 << (10 * (i + 1))
        text = text[:-1]
        break
    else:  # no break case
      factor = 1
    self.value = float(text)
    self.value *= factor
    self.value = int(self.value)

  def get_value(self):
    return self.value

  def get_factor(self):
    for i in reversed(range(len(self.chars))):
      if self.value >= 1000 * (1 << (10 * i)):
        factor, char = 1 << (10 * (i + 1)), self.chars[i]
        break
    else:  # no break case
      factor, char = 1, None
    return factor, char

  def __repr__(self):
    return "kmg('%d')" % self.value

  def __str__(self):
    factor, char = self.get_factor()
    s = '%1.1f' % (self.value / factor)
    if len(s) > 3 or not char:
      return '%d%s' % (self.value / factor, char or '')
    else:
      return s + (char or '')

def get_window_size(file=None, fn=None):
  if fn is None:
    if file is None:
      file = sys.stdout
    fn = file.fileno()
  return struct.unpack('hh', fcntl.ioctl(fn, termios.TIOCGWINSZ, '1234'))

ONE_MINUTE = 60
ONE_HOUR   = 60 * ONE_MINUTE
ONE_DAY    = 24 * ONE_HOUR

def duration_to_string(duration):
  if   duration > ONE_DAY:
    return "%dd%02dh" % (duration // ONE_DAY,
                         duration % ONE_DAY // ONE_HOUR)
  elif duration > ONE_HOUR:
    return "%dh%02dm" % (duration // ONE_HOUR,
                         duration % ONE_HOUR // ONE_MINUTE)
  elif duration > ONE_MINUTE:
    return "%dm%02ds" % (duration // ONE_MINUTE,
                         duration % ONE_MINUTE)
  else:
    return "%.2fs" % duration

def time_to_string(moment):
  today = time.localtime()[:3]
  day   = time.localtime(moment)[:3]
  if day == today:
    return time.strftime("%H:%M:%S", time.localtime(moment))
  elif time.time() - ONE_DAY * 3 < moment < time.time() + ONE_DAY * 3:
    return time.strftime("%a %H:%M", time.localtime(moment))
  elif time.time() - ONE_DAY * 15 < moment < time.time() + ONE_DAY * 15:
    return time.strftime("%m-%d %Hh", time.localtime(moment))
  else:
    return time.strftime("%Y-%m-%d", time.localtime(moment))

class TTY(object):
  esc       = '\x1b'
  # -------------------------- output sequences
  norm      = esc + '[0m'
  underline = esc + '[4m'
  inverse   = esc + '[7m'
  blue      = esc + '[34m'
  black     = esc + '[30m'
  home      = esc + '[H'
  clearEOL  = esc + '[K'
  clearEOS  = esc + '[0J'  # clear to end of screen, clear below
  clear     = esc + '[2J'  # clear whole screen
  cr        = '\r'
  nl        = '\n'
  breakoff  = esc + '[?7l'  # automatic line break
  breakon   = esc + '[?7h'
  save      = esc + '7'  # save cursor position
  restore   = esc + '8'  # restore cursor position
  buffer0   = esc + '[?47l'  # use normal screen buffer
  buffer1   = esc + '[?47h'  # use alternate screen buffer
  # -------------------------- input sequences (keys)
  up        = esc + '[A'
  down      = esc + '[B'
  right     = esc + '[C'
  left      = esc + '[D'

class Counter(tuple):
  def files(self):  return self[0]
  def bytes(self):  return self[1]

  def __add__(self, other):
    assert isinstance(other, Counter)
    return Counter((self.files() + other.files(), self.bytes() + other.bytes()))

class Path_Size(tuple):
  def __str__(self):
    if self.has_contents():
      return ("%d %d %s/\n  " % (
          self.counter().files(),
          self.counter().bytes(),
          self.path()) + '\n  '.join('\n  '.join(str(s).split('\n'))
                                     for s in self.contents()))
    else:
      return ("%d %d %s" % (
          self.counter().files(),
          self.counter().bytes(), self.path()))

  def counter(self):       return self[0]
  def path(self):          return self[1]
  def contents(self):      return self[2]
  def has_contents(self):  return self.contents() is not None

class Ancestry(list):
  '' "represents information about the call path which lead us to the"\
     " current situation; each element contains its father (the node above"\
     " in the tree), progress information and times for ETA estimization"
  def __init__(self, values):
    list.__init__(self, list(values))
    self.times = [ (time.time(), Counter((0, 0))) ]

  def __repr__(self):  return 'Ancestry(' + list.__repr__(self) + ')'

  def __str__(self):
    return (TTY.breakoff +
            (TTY.clearEOL + '\n').join(self.display()) +
            TTY.breakon)

  def add_time(self, value):
    if (len(self.times) < 1 or
      time.time() > self.times[-1][0] + 1.0):
      self.times.append((time.time(), value))
      if len(self.times) > TIMES_CACHE_SIZE:  # tidy up times cache
        ## # find the indices which are farthest away from the linear
        ## # time distribution between the beginning of this Ancestry
        ## # and the current time:
        ## indices = heapq.nlargest(TIMES_CACHE_CHUNK,
        ##              range(1, len(self.times)),
        ##              key=(lambda index:
        ##                 (self.times[0][0] +
        ##                  float(self.times[-1][0]-
        ##                    self.times[0][0]) *
        ##                  index//len(self.times) -
        ##                  self.times[index][0]) //
        ##                 index))
        # find the indices of the elements which are most linear in the
        # curve (most nothing-saying and so prunable because linearly
        # interpolatable anyway):
        indices = heapq.nsmallest(
          TIMES_CACHE_CHUNK, range(1, len(self.times)-1),
          key=(lambda index:
             abs(((self.times[index-1][1].bytes() -
                 self.times[index  ][1].bytes()) /
                (self.times[index-1][0] -
                 self.times[index  ][0])) -
               ((self.times[index  ][1].bytes() -
                 self.times[index+1][1].bytes()) /
                (self.times[index  ][0] -
                 self.times[index+1][0])))))
        # the following code removes the element of the found indices:
        indices.sort()
        indices.reverse()
        for index in indices:
          del self.times[index]
    start, end, path, father = self
    if father is not None:
      father.add_time(value)

  def get_times(self):  return self.times

  def get_counter(self, time):
    "returns the interpolated counter at the given time"
    i = 2
    while self.times[-i][0] > time:
      i -= 1
      if i < 0:
        raise Exception("no extrapolation possible")
    t0 = self.times[-i][0]
    t1 = self.times[-i+1][0]
    x0 = self.times[-i][1].bytes()
    x1 = self.times[-i+1][1].bytes()
    if t0 == time:
      return x0
    # (x1 - x0) / (t1 - t0) == (x - x0) / (time - t0)
    return (x1 - x0) / (t1 - t0) * (time - t0) + x0

  def get_father(self):  return self[3]

  def set_current_counter(self, current_counter):
    self[0] = current_counter
    self.add_time(current_counter)

  def set_end_counter(self, end_counter):
    self[1] = end_counter

  def set_path(self, path):
    self[2] = path

  #def whole(self):
  #  start, end, path, father = self
  #  if father is None:  return start, end
  #  else:         return father.whole()

  def get_root(self):
    father = self.get_father()
    if father is None:  return self
    else:  return father.get_root()

  def get_depth(self):
    father = self.get_father()
    if father is None:  return 1
    else:  return 1 + father.get_depth()

  def progress(self, value):
    start, end, path, father = self
    if father is None:
      return []
    start = start.bytes()
    end   =   end.bytes()
    father_start, father_end, father_path, grandfather = father
    father_start   = father_start.bytes()
    father_end     =   father_end.bytes()
    size           = (father_end-father_start)
    start_of_chunk = (     start-father_start)
    position       = (     value-father_start)
    end_of_chunk   = (       end-father_start)
    return (father.progress(value) +
        [ (path, start_of_chunk, position, end_of_chunk, size,
            self.times) ])

  def display(self, value=None, width=None, smooth_time={}, smoothness=30):
    if width is None:  height, width = get_window_size()
    if value is None:  value = self[0].bytes()
    result = []
    for path, start, value, end, size, times in self.progress(value):
      elapsed = time.time() - times[0][0]
      if not size:
        line = '%-*s' % (width, "(empty)")
      else:
        percent = value * 100.0 / size
        percent_step = percent / elapsed
        if percent_step > 20.0:  # very fast -> display rough values
          decimals = -1
        elif percent_step > 10.0:  # medium speed -> display percent
          decimals = 0
        else:  # slow -> display permille
          decimals = 1
        percent = round(percent, decimals)
        line = '%5.1f%%   %s/%s' % (percent, kmg(value), kmg(size))
        line = list('%-*s' % (width, line))
        line.append('')  # to avoid ugliness at line[end]
        start_v = start * width // size
        value_v = value * width // size
        end_v = end * width // size
        line[start_v]  = TTY.underline + line[start_v]
        line[value_v]  = TTY.norm + TTY.underline + line[value_v]
        #                  end inverse/start underline
        try:
          line[end_v]   += TTY.norm        # end underline
        except Exception as e:
          e.args += (end_v,)
          raise
        line[0]        = TTY.inverse + line[0]
        line = ''.join(line)
      result.append(line)
      if value > 0:
        etoa = (elapsed * (size - value) / value) + times[-1][0]
        if path in smooth_time:
          etoa = (smoothness * smooth_time[path] + etoa) / (smoothness + 1)
          smooth_time[path] = etoa
        etta = etoa - time.time()
        if etta < 0:
          result.append(("%s + %s (imminent)" % (
            time_to_string(times[0][0]),
            duration_to_string(elapsed))))
        else:
          result.append(("%s + %s + %s = %s" % (
            time_to_string(times[0][0]),
            duration_to_string(elapsed),
            duration_to_string(etta),
            time_to_string(etoa))))
      else:
        result.append(("%s + %s (no prediction)" % (
          time_to_string(times[0][0]),
          duration_to_string(elapsed))))
      result.append(path.split('/')[-1][-width:])
    return result

  def plot(self, depth=None):
    gnuplot = os.popen('gnuplot -persist -geometry +0+0', 'w')
    gnuplot.write(
        "set ytics auto\n"
        "set ytics nomirror\n"
        "set y2tics auto\n"
        "set y2tics nomirror\n"
        "plot [0:] [0:100]             \\\n"
        "   [0:]                 \\\n"
        "   '-'       with linespoints lw 3, \\\n"
        "   '-' axes x1y2 with linespoints lw 1\n")
    if depth is None:
      element = self.get_root()
    else:
      element = self
      for i in range(depth):
        element = element.get_father()
    times = element.get_times()
    end_bytes = element[1][1]
    for dummy in ('scaled', 'format filling'):
      for time, (files, bytes) in times:
        gnuplot.write('%f %f\n' %
                      (time - times[0][0], bytes * 100.0 / end_bytes))
      gnuplot.write('e\n')
    gnuplot.close()

def sizeof_path(path, report=None, follow_links=None, target=None,
                add_report=None):
  """
  return a tuple of the counter (files and bytes) of a path given as a string
  (or of a path list given as string list which then will be handled as a
  pseudo dir), the given path name itself, and the contents of this path; if
  the path points to a plain file, this contents will be None; if the path
  points to a directory, the contents will be a list of results of this
  function for each entry in this directory
  """
  if follow_links is None:  follow_links = False
  if isinstance(path, list):
    results = []
    counter = Counter((0, 0))
    for entry in path:
      if target is not None and os.path.isfile(os.path.join(target, entry)):
        if add_report is not None:
          add_report("Skipped existing: %s" % entry)
        continue
      if callable(report):
        result = sizeof_path(
            entry, lambda path, c: report(path, counter + c),
            follow_links=follow_links, target=target, add_report=add_report)
      else:
        result = sizeof_path(
            entry,
            follow_links=follow_links, target=target, add_report=add_report)
      results.append(result)
      entry_counter, p, entries = result
      counter += entry_counter
    return Path_Size((counter, '', results))
  if callable(report):
    report(path, Counter((0, 0)))  # report receives a counter
  try:
    current_stat = (os.stat if follow_links else os.lstat)(path)
  except OSError:  # no such file or directory?
    return Path_Size((Counter((0, 0)), path, None))
  mode = current_stat.st_mode
  if   stat.S_ISDIR(mode):
    try:
      entries = [ path + '/' + entry for entry in sorted(os.listdir(path)) ]
    except OSError:  # permission denied?
      entries = []  # TODO: make this behaviour configurable
    results = []
    counter = Counter((0, 0))
    for entry in entries:
      if target is not None and os.path.isfile(os.path.join(target, entry)):
        if add_report is not None:
          add_report("Skipped existing: %s" % entry)
        continue
      if callable(report):
        result = sizeof_path(
            entry, lambda path, c: report(path, counter + c),
            follow_links=follow_links, target=target, add_report=add_report)
      else:
        result = sizeof_path(
            entry,
            follow_links=follow_links, target=target, add_report=add_report)
      results.append(result)
      entry_counter, p, entries = result
      counter += entry_counter
    return Path_Size((counter, path, results))
  elif stat.S_ISREG(mode):
    return Path_Size((Counter((1, current_stat.st_size)), path, None))
  elif stat.S_ISBLK(mode):   return Path_Size((Counter((0, 0)), path, None))
  elif stat.S_ISCHR(mode):   return Path_Size((Counter((0, 0)), path, None))
  elif stat.S_ISFIFO(mode):  return Path_Size((Counter((0, 0)), path, None))
  elif stat.S_ISLNK(mode):   return Path_Size((Counter((0, 0)), path, None))
  elif stat.S_ISSOCK(mode):  return Path_Size((Counter((0, 0)), path, None))
  else:
    raise Exception("internal error: %r" % (mode,))

last_report_time = 0

def report(path, ancestry, message, cursor_pos=0, width=None):
  global last_report_time
  if last_report_time + 0.05 < time.time():
    last_report_time = time.time()
    try:
      if width is None:  height, width = get_window_size()
      print(TTY.home + '\n' +
            path[-width:] + TTY.clearEOL + '\n' +
            str(ancestry) + TTY.clearEOS +
            TTY.home + message + TTY.clearEOL +
            '\n\n\n\n' * cursor_pos,
            end='', flush=True)
    except Exception as problem:
      print("Problem while reporting:", problem, repr(path), repr(message), repr(ancestry))

def report_scan(path, counter):
  global last_report_time
  if last_report_time + 0.05 < time.time():
    last_report_time = time.time()
    try:
      print(TTY.cr + TTY.clearEOL + TTY.breakoff +
            '%6d %11d %r' % (counter.files(), counter.bytes(), path) +
            TTY.breakon,
            end='', flush=True)
    except Exception as problem:
      print("Problem while reporting:", problem, repr(path), repr(counter))

##########  generator versions  ##########

class Node(tuple):  pass
class Leaf(Node): pass

def tree_traverser(tree, depth=False, ancestry=None):
  """
  walks a tree as returned by sizeof_path() and yields positions in that tree
  (with ancestry); if depth is True then children are handled before the nodes
  """
  counter, path, contents = tree
  if ancestry is None:
    ancestry = Ancestry((Counter((0, 0)), counter, path, None))
  if contents is None:  # this is just a leaf
    yield Leaf((path, ancestry))
  else:  # this is a node
    current_counter, end_counter, father_path, father_ancestry = ancestry
    if not depth:
      yield Node((path, ancestry))
    ancestry2 = Ancestry((current_counter, end_counter, "", ancestry))
    for child in contents:
      end_counter = current_counter + child.counter()
      ancestry2.set_current_counter(current_counter)
      ancestry2.set_end_counter(end_counter)
      ancestry2.set_path(child.path())
      traverser = tree_traverser(child, depth=depth, ancestry=ancestry2)
      for node in traverser:
        yield node
      current_counter = end_counter
    if depth:
      yield Node((path, ancestry))

class Bad_Leaf(Node):  pass
class Special( Node):  pass
class File_Open(Leaf):  pass
class EOF(      Leaf):  pass
class Data(     Leaf):  pass

# the tree_reader_buffer is also used by the consumer of the Data()
tree_reader_buffer = array.array('b')
tree_reader_buffer.frombytes(b'-')

def tree_reader(tree, chunk_size=CHUNK_SIZE, follow_links=None):
  if follow_links is None:  follow_links = False
  stat_fun = os.stat if follow_links else os.lstat
  global tree_reader_buffer
  tree_reader_buffer = array.array('b')
  tree_reader_buffer.frombytes(b'-' * chunk_size)
  for node in tree_traverser(tree):
    if not isinstance(node, Leaf):
      yield node
      continue  # skip the rest
    path, ancestry = node
    try:
      mode = stat_fun(path).st_mode
    except OSError:  # no such file or directory?
      continue
    if (stat.S_ISBLK(mode)  or
        stat.S_ISCHR(mode)  or
        stat.S_ISFIFO(mode) or
        stat.S_ISLNK(mode)  or
        stat.S_ISSOCK(mode)):
      yield Special(node)
      continue  # skip the rest
    elif stat.S_ISDIR(mode):
      raise Exception("Internal error (dir found as leaf): %r" % (node,))
    try:
      f = open(path, 'rb')
    except IOError as e:  # e. g. no read permissions
      yield Bad_Leaf(node + (e, None))
      continue
    yield File_Open(node + (f,))
    current_counter, end_counter, father_path, father_ancestry = ancestry
    ancestry2 = Ancestry((current_counter, end_counter, "", ancestry))
    while True:  # until EOF
      try:
        byte_count = f.readinto(tree_reader_buffer)
      except IOError as e:
        yield Bad_Leaf(node + (e, f))
        break  # ingore for now
      if byte_count == 0:  # EOF
        ancestry2.set_current_counter(current_counter)
        yield EOF((path, ancestry2, f))
        f.close()
        break
      current_counter += Counter((0, byte_count))
      ancestry2.set_current_counter(current_counter)
      yield Data((path, ancestry2, f, byte_count))

class TTY_Input(str):  pass

def interactive_tree_reader(tree, chunk_size=CHUNK_SIZE, follow_links=None):
  source = tree_reader(tree, chunk_size=chunk_size, follow_links=follow_links)
  current_file = None  # is the file while reading one
  tty = open('/dev/tty', 'r')
  while True:  # until the source is traversed
    if current_file is not None:
      r, w, e = select.select([ current_file, tty ], [], [])
      if tty in r:
        key = tty.read(1)
        if key == TTY.esc:  # read esc-sequence
          while True:
            char = tty.read(1)
            key += char
            if char.isalpha():
              break
        yield TTY_Input(key)
      if current_file in r:
        node = next(source)
        if   isinstance(node, Data):
          yield node
          # handle read buffer
        elif isinstance(node, EOF):
          yield node
          current_file = None
          # handle EOF (e. g. close output file)
        else:  # unexpected node
          yield node
          current_file = None
#          raise Exception("unexpected node type: %r (%r)" %
#                          (node.__class__, node))
    else:  # current_file is None:
      try:
        node = next(source)
      except StopIteration:
        break
      if   isinstance(node, File_Open):
        yield node
        path, ancestry, current_file = node
      elif isinstance(node, Special):
        yield node
      elif isinstance(node, Bad_Leaf):
        print('bad leaf: %r' % (node,))  # ignore bad leaves
        time.sleep(2)
      elif not isinstance(node, Leaf):  # directory?
        yield node
      else:
        raise Exception("unexpected node type: %r (%r)" %
                        (node.__class__, node))
  tty.close()

def copy_tree(tree, target, chunk_size=CHUNK_SIZE, follow_links=None,
              add_report=None):
  if follow_links is None:  follow_links = False
  stat_fun = os.stat if follow_links else os.lstat
  if add_report is None:  add_report = lambda report: None

  def preserve_stats(orig_stat, target):
    try:
      os.lchown(target, orig_stat.st_uid, orig_stat.st_gid)
    except OSError:  # Operation not permitted
      add_report("Could not chown %r to %d.%d" %
                 (target, orig_stat.st_uid, orig_stat.st_gid))
    try:
      os.chmod(target, orig_stat.st_mode)
    except OSError:  # Operation not permitted
      add_report("Could not chmod %r to %o" %
                 (target, orig_stat.st_mode))
    try:
      os.utime(target, (orig_stat.st_atime, orig_stat.st_mtime))
    except OSError:  # Operation not permitted
      add_report("Could not utime %r to %d/%d" %
                 (target, orig_stat.st_atime, orig_stat.st_mtime))

  message = [ "" ]
  time_of_last_message = [ 0.0 ]

  def set_message(new_message):
    message[0] = new_message
    time_of_last_message[0] = time.time()

  def get_message():
    if time_of_last_message[0] < time.time() - 5.0:
      return ""
    else:
      return message[0]

  delay = 0.0

  def set_delay_message(direction):
    if delay >= 1.0:
      set_message("delay %s to %.2fs" % (direction, delay))
    else:
      set_message("delay %s to %dms" % (direction, int(delay * 1000)))

  global tree_reader_buffer
  current_out_file = None
  ancestry = None
  stats_to_update_later = []
  for node in interactive_tree_reader(tree, chunk_size=chunk_size,
      follow_links=follow_links):
    if delay > 0.0:
      time.sleep(delay)
    if   isinstance(node, TTY_Input):  # input from user?
      command = node
      if   command == 'q':  # quit
        if current_out_file is not None:
          current_out_file.close()
        break
      elif command == ' ':  # pause
        sys.stdout.write(
          TTY.home + "Paused.  Press any key to continue ...\n")
        sys.stdin.read(1)
        set_message("continued")
      elif command == 'p':  # plot
        if ancestry is not None:
          ancestry.plot()
      elif command == 'd':  # increase delay
        if delay == 0.0:
          delay = 1.0 / 64
        else:
          delay *= 1.25
        set_delay_message("increased")
      elif command == 'D':  # decrease delay
        if delay <= 1.0 / 64:
          delay = 0.0
          set_message("delay disabled")
        else:
          delay /= 1.25
          set_delay_message("decreased")
      else:
        set_message("key not bound: %r" % command)
    elif isinstance(node, File_Open):  # next file?
      if current_out_file is not None:
        raise Exception("Internal error: File_Open while file is open")
      path, ancestry, f = node
      report(path, ancestry, get_message())
      file_name = target + '/' + path
      try:
        os.makedirs('/'.join(file_name.split('/')[:-1]))
      except OSError:  # File exists
        pass  # ignore
      try:
        os.lstat(file_name)
      except:  # as expected:  No such File
        temporary_file_name = file_name + '.part'
        try:
          current_out_file = open(temporary_file_name, 'wb')
        except IOError:  # cannot create file?
          add_report("Could not create file %r" % temporary_file_name)
          current_out_file = 'skip'
      else:  # oops, file exists?
        current_out_file = 'skip'
        # ^^^ we mark us to speed up things (do read, do not write)
    elif isinstance(node, Data):    # next chunk of data?
      if current_out_file is None:
        raise Exception("Internal error: Data without out-file")
      path, ancestry, f, byte_count = node
      report(path, ancestry, get_message())
      if current_out_file != 'skip':
        if byte_count != chunk_size:
          current_out_file.write(
            tree_reader_buffer.tobytes()[:byte_count])
        else:
          tree_reader_buffer.tofile(current_out_file)
    elif isinstance(node, EOF):     # end of current file?
      if current_out_file is None:
        raise Exception("Internal error: Data without out-file")
      path, ancestry, f = node
      report(path, ancestry, get_message())
      if current_out_file != 'skip':
        current_out_file.close()
        os.rename(temporary_file_name, file_name)
        preserve_stats(stat_fun(path), file_name)
      current_out_file = None
    elif isinstance(node, Special):   # device/link/fifo/socket?
      if current_out_file is not None:
        raise Exception("Internal error: Special encountered while writing"
                        " file: %r" % (node,))
      path, ancestry = node
      report(path, ancestry, get_message())
      file_name = target + '/' + path
      #try:
      #  os.makedirs('/'.join(file_name.split('/')[:-1]))
      #except OSError:  # File exists
      #  pass  # ignore
      mode = stat_fun(path).st_mode
      if   stat.S_ISLNK(mode):
        link_source = target + '/' + path
        link_target = os.readlink(path)
        try:
          os.symlink(link_target, link_source)
        except OSError:  # File exists?
          add_report("Could not create symlink to %r at %r" %
                     (link_target, link_source))
      else:
        add_report("UNIMPLEMENTED: Cannot handle special file yet: %r" %
                   (node,))
    elif isinstance(node, Bad_Leaf):  # error?
      add_report("Bad leaf: %r (%s)" % (node, target))
      if current_out_file is None:
        raise Exception("Internal error: Data without out-file")
      if current_out_file != 'skip':
        current_out_file.close()
      current_out_file = None
    elif not isinstance(node, Leaf):  # directory?
      path, ancestry = node
      if path != '':
        report(path, ancestry, get_message())
        dir_path = target + '/' + path
        try:
          os.makedirs(dir_path)
        except OSError:  # file exists?
          add_report("Could not make dir: %r" % dir_path)
        stats_to_update_later.append((stat_fun(path), dir_path))
    else:
      raise Exception("Internal error: unexpected node type: %r (%r)" %
                      (node.__class__, node))
  for status, path in reversed(stats_to_update_later):
    preserve_stats(status, path)

def read_tree(tree):
  message = [ "" ]
  time_of_last_message = [ 0.0 ]
  cursor_pos = 0

  def set_message(new_message):
    message[0] = new_message
    time_of_last_message[0] = time.time()

  def get_message():
    if time_of_last_message[0] < time.time() - 5.0:
      return ""
    else:
      return message[0]

  delay = 0.0

  def set_delay_message(direction):
    if delay >= 1.0:
      set_message("delay %s to %.2fs" % (direction, delay))
    else:
      set_message("delay %s to %dms" % (direction, int(delay * 1000)))

  ancestry = None
  for node in interactive_tree_reader(tree):
    if   isinstance(node, TTY_Input):  # input from user?
      command = node
      if   command == 'q':  # quit
        break
      elif command == ' ':  # pause
        sys.stdout.write(
          TTY.home + "Paused.  Press any key to continue ...\n")
        sys.stdin.read(1)
        set_message("continued")
      elif command == 'p':  # plot
        if ancestry is not None:
          ancestry.plot(depth=ancestry.get_depth() - 1 - cursor_pos)
      elif command == 'd':  # increase delay
        if delay == 0.0:
          delay = 1.0 / 64
        else:
          delay *= 1.25
        set_delay_message("increased")
      elif command == 'D':  # decrease delay
        if delay <= 1.0 / 64:
          delay = 0.0
          set_message("delay disabled")
        else:
          delay /= 1.25
          set_delay_message("decreased")
      elif command == TTY.down:
        if ancestry and cursor_pos + 1 < ancestry.get_depth():
          cursor_pos += 1
      elif command == TTY.up:
        if ancestry and cursor_pos > 0:
          cursor_pos -= 1
      else:
        set_message("key not bound: %r" % command)
    elif isinstance(node, Data):
      if   delay == 'step':
        if sys.stdin.readline() != '\n':
          print("delay = 10.0")
          print("Enter 'delay 0' to run.")
          time.sleep(2)
          delay = 10.0
      elif delay > 0.0:
        time.sleep(delay)
      path, ancestry, f, byte_count = node
      report(path, ancestry, get_message(), cursor_pos)

def main():
  if   sys.argv[1] == 'cp':
    del sys.argv[1]
    follow_links = False
    if sys.argv[1] == '-f':  # follow links?
      follow_links = True
      del sys.argv[1]
    reports = []

    def add_report(report):
      reports.append(report)

    tree = sizeof_path(sys.argv[1:-1], report_scan, follow_links,
                       target=sys.argv[-1], add_report=add_report)
    sys.stdout.write(
        TTY.cr + TTY.clearEOL + TTY.save + TTY.buffer1 + TTY.clear)
    sys.stdout.flush()
    try:
      copy_tree(tree,
                target=sys.argv[-1],
                follow_links=follow_links,
                add_report=add_report)
    finally:
      sys.stdout.write(TTY.clear + TTY.buffer0 + TTY.restore)
      sys.stdout.flush()
    for report in reports:
      print(report)
  elif sys.argv[1] == 'read':
    del sys.argv[1]
    tree = sizeof_path(sys.argv[1:], report_scan)
    sys.stdout.write(
        TTY.cr + TTY.clearEOL + TTY.save + TTY.buffer1 + TTY.clear)
    sys.stdout.flush()
    try:
      read_tree(tree)
    finally:
      sys.stdout.write(TTY.clear + TTY.buffer0 + TTY.restore)
      sys.stdout.flush()
  else:
    print("bad command:", sys.argv[1])
    sys.exit(1)

def prepare_tty():
  global stdin_fd
  stdin_fd = sys.stdin.fileno()  # will most likely be 0
  global old_stdin_config
  old_stdin_config = termios.tcgetattr(stdin_fd)
  [ iflag, oflag, cflag,
    lflag, ispeed, ospeed, cc ] = termios.tcgetattr(stdin_fd)
  cc[termios.VTIME] = 1
  cc[termios.VMIN]  = 1
  iflag = iflag & ~(
      termios.IGNBRK |
      termios.BRKINT |
      termios.PARMRK |
      termios.ISTRIP |
      termios.INLCR |
      termios.IGNCR |
      #termios.ICRNL |
      termios.IXON)
  cflag = cflag | termios.CS8
  lflag = lflag & ~(
      termios.ECHO |
      termios.ECHONL |
      termios.ICANON |
      #termios.ISIG |
      termios.IEXTEN)
  termios.tcsetattr(stdin_fd, termios.TCSANOW,
                    [ iflag, oflag, cflag, lflag, ispeed, ospeed, cc ])

def cleanup_tty():
  termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_stdin_config)

if __name__ == '__main__':
  prepare_tty()
  try:
    main()
  finally:
    cleanup_tty()
