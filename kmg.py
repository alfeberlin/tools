#!/usr/bin/env python3

import sys
import re

def process_line(line):

  def group_thousands(number):
    reversed_groups = re.findall(r'\d{1,3}', number.group()[::-1])
    for i in range(len(reversed_groups)):
      reversed_groups[i] += ('\x1b[22m' if i % 2 == 0 else '\x1b[1m')[::-1]
    return ''.join(reversed_groups)[::-1]

  return re.sub(r'\d{5,}', group_thousands, line)

def process(stream):
  for line in stream:
    yield process_line(line)

def main(argv):
  for atom in process(sys.stdin):
    print(atom, end='')

if __name__ == '__main__':
  sys.exit(main(sys.argv))
