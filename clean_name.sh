#!/bin/bash
#
# clean_name.sh -- interprets $1 as a file name (complete path)
#                  and prints a version of that file name which does not
#                  contain any ugly characters (spaces, newlines ... etc).
#                  Only the base name is affected, the dir name stays
#                  untouched.
#                  can be used recursively for directory trees:
#                  find . -depth -exec clean_name -m {} \;

cleaned_name() {
    file=$1
    whole_path=$2
    dir=$(dirname "$file")
    "$whole_path" && [ "$dir" != "." ] && dir=$(cleaned_name "$dir" true)
    base=$(basename "$file")
    # replace all dots before the final dot by underscores:
    while true
    do
      oldbase=$base
      base=$(echo "$base" | sed -r -e 's/\.([^.]*\.)/_\1/g')
      [ "$oldbase" = "$base" ] && break
    done
    # replace all special characters:
    base=$(echo "$base" \
        | sed -r \
        -e 's/á/a/g'                        \
        -e 's/Á/A/g'                        \
        -e 's/à/a/g'                        \
        -e 's/À/A/g'                        \
        -e 's/ä/ae/g'                       \
        -e 's/Ä/AE/g'                       \
        -e 's/Ç/C/g'                        \
        -e 's/é/e/g'                        \
        -e 's/É/E/g'                        \
        -e 's/è/e/g'                        \
        -e 's/È/E/g'                        \
        -e 's/ë/e/g'                        \
        -e 's/Ë/E/g'                        \
        -e 's/í/i/g'                        \
        -e 's/Í/I/g'                        \
        -e 's/ì/i/g'                        \
        -e 's/Ì/I/g'                        \
        -e 's/ï/i/g'                        \
        -e 's/Ï/I/g'                        \
        -e 's/ğ/g/g'                        \
        -e 's/Ł/L/g'                        \
        -e 's/ó/o/g'                        \
        -e 's/Ó/O/g'                        \
        -e 's/ò/o/g'                        \
        -e 's/Ò/O/g'                        \
        -e 's/ö/oe/g'                       \
        -e 's/Ö/OE/g'                       \
        -e 's/ú/u/g'                        \
        -e 's/Ú/U/g'                        \
        -e 's/ù/u/g'                        \
        -e 's/Ù/U/g'                        \
        -e 's/ü/ue/g'                       \
        -e 's/Ü/UE/g'                       \
        -e 's/ß/ss/g'                       \
        -e 's/&/+/g'                        \
        -e 's/[^a-zA-Z0-9_.@#$%^&+=-]/_/g'  \
        -e 's/-_/__/g'                      \
        -e 's/_-/__/g'                      \
        -e 's/\._+/./g'                     \
        -e 's/_+\././g'                     \
        -e 's/_+$//'                        \
        -e 's/^_+//'                        \
        -e 's/___+/__/g'
    )

    if [ "$dir" = "." ]
    then
      echo "$base"
    else
      echo "$dir/$base"
    fi
}

move=false
verbose=false
whole_path=false
use_stdin=false
while true
do
    case "$1" in
      --help|-h)
        printf "usage: %s [options] name ...\n" "$0"
        printf "       Without options, clean version of the given names are"
        printf " given out.\n"
        printf "       Options:\n"
        printf "         -m    move the file of the given name to the clean"
        printf " name\n"
        printf "         -v    be verbose\n"
        printf "         -w    clean the whole path (not just the basename)\n"
        printf "         -h\n"
        printf "               or\n"
        printf "         --help   print this help\n"
        printf "         -     use stdin instead of command line agruments as input\n"
        exit 0
        ;;
      -m)
        move=true
        shift
        ;;
      -w)
        whole_path=true
        shift
        ;;
      -v)
        verbose=true
        shift
        ;;
      -)
        use_stdin=true
        shift
        ;;
      *)
        break
        ;;
    esac
done

process_file() {
    file=$1
    if $move
    then
        new=$(cleaned_name "$file" "$whole_path")
        if [ "$file" != "$new" ]
        then
            $verbose && printf "mv  %s\n--> %s\n" "$file" "$new"
            mv -i "$file" "$new"
        fi
    else
        cleaned_name "$file" "$whole_path"
    fi
}

if $use_stdin
then
    process_file "$(cat)"
else
    for file
    do
        process_file "$file"
    done
fi
