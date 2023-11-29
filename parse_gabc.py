#! /bin/env python

"""
parse_gabc finds Gregorio GABC notation in .gabc or .tex
files and converts them into lilypond format.  The intent
is to be able to convert (using lilypond) into a midi file
so I can listen to the tune.

Usage:
  parse_gabc [ source.gabc | source.tex <--snippet=n> ]

  --snippet argument pulls out the nth gabcsnippet from a .tex file
  --debug   makes logging more verbose
"""

import argparse
import logging
import re


class GabcParser:
    """
    understands the GABC syntax, internalizing it into a sequential note
    representation

    so given a gabc clef of c4 (tonic on top line), we know the bottom line
    (D line in gabc) is the second note of the scale and we'll take the space
    just under as the tonic.  ie the C space.  ord('a') = 97
    so I need ord(gabc)-ord('a')+60

    we measure from the stave's bottom line (indicated by d in gabc notation)

    """

    logger = logging.getLogger("GabcParser")
    DOUBLE_DOT = re.compile(r"\.\.")
    DOUBLE_BAR = re.compile(r"::")
    CLEF_PATTERN = re.compile(r"([cf])([1-4])")
    REMOVAL_PATTTERNS = [
        DOUBLE_BAR,
        CLEF_PATTERN,
        re.compile(r"\[\d+\]"),  # eg [3] note spacing
        re.compile(r"\[.*?\]"),  # eg [ob:0;1mm] slur and [alt:stuff]
    ]

    def __init__(self):
        self.tonic_adjust = 0
        self.note_stream = []
        self.last_neume_len = 0
        # the semi_tones array may be modified on the fly by an accidental, but
        # currently only a flattening of the 7th is currently supported
        self.semi_tones = {
            0: 0,
            1: 2,
            2: 4,
            3: 5,
            4: 7,
            5: 9,
            6: 11,
        }

    def set_clef(self, clef):
        """
        set tonic_adjust according to the clef passed in.
        The clef can only be on line 1-4 and a c or f clef

        tonic_adjust is how many notes we need to add because the tonic is below the
        bottom of the stave.
        eg clef is f1, then the tonic must be 3 notes lower than the bottom line, 3 added
        c1 says the tonic is on the bottom line, nothing added
        c4 says the bottom line is 6 notes below the tonic

        """
        match_options = GabcParser.CLEF_PATTERN.match(clef.lower())
        if not match_options:
            raise ValueError
        line = int(match_options[2])
        self.tonic_adjust = ord(match_options[1]) - ord("c") - 2 * (line - 1)

    def parse_gabc(self, note_array):
        """
        note_array is a list of strings of gabc notation

        note_array[0] is the initial clef (there may be others)
        """
        GabcParser.logger.debug(f"{note_array}")
        self.set_clef(note_array[0])  # fixed by gabc format
        for i in range(1, len(note_array)):
            self.decode_gabc_string(note_array[i])

    def ornament_last_note(self, ornament_type):
        """
        for the moment we only handle quillisma (w)
        """
        self.note_stream[-1].ornament(ornament_type)

    def deal_with_syllable_level(self, g_str):
        """
        for the moment, the following items are assumed to occur only once
        per syllable
        """
        match_options = GabcParser.DOUBLE_BAR.match(g_str)  # double bar
        if match_options:
            self.maybe_lengthen_last_note()

        match_options = GabcParser.CLEF_PATTERN.match(g_str)
        if match_options:
            self.set_clef(g_str)

        match_options = re.search(r"[a-m]([xy])", g_str)  # this is an accidental
        if match_options:
            GabcParser.logger.debug(f"found accidental {match_options[0]}")
            self.set_accidental(match_options[1])
            g_str = re.sub(r"[a-m][xy]", "", g_str)

        for pattern in GabcParser.REMOVAL_PATTTERNS:
            g_str = re.sub(pattern, "", g_str)

        match_options = re.search(r"[a-l]+$", g_str)  # ends in multi-note neume?
        if match_options:
            self.last_neume_len = match_options.span()[1] - match_options.span()[0]

        return g_str

    def decode_gabc_string(self, g_str):
        """
        parse the notes for a single syllable
        """
        GabcParser.logger.info(f"decoding {g_str}")

        g_str = self.deal_with_syllable_level(g_str)

        prev_note = ""  # handle consecutive identical notes as lengthening
        dot_seen = False

        for ch in g_str.lower():
            GabcParser.logger.debug(f"Decode... found character {ch}")
            if "a" <= ch <= "m":
                if prev_note == ch:  # same note, treat like a tie
                    self.maybe_lengthen_last_note(duplicate_note=True)
                else:
                    self.note_stream.append(self.make_note(ch))
                    prev_note = ch

            elif ch == "w":
                self.ornament_last_note(ch)

            elif ch in {"v", "/", "!", "\n", "z"}:
                pass  # just ignore virga and spacing

            elif ch == ".":  # dotted note
                if dot_seen:  # double dotted => previous 2 notes extended
                    # and on second time, we'll get the n-1 note
                    num_notes = 2
                    dot_seen = False
                else:
                    # first time through this, we lengthen the last note
                    num_notes = 1
                    dot_seen = True

                self.maybe_lengthen_last_note(num_notes=num_notes)

            elif ch in {",", ";", ":"}:  # reached a bar
                self.undo_accidental()
                self.maybe_lengthen_last_note()
                self.last_neume_len = 0

            elif ch == "~":
                pass  # ignore liquescent for the mo

            else:
                GabcParser.logger.error(f"can't cope with :{ch}:")
                raise ValueError

    def maybe_lengthen_last_note(self, num_notes=1, duplicate_note=False):
        """
        a dot lengthens a note, as does the last note before a bar (division)
        some music combines both notations, in which case, only allow it to be
        doubled.
        if we're lengthening as a result of a bar line, then all notes in final neume get lengthened
        duplicate_note is for the case where multiple same notes are encountered in a
        syllable leading to >= 3* length
        """
        GabcParser.logger.debug(
            f"lengthen... called with args {num_notes=} {duplicate_note=} {self.last_neume_len=}"
        )
        if duplicate_note:  # like a tie, always increment
            self.note_stream[-1].increment_duration()
        else:
            for note_num in range(max(self.last_neume_len, num_notes)):
                if not self.note_stream[-1 - note_num].doubled:  # already doubled
                    self.note_stream[-1 - note_num].increment_duration()

    def set_accidental(self, on_off):
        """
        for the moment we always assume it's the seventh
        """
        assert on_off in {"x", "y"}
        if on_off == "x":  # a flat
            self.semi_tones[6] = 10
        else:
            self.undo_accidental()

    def undo_accidental(self):
        """
        undo the set_accidental action
        also used at bars
        """
        self.semi_tones[6] = 11

    def semitones(self, n: int):
        """
        convert a note number into a number of semitones above (or below)
        the tonic

        note that the self.semi_tones array is not constant as it can be
        altered by the presence of an accidental
        """
        assert isinstance(n, int)
        octave, interval = divmod(n, 7)
        return octave * 12 + self.semi_tones[interval]

    def make_note(self, letter):
        """
        find how many lines we are above the bottom of the stave, then
        add the tonidAdjust, built from the most recent clef
        """
        note_num = ord(letter) - ord("d")  # the bottom line of the stave
        note_num += self.tonic_adjust
        note_val = self.semitones(note_num)  # semitones relative to tonic
        return Note(note_val)

    def to_ly(self):
        """
        render the parsed snippet in lilypond format
        """
        print('\\version "2.22.2"')
        print('\\language "english"')
        print("\\score {")
        print("\\sequential {")
        for note in self.note_stream:
            print(f"{note.to_ly():s} ")
        print("}")
        print("}")
        print("\\score {")
        print("\\sequential {")
        for note in self.note_stream:
            print(f"{note.to_ly():s} ")
        print("}")
        print("\\midi { \\tempo 4 = 170 }")
        print("}")


