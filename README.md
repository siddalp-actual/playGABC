# playGABC
Convert Gregorio .gabc and \gabcsnippet{} in tex files into `Lilypond` format. 

The created .ly file contains processing statments so that .midi output will 
be produced, which can then be input to a tool such as `timidity` - see
`playGABC.sh` for trivial script to do this.

```
usage: parse_gabc.py [-h] [-d] [--snippet SNIPPET] [-t] filename

Parse parentheses from text file

positional arguments:
  filename           Filename to parse

options:
  -h, --help         show this help message and exit
  -d, --debug        turn on debugging
  --snippet SNIPPET  1..n the which snippet to find
  -t, --text         parse out and return just the text
```
