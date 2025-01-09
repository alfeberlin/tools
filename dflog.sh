#!/bin/bash
#
# Monitor df status of arbitrary mounts.
#
# Copy this file to /usr/bin/dflog and add this line to root's crontab:
# * * * * * DFLOG=/var/log/df /usr/bin/dflog cron / /media/foo
#
# This will log the df status of the mounts / and /media/foo in the
# files /var/log/df___.data and /var/los/df___media__foo.data .
# Display the graphs of the free space using
#
# $ dflog plot /var/log/df_*.data
#

: ${DFLOG:=$HOME/var/log/df}
: ${SLEEP:=60}

daemon() {
  while true
  do
    cron "$@"
    sleep "${SLEEP}"
  done
}

cron() {
  mkdir -p "$(dirname "$DFLOG")"
  now=$(date +%s)
  for dir
  do
    datafile=${DFLOG}_${dir//\//__}.data
    df "$dir" | {
      read headers
      read dev size used available percent mountpoint
      {
        read minus_2_line
        read last_line
      } < <(tail -2 "$datafile")
      read minus_2_time minus_2_size minus_2_used minus_2_available \
        minus_2_percent <<< "$minus_2_line"
      read last_time last_size last_used last_available last_percent \
        <<< "$last_line"
      if [ "$minus_2_size,$minus_2_used,$minus_2_available" = \
           "$last_size,$last_used,$last_available" ] && \
         [ "$last_size,$last_used,$last_available" = \
           "$size,$used,$available" ]
      then  # replace redundant line
        with_nl="${last_line}x"
        truncate -s -${#with_nl} "$datafile"
      fi
      printf "%-10d %12d %12d %12d %3d\n" \
        "$now" "$size" "$used" "$available" "${percent%%%}" >> "$datafile"
    }
  done >> "$DFLOG".log
}

plot() {
  gnuplot <<EOF
set xdata time
set timefmt "%s"
set format y "%.3fG"
set format x "%m-%d\n%H:%M"
plot 0 notitle
$(
  for dir in "$@"
  do
    echo "replot '$dir' using 1:(\$4/1000000) with lp title \"$dir\""
  done
)
while (1) { pause $SLEEP; replot; }
EOF
}

significant_change() {
  t1=$1
  s1=$2
  u1=$3
  a1=$4
  t2=$5
  s2=$6
  u2=$7
  a2=$8
  limit=$9
  [ "$t2" -gt $(( t1 + 3600 )) ] && return 0
  (( ds = (s1 - s2) ** 2 ))
  (( du = (u1 - u2) ** 2 ))
  (( da = (a1 - a2) ** 2 ))
  [ "$ds" -gt "$limit" ] ||
  [ "$du" -gt "$limit" ] ||
  [ "$da" -gt "$limit" ]
}

reduce() {
  limit=$(("$1" ** 2))
  old_time=0
  old_size=0
  old_used=0
  old_available=0
  old_percent=0
  cur_time=0
  cur_size=0
  cur_used=0
  cur_available=0
  cur_percent=0
  last_time=0
  while read new_time new_size new_used new_available new_percent
  do
    significant_change \
      "$old_time" "$old_size" "$old_used" "$old_available" \
      "$new_time" "$new_size" "$new_used" "$new_available" \
      "$limit" && {
      significant_change \
        "$cur_time" "$cur_size" "$cur_used" "$cur_available" \
        "$new_time" "$new_size" "$new_used" "$new_available" \
        "$limit" &&
        [ "$cur_time" != "$last_time" ] &&
        printf "%-10d %12d %12d %12d %3d\n" \
               "$cur_time" \
               "$cur_size" \
               "$cur_used" \
               "$cur_available" \
               "$cur_percent"
      printf "%-10d %12d %12d %12d %3d\n" \
             "$new_time" \
             "$new_size" \
             "$new_used" \
             "$new_available" \
             "$new_percent"
      last_time=$new_time
      old_time=$new_time
      old_size=$new_size
      old_used=$new_used
      old_available=$new_available
      old_percent=$new_percent
    }
    cur_time=$new_time
    cur_size=$new_size
    cur_used=$new_used
    cur_available=$new_available
    cur_percent=$new_percent
  done
}

case "$1" in
  plot)
    shift
    plot "$@"
    ;;
  daemon)
    shift
    daemon "$@"
    ;;
  cron)
    shift
    cron "$@"
    ;;
  reduce)
    shift
    reduce "$@"
    ;;
  *)
    (
      echo "not understood: $2"
      echo "usage: $0 plot <file ...>"
      echo "       $0 daemon <dir ...>"
      echo "       $0 cron <dir ...>"
      echo "       $0 reduce <dir ...>"
    ) 1>&2
    exit 1
    ;;
esac