class Note:
    """
    in midi notation, middle C is note 60 (=x3c)
    the internal representation will use 60 as the tonic

    """

    LY_DURATION = ["", "4", "2", "2.", "1"]

    logger = logging.getLogger("Note")

    def __init__(self, val: int):
        Note.logger.debug(f"__init__() created note {val}")
        self.val = val + 60
        self.duration = 1
        self.ornamentation = None
        self.doubled = False
        Note.logger.info(f"{self.to_ly()}")

    @staticmethod
    def ly_fmt(note_num, octave, duration):
        """
        just short hand for complex format string
        """
        return "{:s}{:s}{:s}".format(note_num, octave, duration)

    @staticmethod
    def ly_octave(octave):
        """
        shorthand for ly octave conversion
        """
        if octave > 4:
            octave_indicator = "'" * (octave - 4)
        if octave == 4:
            octave_indicator = ""
        if octave < 4:
            octave_indicator = "," * (4 - octave)
        return octave_indicator

    def to_ly(self):
        """
        render myself as a lilypond representation
        """
        note_array = {
            0: "c",
            1: "cs",
            2: "d",
            3: "ds",
            4: "e",
            5: "f",
            6: "fs",
            7: "g",
            8: "gs",
            9: "a",
            10: "bf",  # rather than as, usually result of accidental
            11: "b",
        }
        (octave, notenum) = divmod(self.val, 12)
        octave_indicator = Note.ly_octave(octave)

        if self.ornamentation is None:
            return self.ly_fmt(
                note_array[notenum], octave_indicator, Note.LY_DURATION[self.duration]
            )

        passing_duration = "8"
        main_frm = Note.ly_fmt(note_array[notenum], octave_indicator, passing_duration)
        passing_note_oct, passing_note_num = divmod(self.val - 2, 12)
        pn_frm = "{:s}{:s}{:s}".format(
            note_array[passing_note_num],
            Note.ly_octave(passing_note_oct),
            passing_duration,
        )
        return f"\\tuplet 3/2 {{ {main_frm} {pn_frm} {main_frm} }}"

    def increment_duration(self):
        """
        increment the duration, and also record that this has been done
        need to stop this happening twice when there is a dotted note just
        before a bar
        """
        self.duration += 1
        self.doubled = True

    def ornament(self, ornamentation_type):
        """
        mark the note with an ornamentation
        """
        self.ornamentation = ornamentation_type


