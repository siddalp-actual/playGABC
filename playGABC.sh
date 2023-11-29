#! /bin/bash
echo "args: $@"
./parse_gabc.py "$@" > try.ly
lilypond try.ly
timidity try.midi
