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
        re.compile(r"\[.*\]"),  # eg [ob:0;1mm] slur and [alt:stuff]
    ]

    # matches a neume (letters) or a terminating dot, set up to return
    # length of either
    LAST_NEUME_PATTERN = re.compile(r"(?i:[a-l]+)$|\.$")  # ?i: => qignore case

    def __init__(self):
        self.note_stream = []
        self.last_neume_len = 0
        self.scale = None

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
        match_obj = GabcParser.CLEF_PATTERN.match(clef.lower())
        if not match_obj:
            raise ValueError
        line = int(match_obj[2])
        # self.tonic_adjust = ord(match_options[1]) - ord("c") - 2 * (line - 1)
        self.scale = Scale(tonic=ord(match_obj[1]) - ord("c") - 2 * (line - 1))

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
        match_obj = GabcParser.DOUBLE_BAR.match(g_str)  # double bar
        if match_obj:
            self.logger.debug("double bar seen")
            self.maybe_lengthen_last_note(num_notes=0)  # driven by neume length

        match_obj = GabcParser.CLEF_PATTERN.match(g_str)
        if match_obj:
            self.logger.debug("clef seen")
            self.set_clef(g_str)

        match_obj = re.search(r"[a-m]([xy])", g_str)  # this is an accidental
        if match_obj:
            GabcParser.logger.debug(f"found accidental {match_obj[0]}")
            self.set_accidental(match_obj[1])
            g_str = re.sub(r"[a-m][xy]", "", g_str)

        for pattern in GabcParser.REMOVAL_PATTTERNS:
            g_str = re.sub(pattern, "", g_str)

        # does it end in multi-note neume?
        match_obj = GabcParser.LAST_NEUME_PATTERN.search(g_str)
        if match_obj:
            self.logger.debug(
                f"last neume {match_obj.string[match_obj.start():match_obj.end()]}"\
                f" length={match_obj.span()[1]-match_obj.span()[0]}"
            )
            self.last_neume_len = match_obj.span()[1] - match_obj.span()[0]

        return g_str

    def decode_gabc_string(self, g_str):
        """
        parse the notes for a single syllable
        """
        GabcParser.logger.info(f"decoding {g_str}")

        g_str = self.deal_with_syllable_level(g_str)

        GabcParser.logger.info(f"after syllable level {g_str} {self.last_neume_len=}")

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

            elif ch in {"v", "@", "/", "!", "\n", "z"}:
                # v adds virga, @ suppresseses one
                # / ! cause spacing to tweak the notes
                # used in a neume
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

            elif ch == "r":  # hollow note
                self.shorten_last_note()

            elif ch in {",", ";", ":"}:  # reached a bar
                self.scale.undo_accidental()
                self.maybe_lengthen_last_note(num_notes=0)  # driven by last neume
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
            if num_notes == 0:  # a bar, use neume length
                num_notes = self.last_neume_len
            for note_num in range(num_notes):
                if not self.note_stream[-1 - note_num].doubled:  # already doubled
                    self.note_stream[-1 - note_num].increment_duration()

    def shorten_last_note(self):
        """
        a hollow punctum is considered to be half normal
        duration.
        """
        self.note_stream[-1].halve_duration()

    def set_accidental(self, on_off):
        """
        for the moment we always assume it's the seventh
        """
        assert on_off in {"x", "y"}
        if on_off == "x":  # a flat
            self.scale.set_accidental("on")
        else:
            self.scale.set_accidental("off")

    def make_note(self, letter):
        """
        find how many lines we are above the bottom of the stave, then
        add the tonidAdjust, built from the most recent clef
        """
        note_num = ord(letter) - ord("d")  # the bottom line of the stave
        return self.scale.make_note(note_num)

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


class Scale:
    """
    affected by accidentals and the key-signature this is used
    to map a note position on a stave to a pitch, or more properly,
    a midi-note number
    """

    def __init__(self, tonic=0):
        """
        create a new scale object
        """
        self.tonic_adjust = tonic
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

    def make_note(self, stave_pos: int):
        """
        find how many lines we are above the bottom of the stave, then
        add the tonidAdjust, built from the most recent clef
        """
        stave_pos += self.tonic_adjust
        note_val = self.semitones(stave_pos)  # semitones relative to tonic
        return Note(note_val, self)

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

    def lower_note(self, value_in_semitones):
        """
        given a value in semitones within the scale,
        find the next lower note, (this may be one or two semitones
        lower depending on where value_in_semitones lies)
        and return a Note representing it
        """
        octave, interval = divmod(value_in_semitones, 12)
        pos = self.get_scale_pos(interval)  # pos in range [0:6]
        if pos == 0:
            pos = 6
            octave -= 1
        else:
            pos -= 1
        return Note(12 * octave + self.semitones(pos), self)

    def get_scale_pos(self, intvl):
        """
        reverse lookup the value to find the corresponding key of the semi_tones array
        """
        for note, semis in self.semi_tones.items():
            if semis == intvl:
                return note
        logger.error(f"get_scale_pos: {intvl=} not found")
        raise ValueError

    def set_accidental(self, on_off):
        """
        for the moment we always assume it's the seventh
        """
        assert on_off in {"on", "off"}
        if on_off == "on":  # a flat
            self.semi_tones[6] = 10
        else:
            self.undo_accidental()

    def undo_accidental(self):
        """
        undo the set_accidental action
        also used at bars
        """
        self.semi_tones[6] = 11


class Note:
    """
    in midi notation, middle C is note 60 (=x3c)
    the internal representation will use 60 as the tonic

    """

    LY_DURATION = ["", "8", "4", "4.", "2", "2.", "1"]
    NORMAL_DURATION = 2
    MIDI_PITCH_OFFSET = 60

    logger = logging.getLogger("Note")

    def __init__(self, val: int, scale: Scale):
        Note.logger.debug(f"__init__() created note {val}")
        self.val = val + Note.MIDI_PITCH_OFFSET
        self.scale = scale
        self.duration = self.NORMAL_DURATION
        self.ornamentation = None
        self.doubled = False
        Note.logger.info(f"{self.to_ly()}")

    def get_note_lower(self):
        """
        Need to use the current scale, to work out what the next lower note
        would be
        """
        val = self.val - Note.MIDI_PITCH_OFFSET
        return self.scale.lower_note(val)

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
        passing_note = self.get_note_lower()
        passing_note_oct, passing_note_num = divmod(passing_note.val, 12)
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
        self.duration += self.NORMAL_DURATION
        self.doubled = True

    def halve_duration(self):
        """
        make this note length that of half a punctum
        """
        self.duration = 1

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
