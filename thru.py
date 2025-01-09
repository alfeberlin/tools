#!/usr/bin/env python3
#
# thru.py limits the amount of data in a pipe.  use it like this:
#     cmd1 | thru | cmd2     or, of course:
#     cmd  | thru [> file]
#
#     it does not change the throughput.
#
#     thru reports the current bytes-per-second and the overall amount
#     to a fifo.
#     thru reads commands to set new current limits from another fifo.
#

usage = """
Usage: %s [options] [commands or name]

  If a command is given, the command is executed and then the process will
  terminate.  If no command is given, the process will enter passing mode,
  then all input on stdin will be passed to stdout using the specified
  buffer size and delay.  Reporting some throughput information is done
  regularly and can be read by another process (using command -w for
  instance).

  If a name is given for passing mode, then this name is used for this
  process (unless it already exists, then up to 20 ".x" suffixes are tried).
  If no name is given (or if all suffix versions failed), a random number
  is chosen as name.

  Options include:
    -q    be quiet about problems
    -u    use human readable display for sizes
    -v    be verbose about what is happening
    -d <delay>
        use given delay (in seconds) after each buffer is written
        (defaults to 0)
    -b <bufferSize>
        use given buffer size (defaults to 64k)
    -g <granularity>
        use given granularity (in seconds) for reporting (defaults to 1)

  Commands include:
    -h    print this help
    -l    list names of all running processes
    -w <name>
        watch given process; output is "name delay buffer amount rate"
        where <rate> is bytes per second in the period since the last
        report
    -W [<names>]
        watch the given processes (or all if none is given)
    -D <name> <delay>
        set the delay of the process with the given name remotely
        (see -d for details)
    -B <name> <bufferSize>
        set the buffer size of the process with the given name remotely
        (see -b for details)
    -G <name> <granularity>
        set the granularity of the process with the given name remotely
        (see -g for details)

  Examples:
    cat very_large_file | thru | uploader_script
    od < /dev/urandom | thru -b 1 -d 0.04
"""

import sys, select, os, array, random, atexit, time, json, re

import kmg

class Copier(object):

  class Drained(Exception): pass

  def __init__(self, fifoPath, options):
    self.startTime = time.time()
    self.fifoPath = fifoPath
    # default values
    self.bufferSize = options.bufferSize
    self.granularity = options.granularity
    self.delay = options.delay
    self.verbose = options.verbose
    self.quiet = options.quiet
    # initialization
    self.newBufferSize = None  # used for re-init during runtime
    self.writtenBytes = 0
    self.initBuffer()
    self.initFifos()
    self.nextOutputTime = 0.0

  def initBuffer(self):
    self.buffer = array.array('b')
    self.buffer.frombytes(b'-' * self.bufferSize)
    self.bufferByteCount = 0

  def initFifos(self):
    reportPath = os.path.join(self.fifoPath, 'report')
    dummy = os.open(reportPath, os.O_RDONLY | os.O_NONBLOCK)
    # ^^^ just to allow the open-to-write below
    self.reportFifo = os.open(reportPath, os.O_WRONLY)
    os.close(dummy)
    controlPath = os.path.join(self.fifoPath, 'control')
    self.controlFifo = os.open(controlPath, os.O_RDONLY | os.O_NONBLOCK)
    self.nextReportTime = 0.0

  def copy(self):
    while True:  # until Drained
      channels = self.selectChannels()
      if self.controlFifo in channels:
        self.handleCommand(self.readCommand())
      if self.reportFifo in channels:
        self.report()
      if self.bufferByteCount > 0:
        if (sys.stdout in channels and
          time.time() >= self.nextOutputTime):
          self.nextOutputTime = time.time() + self.delay
          self.writeBuffer()
      if self.bufferByteCount < self.bufferSize:
        if sys.stdin in channels:
          try:
            self.readBuffer()
          except self.Drained:
            break
      waitDuration = (min(self.nextOutputTime, self.nextReportTime) -
          time.time())
      if waitDuration > 0:
        time.sleep(waitDuration)

  def selectChannels(self):
    r = [ self.controlFifo ]
    if self.bufferByteCount < self.bufferSize:  # buffer not yet full?
      r.append(sys.stdin)
    outputDelayed = self.nextOutputTime > time.time()
    reportDelayed = self.nextReportTime > time.time()
    w = []
    if not outputDelayed and self.bufferByteCount > 0:
      w.append(sys.stdout)
    if not reportDelayed:
      w.append(self.reportFifo)
    times = []
    if outputDelayed: times.append(self.nextOutputTime)
    if reportDelayed: times.append(self.nextReportTime)
    try:
      waitDuration = max(min(times) - time.time(), 0)
    except ValueError:  # no times?
      waitDuration = None  # never time out
    if self.verbose:
      print("# select:", r, w, waitDuration, "...", end=' ',
            file=sys.stderr, flush=True)
    try:
      r, w, e = select.select(r, w, [], waitDuration)
    except Exception as e:
      print("# problem with select:", r, w, waitDuration,
            file=sys.stderr)
      raise
    if self.verbose:
      print(r, w, e, file=sys.stderr)
    return r + w

  def handleCommand(self, command):
    if not command:  # ignore empty strings
      return
    try:
      command = json.loads(command)
      if command[0] == 'delay':
        self.delay = command[1]
        self.nextOutputTime = time.time() + self.delay
      elif command[0] == 'bufferSize':
        self.newBufferSize = command[1]
      elif command[0] == 'granularity':
        self.granularity = command[1]
      else:
        if not self.quiet:
          print("unimplemented command: %r" % command,
                file=sys.stderr)
    except Exception as problem:
      if not self.quiet:
        print("handleCommand:", problem, repr(command),
              file=sys.stderr)

  def readCommand(self):
    result = os.read(self.controlFifo, 1000)
    os.close(self.controlFifo)
    controlPath = os.path.join(self.fifoPath, 'control')
    self.controlFifo = os.open(controlPath, os.O_RDONLY | os.O_NONBLOCK)
    return result

  def writeBuffer(self):
    written = 0
    while written < self.bufferByteCount:
      if self.bufferByteCount != self.bufferSize or written > 0:
        written += os.write(sys.stdout.fileno(),
          self.buffer.tobytes()[written:self.bufferByteCount])
      else:
        self.buffer.tofile(sys.stdout.buffer)
        written += len(self.buffer)
    sys.stdout.flush()
    self.writtenBytes += self.bufferByteCount
    self.bufferByteCount = 0
    if self.newBufferSize is not None:
      self.bufferSize = self.newBufferSize
      self.newBufferSize = None
      self.initBuffer()

  def buildReport(self):
    return json.dumps([
      self.startTime, self.writtenBytes, self.bufferSize, self.delay ])

  def report(self):
    self.nextReportTime = time.time() + self.granularity
    try:
      os.write(self.reportFifo, (self.buildReport() + '\n').encode('utf-8'))
    except OSError as problem:
      pass
      #if problem.errno != os.errno.EPIPE:
      #  raise

  def readBuffer(self):
    chunk = os.read(
      sys.stdin.fileno(), self.bufferSize - self.bufferByteCount)
    self.buffer[self.bufferByteCount:self.bufferByteCount + len(chunk)] = \
      array.array('b', chunk)
    self.bufferByteCount += len(chunk)
    if self.bufferByteCount == 0:
      raise self.Drained()

