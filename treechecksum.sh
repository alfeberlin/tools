#!/bin/bash

fileChecksum() {
  (
    head -c 100000 "$1"
    tail -c 100000 "$1"
    wc -c < "$1"
  ) | md5sum | cut -d' ' -f 1
}

dirChecksum() {
  if [ -h "$1" ]
  then
    return  # ignore symlinks
  elif [ -f "$1" ]
  then
    checksum=$(fileChecksum "$1")
  elif [ -d "$1" ]
  then
    checksum=$(
      shopt -s dotglob
      shopt -s nullglob
      for f in "$1"/*
      do
        dirChecksum "$f"
      done | sort | md5sum | cut -d' ' -f 1
    )
  fi
  echo "$checksum"
  echo "$checksum $1" 1>&3
}

case "$1" in
  -d)
    list=$(dirChecksum "$1" 3>&1 1>/dev/null)
    lastChecksum=''
    while read checksum path
    do
      if [ "$checksum" = "$lastChecksum" ]
      then
        echo "duplicate found: $path = $lastPath"
      fi
      lastChecksum=$checksum
      lastPath=$path
    done < <(sort <<< "$list")
    ;;
  -t)
    shift
    for i
    do
      dirChecksum "$i" 3>&1 1>/dev/null
    done
    ;;
  *)
    echo "Option $1 not understood; use -d or -t."
    ;;
esac
