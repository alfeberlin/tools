#!/bin/bash

usage="
usage: $0 [options] <filename>
options include:
    -s <start>
         Usage <start> as starting offset (defaults to 0)
"

start=0
ebcdic=false
while true
do
  case "$1" in
    -s)
      start=$2
      shift 2
      ;;
    -e)
      ebcdic=true
      shift
      ;;
    -*)
      echo "unknown option $1$usage" 1>&2
      exit 1
      ;;
    *)
      break
      ;;
  esac
done

filename=${1:?"missing <filename>$usage"}
filesize=$(stat -c %s "$filename")

incnibble=${incnibble:-1}  # which nibble to manipulate

keol=$(tput kel || printf '\x1b[K')
keos=$(tput ked || printf '\x1b[J')
rev=$(tput rev || printf '\x1b[7m')
norm=$(tput sgr0 || printf '\x1b[m')

clear
while true
do
  tput home
  txt=$(printf "%010x = %d = %dk = %dM = %dG = %.2f%%  %s" \
    $start $start $[start >> 10] $[start >> 20] $[start >>30] \
    "$(bc <<<"scale=3; $start * 100 / $filesize")" \
    "$($ebcdic && echo "EBCDIC" || echo "ASCII")")
  p=$[9-incnibble]
  display=$(
    xxd $($ebcdic && printf "%s" -E) $XXD_COLS -s $start "$filename" |
      head -$[$(tput lines) - 1]
  )
#  display=$(od -t x1 -j $start "$filename" | head -$[$(tput lines) - 1])
  printf "%s%s%s%s%s%s\n%s%s" \
    "${txt:0:$p}" "$rev" "${txt:$p:1}" "$norm" "${txt:$[p+1]}" "$keol" \
    "$display" "$keos"
  read -s -n 1 a
  if [ "$a" = $'\x1b' ]
  then
    seq=''
    sequenceComplete=false
    while true
    do
      if read -s -n 1 -t 0.01 c
      then
        if [ "$c" = $'\x1b' ]
        then
          sequenceComplete=true
        else
          $sequenceComplete || seq="$seq$c"
        fi
      else
        break
      fi
    done
    case "$seq" in
      "[A")  a=p;;
      "[B")  a=n;;
      "[C")  a=f;;
      "[D")  a=b;;
      "[5~") a=P;;
      "[6~") a=N;;
    esac
  fi
  case "$a" in
    q) echo; break;;
    p) start=$[start - (1 << (incnibble * 4))];;
    n) start=$[start + (1 << (incnibble * 4))];;
    P) start=$[start - (16 << (incnibble * 4))];;
    N) start=$[start + (16 << (incnibble * 4))];;
    b) incnibble=$[incnibble + 1];;
    f) incnibble=$[incnibble - 1];;
    e) ebcdic=$($ebcdic && echo false || echo true);;
    g) start=0;;
    G) start=$filesize;;
    /)
      tput home
      printf "/%s" "$keol"
      IFS='' read -r newSearchTerm
      if [ "$newSearchTerm" = "" ]
      then
        [ "$searchTerm" = "" ] && continue
      else
        searchTerm=$newSearchTerm
      fi
      tput home
      printf "searching for %q ...%s" "$searchTerm" "$keol"
      aborted=false
      trap '
        kill $(pstree -p $$ | grep tail | grep -o "[0-9]*")
        aborted=true
        trap SIGINT
      ' SIGINT
      IFS=: read -r offsetMinusOne occurrence < <(
        tail -c +$((start+2)) "$filename" |
          grep -a -o -b -i "$searchTerm" -m 1
      )
      echo "fatherout"
      trap SIGINT
      $aborted || start=$((start + offsetMinusOne + 1))
      ;;
  esac
  [ $start -lt 0 ] && start=0
  [ $incnibble -lt 0 ] && incnibble=0
  [ $incnibble -gt 9 ] && incnibble=9
done
