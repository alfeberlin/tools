#!/usr/bin/env python3

import time, os

from collections import defaultdict

class NoSuchProcess(Exception):
  pass
def getFds(pid):
  try:
    return os.listdir('/proc/%s/fd/' % pid)
  except FileNotFoundError as e:
    raise NoSuchProcess(pid) from e

def getPos(pid, fd):
  with open('/proc/%s/fdinfo/%s' % (pid, fd)) as f:
    return int(f.readline()[5:])

def getSize(pid, fd):
  path = getPath(pid, fd)
  try:
    result = os.path.getsize(path)
  except FileNotFoundError:
    return 0
  if result == 0 and not os.path.isfile(path):  # maybe block device?
    fd = os.open(path, os.O_RDONLY)
    try:
      result = os.lseek(fd, 0, os.SEEK_END)
    except OSError:  # seeking impossible
      result = 0
    finally:
      os.close(fd)
  return result

class FdIsPipe(Exception): pass

def getPath(pid, fd):
  result = os.readlink('/proc/%s/fd/%s' % (pid, fd))
  if result.startswith('pipe:['):
    raise FdIsPipe(result)
  return result

def extendHistory(history, pid):
  for fd in getFds(pid):
    try:
      history[fd, getPath(pid, fd)].append(
        (time.time(), getPos(pid, fd), getSize(pid, fd)))
    except FdIsPipe:
      pass  # ignore fds to pipe

def initHistory(pid):
  result = defaultdict(list)
  extendHistory(result, pid)
  return result

def reduceHistory(history):
  for key, value in history.items():
    if len(value) > 15:
      # only keep first, last-but-tenth, and last
      del value[1:-10]
      del value[2:-1]

def entryPrediction(fd, path, values):
  t1, pos1, size1 = values[-5:][0]
  t2, pos2, size2 = values[-1]
  if t1 == t2:  # no time passed yet?
    return fd, path, (t2, pos2, size2), None, None, None, None, None, None, None
  growth = (size2 - size1) / (t2 - t1)  # bytes/sec growth of file
  if growth != 0:
    tSize0 = t1 - size1 / growth  # time when size was 0
  else:
    tSize0 = None
  speed = (pos2 - pos1) / (t2 - t1)  # speed of pos in bytes/sec
  if speed != 0:
    tPos0 = t1 - pos1 / speed  # time when pos was 0
    tPosSize2 = t1 + (size2 - pos1) / speed  # time of pos reaching size2
  else:
    tPos0 = tPosSize2 = None
  if speed != growth:  # when will both meet?
    tm = t2 + (size2 - pos2) / (speed - growth)
    sizeM = size2 + growth * (tm - t2)
  else:
    tm = sizeM = None
  return (fd, path, (t2, pos2, size2), growth, speed, tSize0, tPos0,
          tPosSize2, tm, sizeM)

def eachPrediction(history):
  for (fd, path), values in history.items():
    yield entryPrediction(fd, path, values)

def displayTime(t):
  if t is None:
    return "n/a"
  d = t - time.time()
  try:
    lt = time.localtime(t)
  except:
    return "??"
  return (
    time.strftime("%%F (now%+dy)" % (d/86400/365), lt)
    if abs(d) > 2 * 86400 * 365 else
    time.strftime("%%F (now%+dM)" % (d/86400/30), lt)
    if abs(d) > 2 * 86400 * 30 else
    time.strftime("%%F (now%+dd)" % (d/86400), lt)
    if abs(d) > 2 * 86400 else
    time.strftime("%%a, %%T (now%+dh)" % (d/3600), lt)
    if time.strftime('%F', lt) != time.strftime('%F', time.localtime()) else
    time.strftime("%%T (now%+dh)" % (d/3600), lt)
    if abs(d) > 2 * 3600 else
    time.strftime("%%T (now%+dm)" % (d/60), lt)
    if abs(d) > 2 * 60 else
    time.strftime("%%T (now%+ds)" % d, lt))

def displaySize(size):
  return (
    "n/a" if size is None else
    "%d B" % size
    if size < 1e3 else
    "%.2f kB" % (size / 1e3)
    if size < 1e6 else
    "%.2f MB" % (size / 1e6)
    if size < 1e9 else
    "%.2f GB" % (size / 1e9))

def displaySpeed(speed):
  return displaySize(speed) + "/s"

def printPrediction(history):
  for (fd, path, (t2, pos2, size2), growth, speed, tSize0, tPos0,
       tPosSize2, tm, sizeM) in eachPrediction(history):
    if not growth and not speed:  # not interesting?
      continue
    print("===", fd, "->", os.path.basename(path))
    if pos2 < size2 * 0.99:  # position not at end of file:
      print(displaySize(pos2) + "/" + displaySize(size2) +
            " (%.1f%%)" % (pos2*100.0/size2),
            ("(growing: " + displaySpeed(growth) + ")" if growth else ''),
            "(reading: " + displaySpeed(speed) + ")")
      print("T₀:", displayTime(tSize0) if growth else displayTime(tPos0),
            "Tₑ:", displayTime(tPosSize2),
            ("Tₘ: " + displayTime(tm) if growth else ''))
    else:  # just growing
      print(displaySize(size2),
            ("(growing: " + displaySpeed(growth) + ")" if growth else ''))
      print("T₀: " + displayTime(tSize0))

def watchPrediction(pid, delay):
  history = initHistory(pid)
  while True:
    os.system('clear')
    printPrediction(history)
    try:
      extendHistory(history, pid)
    except NoSuchProcess:  # process terminated?
      return 0
    reduceHistory(history)
    time.sleep(delay)

def main(argv):
  watchPrediction(argv[1], float(os.getenv('FDPROGRESS_DELAY', '1')))

if __name__ == '__main__':
  import sys
  sys.exit(main(sys.argv))