homeDir = '/run/shm/thru'

def getFifoPath(name):
  fifoPath = os.path.join(homeDir, name)
  try:
    os.makedirs(fifoPath)
  except OSError as problem:
    if problem.errno == os.errno.EEXIST:
      raise NameInUse(name)
    else:
      raise
  os.mkfifo(os.path.join(fifoPath, 'report'))
  os.mkfifo(os.path.join(fifoPath, 'control'))

  def cleanup(fifoPath=fifoPath):
    os.unlink(os.path.join(fifoPath, 'report'))
    os.unlink(os.path.join(fifoPath, 'control'))
    os.rmdir(fifoPath)

  atexit.register(cleanup)
  return fifoPath

class NameInUse(Exception): pass

def lineByLine(openFile):
  while True:
    line = openFile.readline()
    if not line:
      break
    yield line

def reportOn(name):
  with open(os.path.join(homeDir, name, 'report')) as reportFile:
    lastReportTime = None
    lastPos = None
    for line in lineByLine(reportFile):
      thruStartTime, pos, bufferSize, delay = json.loads(line)
      durationSinceLast = (None if lastReportTime is None
          else time.time() - lastReportTime)
      progressSinceLast = (None if lastPos is None
          else pos - lastPos)
      lastReportTime = time.time()
      lastPos = pos
      yield (thruStartTime, durationSinceLast, progressSinceLast,
          pos, bufferSize, delay)

def reportOnMany(names):
  if names:
    reportFiles = { name: open(os.path.join(homeDir, name, 'report'))
                    for name in names }
  else:
    reportFiles = { name: open(os.path.join(homeDir, name, 'report'))
                    for name in os.listdir(homeDir) }
  file2name = { f: name for name, f in reportFiles.items() }
  try:
    lastReportTimes = {}
    lastPoses = {}
    thruStartTimes = {}
    poses = {}
    bufferSizes = {}
    delays = {}
    durationSinceLasts = {}
    progressSinceLasts = {}
    while not names or reportFiles:
      r, w, e = select.select(reportFiles.values(), [], [], 1.0)
      for f in r:
        name = file2name[f]
        line = f.readline()
        if not line:
          del file2name[f]
          del reportFiles[name]
          f.close()
        else:
          thruStartTimes[name], poses[name], bufferSizes[name], \
              delays[name] = json.loads(line)
          durationSinceLasts[name] = (None if name not in lastReportTimes
              else time.time() - lastReportTimes[name])
          progressSinceLasts[name] = (None if name not in lastPoses
              else poses[name] - lastPoses[name])
          lastReportTimes[name] = time.time()
          lastPoses[name] = poses[name]
        yield (thruStartTimes, durationSinceLasts,
            progressSinceLasts, poses, bufferSizes,
            delays, reportFiles.keys(), name)
      for name in os.listdir(homeDir):
        if name not in reportFiles:
          f = open(os.path.join(homeDir, name, 'report'))
          reportFiles[name] = f
          file2name[f] = name
  finally:
    for f in reportFiles.values():
      f.close()

