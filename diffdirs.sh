#!/bin/bash
#
# diffdirs.sh compares two directories
#

dir1=$1
dir2=$2

shift 2

if [ "$1" = "-f" ]
then
  format="$2\n"
  shift 2
else
  format="%p %s\n"
fi

diff "$@" <(cd "$dir1"; find . -type f -printf "$format" | sort) \
          <(cd "$dir2"; find . -type f -printf "$format" | sort)
