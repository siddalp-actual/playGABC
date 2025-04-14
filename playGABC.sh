#! /bin/bash
echo "args: $@"
thisdir=`pwd`
file_path=""
args=()
# Parse the arguments, looking for the file path.
while [ "$#" -gt 0 ]; do
  case "$1" in
    -* | --*) # If it starts with - or --, treat it as an option.
      args+=("$1")
      ;;
    *)       # Otherwise, assume it's the file path.
      if [ -z "$file_path" ]; then
        file_path="$1"
      else
        args+=("$1") # If file_path is already found, treat this as an argument.
      fi
      ;;
  esac
  shift
done

mydir=`dirname $0`
fn="playGABC"
pushd "/home/siddalp/github/playGABC"
./parse_gabc.py "${args[@]}" "$thisdir/$file_path" > $fn.ly
lilypond $fn.ly
timidity $fn.midi
popd