def sendCommand(name, command):
  with open(os.path.join(homeDir, name, 'control'), 'wa') as control:
    data = json.dumps(command)
    control.write(data)

def setDelay(name, delay):
  sendCommand(name, [ 'delay', delay ])

def setBufferSize(name, bufferSize):
  sendCommand(name, [ 'bufferSize', bufferSize ])

def setGranularity(name, granularity):
  sendCommand(name, [ 'granularity', granularity ])

class Options(object):
  quiet = False
  verbose = False
  granularity = 1.0
  delay = 0.0
  bufferSize = 1<<16  # 64k
  humanReadable = False

def int2kmgt(i):
  return ''.join(''.join(x)
    for x in reversed(zip(reversed(
      [ x[0] for x in re.findall(r'(\d{1,3})(?=(\d{3})*$)', str(i)) ]
    ), ' kMGT')))[:-1]

def parseArgv(argv):
  options = Options()
  while len(argv) > 1:
    if argv[1] == '-h':  # print usage
      print(usage % argv[0])
      sys.exit(0)
    elif argv[1] == '-u':  # human readable
      options.humanReadable = True
      del argv[1]
    elif argv[1] == '-q':  # suppress error messages
      options.quiet = True
      del argv[1]
    elif argv[1] == '-v':  # be verbose
      options.verbose = True
      del argv[1]
    elif argv[1] == '-d':  # set delay
      options.delay = float(argv[2])
      del argv[1:3]
    elif argv[1] == '-b':  # set delay
      options.bufferSize = int(argv[2])
      del argv[1:3]
    elif argv[1] == '-g':  # set granularity
      options.granularity = float(argv[2])
      del argv[1:3]
    elif argv[1] == '-l':  # list all running thrus
      for name in os.listdir(homeDir):
        if os.path.isdir(os.path.join(homeDir, name)):
          print(name)
      return None
    elif argv[1] == '-w':  # watch info about given running thru
      size = int2kmgt if options.humanReadable else int
      name = argv[2]
      suffix = '\r' if os.isatty(1) else '\n'
      # ^^^ we want all output in one line if this is a tty
      for (thruStartTime, durationSinceLast, progressSinceLast,
        pos, bufferSize, delay) in reportOn(name):
        print(name, delay, size(bufferSize), size(pos),
              (size(int(progressSinceLast/durationSinceLast))
               if durationSinceLast else "./."), suffix, end=' ',
              flush=True)
      return None
    elif argv[1] == '-W':  # watch info about several given running thrus
      size = int2kmgt if options.humanReadable else int
      names = argv[2:]
      init = '\x1b[H\x1b[2J' if os.isatty(1) else '----\n'
      # ^^^ we want to clear the screen for each chunk if this is a tty
      collected = []
      for (thruStartTimes, durationSinceLasts, progressSinceLasts, poses,
          bufferSizes, delays, actives, name) in reportOnMany(names):
        for active in actives:
          if active not in collected:
            collected.append(active)
        def argsForOutput(name):
          try:
            return (
                ' ' if name in actives else 'X',
                name,
                delays[name],
                size(bufferSizes[name]),
                size(poses[name]),
                size(int(progressSinceLasts[name]/durationSinceLasts[name]))
                    if durationSinceLasts[name] else "./.")
          except KeyError:
            return ('?', name, '', '', '', '')
        print(init + kmg.process_line(
            '\n'.join('%s %-8s:\t%s %10s %16s %12s' % argsForOutput(name)
                      for name in (names or collected))))
      return None
    elif argv[1] == '-D':  # set a delay remotely
      name = argv[2]
      delay = float(argv[3])
      setDelay(name, delay)
      return None
    elif argv[1] == '-B':  # set buffer size remotely
      name = argv[2]
      bufferSize = int(argv[3])
      setBufferSize(name, bufferSize)
      return None
    elif argv[1] == '-G':  # set granularity remotely
      name = argv[2]
      granularity = float(argv[3])
      setGranularity(name, granularity)
      return None
    else:
      break
  if len(argv) > 1:
    name = argv[1]
    for i in range(20):
      try:
        return getFifoPath(name + '.x' * i), options
      except NameInUse:
        pass
  # find a random name
  while True:  # until unused name found
    name = str(random.randint(1000, 9999))
    try:
      return getFifoPath(name), options
    except NameInUse:
      pass

if __name__ == '__main__':
  action = parseArgv(sys.argv)
  if action:
    fifoPath, options = action
    copier = Copier(fifoPath, options)
    copier.copy()