PARENTHETICAL_TEXT = re.compile(r"\(([^)]+)\)")


def parse_parentheses(text):
    """
    extract the text found within parentheses
    """
    remaining_matches = PARENTHETICAL_TEXT.findall(text)

    if remaining_matches:
        results = remaining_matches
    else:
        print("no parenthesized groups found")
        raise ValueError

    return results


def remove_parens(text):
    """
    find everything that isn't between parentheses
    """
    the_rest = PARENTHETICAL_TEXT.sub("", text, count=0)  # replace all
    logger.info(the_rest)
    no_alt = re.sub(r"<alt>.*</alt>", "", the_rest, count=0)
    no_tags = re.sub(r"</?\w+>", "", no_alt, count=0)
    return no_tags


def find_gabc(file_name, snippet=1):
    """
    read the contents of the named file - for the moment just assume it's
    a .gabc or .tex file.

    .gabc: continue - assumes no parenthesized text other than in the lyrics
    .tex:  look for \\gabcsnippet{} tags and extract their content
    """
    with open(file_name, "r", encoding="utf-8") as text_file:
        text = text_file.read()

    if file_name.endswith(".tex"):
        # this RE uses minimal matching .*? to find the first closing brace
        # but doesn't cope with the tag itself containing braces eg {\ae}
        #   matches = re.findall(r"\\gabcsnippet{(.*?)}", text, flags=re.DOTALL)
        # NB DOTALL makes the . match a newline character too, so multi-line search
        # take 2
        # finds either a string without braces or the concatenation of no braces,
        # fully braced, no braces
        matches = re.findall(
            r"\\gabcsnippet{([^{}]+|[^{}]+{.*?}[^{}]+)}", text, flags=re.DOTALL
        )
        # NB the above is a halfway house - look for recursive re to find braces which uses
        # atomic group (?>...) available either in regex module or re post V3.11
        logger.info(f".tex file contains {len(matches)} snippets")
        if snippet <= len(matches):
            text = matches[snippet - 1]
        else:
            print(
                f"Error: option --snippet={snippet} is greater than number"
                " of snippets - {len(matches)}"
            )
            logger.info(matches)
            raise ValueError

        logger.info(text)

    return text


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse parentheses from text file")
    parser.add_argument("filename", help="Filename to parse")
    parser.add_argument("-d", "--debug", action="store_true", help="turn on debugging")
    parser.add_argument(
        "--snippet", action="store", default=1, help="1..n the which snippet to find"
    )
    parser.add_argument(
        "-t", "--text", action="store_true", help="parse out and return just the text"
    )
    args = parser.parse_args()

    filename = args.filename

    logger = logging.getLogger(__name__)

    LOGGER_LEVEL = logging.ERROR
    if args.debug:
        LOGGER_LEVEL = logging.DEBUG
    logging.basicConfig(force=True, level=LOGGER_LEVEL)

    txt = find_gabc(
        filename, snippet=int(args.snippet)
    )  # return content of gabc file or \gabcsnippet{}

    if args.text:
        print(remove_parens(txt))
    else:
        gabc_data = parse_parentheses(txt)

        logger.info(f"Found gabc data: {gabc_data}")
        gp = GabcParser()
        gp.parse_gabc(gabc_data)
        gp.to_ly()
