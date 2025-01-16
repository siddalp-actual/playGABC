#! /bin/bash
echo "args: $@"
thisdir=`pwd`
mydir=`dirname $0`
fn="playGABC"
pushd "/home/siddalp/github/playGABC"
./parse_gabc.py "$thisdir/$1" > $fn.ly
lilypond $fn.ly
timidity $fn.midi
popd
