#! /bin/bash
echo "args: $@"
mydir=`dirname $0`
fn="playGABC"
$mydir/parse_gabc.py "$@" > $fn.ly
lilypond $fn.ly
timidity $fn.midi
