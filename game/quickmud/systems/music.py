"""music.c: the songs (music.txt), the jukeboxes and the global music channel (#74, P4 PR 5).

song_table and channel_songs are the Game's songs and channel_songs. channel_songs[0] is the line the global song
is at (-1 before its title), and channel_songs[1..MAX_GLOBAL] the queue, the playing song first. A jukebox keeps
the same in its values: value[0] the line, value[1..4] the queue.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/music.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quickmud.data import constants as C
from quickmud.net.act import act, act_new
from quickmud.net.output import send_to_char

MAX_SONGS, MAX_LINES, MAX_GLOBAL = 20, 100, 10  # music.h


@dataclass(eq=False)
class Song:
    """song_data. A row load_songs didn't fill has no name (NULL), no lines and no lyrics."""

    group: str | None = None
    name: str | None = None
    lyrics: list = field(default_factory=lambda: [None] * MAX_LINES)
    lines: int = 0


def new_song_table() -> list[Song]:
    return [Song() for _ in range(MAX_SONGS)]


def _text(s: str | None) -> str:
    """A string for %s, as glibc prints a NULL one."""
    return "(null)" if s is None else s


# C: music.c song_update
def song_update(game) -> None:
    songs, channel = game.songs, game.channel_songs

    # "do the global song, if any"
    if channel[1] >= MAX_SONGS:
        channel[1] = -1
    if channel[1] > -1:
        if channel[0] >= MAX_LINES or channel[0] >= songs[channel[1]].lines:
            channel[0] = -1
            for i in range(1, MAX_GLOBAL):  # "advance songs"
                channel[i] = channel[i + 1]
            channel[MAX_GLOBAL] = -1
        else:
            song = songs[channel[1]]
            if channel[0] < 0:
                buf = "Music: %s, %s" % (_text(song.group), _text(song.name))
                channel[0] = 0
            else:
                buf = "Music: '%s'" % _text(song.lyrics[channel[0]])
                channel[0] += 1
            for d in list(game.descriptor_list):
                victim = d.original if d.original is not None else d.character
                if (d.connected == C.CON_PLAYING and not victim.comm & C.COMM_NOMUSIC
                        and not victim.comm & C.COMM_QUIET):
                    act_new("$t", d.character, buf, None, C.TO_CHAR, C.POS_SLEEPING)

    for obj in list(game.object_list):
        if obj.item_type != C.ITEM_JUKEBOX or obj.value[1] < 0:
            continue
        if obj.value[1] >= MAX_SONGS:
            obj.value[1] = -1
            continue

        # "find which room to play in"
        room = obj.in_room
        if room is None:
            if obj.carried_by is None:
                continue
            room = obj.carried_by.in_room
            if room is None:
                continue

        song = songs[obj.value[1]]
        if obj.value[0] < 0:
            buf = "$p starts playing %s, %s." % (_text(song.group), _text(song.name))
            if room.people:
                act(buf, room.people[0], obj, None, C.TO_ALL)
            obj.value[0] = 0
            continue
        if obj.value[0] >= MAX_LINES or obj.value[0] >= song.lines:
            obj.value[0] = -1
            # "scroll songs forward"
            obj.value[1] = obj.value[2]
            obj.value[2] = obj.value[3]
            obj.value[3] = obj.value[4]
            obj.value[4] = -1
            continue
        line = song.lyrics[obj.value[0]]
        obj.value[0] += 1
        buf = "$p bops: '%s'" % _text(line)
        if room.people:
            act(buf, room.people[0], obj, None, C.TO_ALL)


# C: music.c load_songs
def load_songs(game) -> None:
    """Read music.txt: each song is its group and name (strings ending in ~), then lines of lyrics up to a ~ alone,
    and the file ends with #."""
    from quickmud.core.errors import CWouldCrash
    from quickmud.core.log import bug
    from quickmud.entities.game import c_path
    from quickmud.world.areafile.reader import Reader

    channel = game.channel_songs
    for i in range(MAX_GLOBAL + 1):  # "reset global"
        channel[i] = -1

    path = c_path(game, C.MUSIC_FILE)
    if not path.is_file():
        bug("Couldn't open music file, no songs available.", 0)
        raise CWouldCrash("music.c load_songs: fclose (NULL) when music.txt won't open (#83)")
    r = Reader.from_path(path)
    songs = game.songs
    for count in range(MAX_SONGS):
        letter = r.read_letter()
        if letter == "#":
            songs[count].name = None
            return
        r.ungetc()
        songs[count].group = r.read_string()
        songs[count].name = r.read_string()

        lines = 0  # "read lyrics"
        while True:
            letter = r.read_letter()
            if letter == "~":
                songs[count].lines = lines
                break
            r.ungetc()
            if lines >= MAX_LINES:
                bug("Too many lines in a song -- limit is  %d.", MAX_LINES)
                break  # sic (#83): lines isn't set, and the rest of its lyrics are read as the next song
            songs[count].lyrics[lines] = r.read_string_eol()
            lines += 1


# C: music.c do_play
def do_play(ch, argument: str) -> None:
    from quickmud.commands.interp import one_argument
    from quickmud.core.strings import str_cmp, str_prefix
    from quickmud.entities.handler import can_see_obj
    from quickmud.entities.things import add_buf, new_buf
    from quickmud.net.output import page_to_char
    from quickmud.persist.player import capitalize

    game_songs = _game().songs
    channel = _game().channel_songs
    str_, arg = one_argument(argument)

    for juke in ch.in_room.contents:
        if juke.item_type == C.ITEM_JUKEBOX and can_see_obj(ch, juke):
            break
    else:
        juke = None

    if argument == "":
        send_to_char("Play what?\n\r", ch)
        return
    if juke is None:
        send_to_char("You see nothing to play.\n\r", ch)
        return

    if str_cmp(arg, "list"):
        buffer = new_buf()
        argument, arg = one_argument(str_)  # sic (#83): "play list NAME" takes NAME as the option, and lists all
        artist = str_cmp(arg, "artist")
        match = argument != ""
        add_buf(buffer, capitalize("%s has the following songs available:\n\r" % juke.short_descr))
        col = 0
        for song in game_songs:
            if song.name is None:
                break
            if artist and (not match or str_prefix(argument, song.group)):
                buf = "%-39s %-39s\n\r" % (song.group, song.name)
            elif not artist and (not match or str_prefix(argument, song.name)):
                buf = "%-35s " % song.name
            else:
                continue
            add_buf(buffer, buf)
            if not artist:
                col += 1
                if col % 2 == 0:  # non-negative: a count
                    add_buf(buffer, "\n\r")
        if not artist and col % 2 != 0:  # non-negative: a count
            add_buf(buffer, "\n\r")
        page_to_char(buffer.string, ch)
        return

    global_ = False
    if str_cmp(arg, "loud"):
        argument = str_
        global_ = True

    if argument == "":
        send_to_char("Play what?\n\r", ch)
        return
    if (global_ and channel[MAX_GLOBAL] > -1) or (not global_ and juke.value[4] > -1):
        send_to_char("The jukebox is full up right now.\n\r", ch)
        return

    for song in range(MAX_SONGS):
        if game_songs[song].name is None:
            send_to_char("That song isn't available.\n\r", ch)
            return
        if str_prefix(argument, game_songs[song].name):
            break
    else:
        send_to_char("That song isn't available.\n\r", ch)
        return

    send_to_char("Coming right up.\n\r", ch)
    if global_:
        for i in range(1, MAX_GLOBAL + 1):
            if channel[i] < 0:
                if i == 1:
                    channel[0] = -1
                channel[i] = song
                return
    else:
        for i in range(1, 5):
            if juke.value[i] < 0:
                if i == 1:
                    juke.value[0] = -1
                juke.value[i] = song
                return


def _game():
    from quickmud.entities import game as game_module

    return game_module.current
