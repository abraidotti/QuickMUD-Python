/* iocheck: run input and output cases through the C game's own comm.c, for charm_tools port io (abraidotti/charm#28).
 *
 * Linked against the game's object files (comm.c compiled with -Dmain=game_main), like rngcheck and worldcheck.
 * Reads a case script on stdin, one command per line, and prints what each command did, so the Python game can
 * run the same script and the outputs can be compared. A connection is a socketpair: the game's end is the
 * descriptor, and this program reads the other end to see what the game sent.
 *
 * String arguments are the rest of the line, with C escapes: \n \r \t \b \e \\ \s (a space) \xHH. Output escapes
 * backslash, newline, carriage return and anything outside printable ASCII the same way.
 *
 * Commands (n is a number, s a string, k a character or object number, "-" for none):
 *   new n             a connection in state n; it becomes the current one
 *   ansi n | fcommand n | inbuf s | send s | read | out n s | desc s | flush n | recv | show s
 *   buffer            read_from_buffer, then clear incomm as the game loop does once it has run the command
 *   pc | npc s        a player on the current connection, or a mob with that short description; both go in
 *                     the test room, and become the current character
 *   use k             make character k current (and its connection, if it has one)
 *   set FIELD n       a number on the current character (see set_field)
 *   str FIELD s       name, short, prompt or prefix of the current character
 *   room flags sector light | roomname s | sun n
 *   obj n s           an object with those extra flags and short description
 *   char s | page s | prompt | colour k|- codes
 *   act TYPE k k|- k|- s     act_new (s, char, obj arg1, char arg2, TYPE, POS_RESTING)
 *   actt TYPE k s|- s|- s    act_new with text arguments ($t, $T, $d)
 *
 * Part of charm_tools (MIT, tools/LICENSE). It calls the game's code but contains none of it.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/socket.h>
#include "merc.h"
#include "recycle.h"

bool read_from_descriptor (DESCRIPTOR_DATA * d);
void read_from_buffer (DESCRIPTOR_DATA * d);
bool process_output (DESCRIPTOR_DATA * d, bool fPrompt);
void bust_a_prompt (CHAR_DATA * ch);
int colour (char type, CHAR_DATA * ch, char *string);

#define MAXK 32
static DESCRIPTOR_DATA *descs[MAXK];
static int peers[MAXK], ndesc;
static DESCRIPTOR_DATA *d;
static int peer = -1;
static CHAR_DATA *chars[MAXK];
static int nchar;
static CHAR_DATA *ch;
static OBJ_DATA *objs[MAXK];
static int nobj;
static ROOM_INDEX_DATA room;
static AREA_DATA area;
static MOB_INDEX_DATA mob_index;
static OBJ_INDEX_DATA obj_index;

static void esc (const char *s, int n)
{
    int i;
    for (i = 0; i < n; i++)
    {
        unsigned char c = (unsigned char) s[i];
        if (c == '\\') fputs ("\\\\", stdout);
        else if (c == '\n') fputs ("\\n", stdout);
        else if (c == '\r') fputs ("\\r", stdout);
        else if (c >= 32 && c < 127) putchar (c);
        else printf ("\\x%02x", c);
    }
}

static void escs (const char *s)
{
    esc (s, s ? (int) strlen (s) : 0);
}

static int unesc_len;  /* the length of unesc's last result, which can hold NULs */

static char *unesc (const char *s)
{
    static char out[65536];
    int n = 0;
    for (; *s; s++)
    {
        if (*s != '\\') { out[n++] = *s; continue; }
        s++;
        switch (*s)
        {
            case 'n': out[n++] = '\n'; break;
            case 'r': out[n++] = '\r'; break;
            case 't': out[n++] = '\t'; break;
            case 'b': out[n++] = '\b'; break;
            case 'e': out[n++] = '\033'; break;
            case 's': out[n++] = ' '; break;
            case 'x': { char h[3] = { s[1], s[2], 0 }; out[n++] = (char) strtol (h, NULL, 16); s += 2; break; }
            default: out[n++] = *s; break;
        }
    }
    out[n] = '\0';
    unesc_len = n;
    return out;
}

static void recv_all (void)
{
    char buf[65536];
    int n, total = 0;
    while ((n = read (peer, buf + total, sizeof (buf) - total)) > 0)
        total += n;
    printf (" recv=");
    esc (buf, total);
}

static void set_field (const char *f, long v)
{
    if (!strcmp (f, "hit")) ch->hit = v;
    else if (!strcmp (f, "max_hit")) ch->max_hit = v;
    else if (!strcmp (f, "mana")) ch->mana = v;
    else if (!strcmp (f, "max_mana")) ch->max_mana = v;
    else if (!strcmp (f, "move")) ch->move = v;
    else if (!strcmp (f, "max_move")) ch->max_move = v;
    else if (!strcmp (f, "exp")) ch->exp = v;
    else if (!strcmp (f, "gold")) ch->gold = v;
    else if (!strcmp (f, "silver")) ch->silver = v;
    else if (!strcmp (f, "alignment")) ch->alignment = v;
    else if (!strcmp (f, "level")) ch->level = v;
    else if (!strcmp (f, "wait")) ch->wait = v;
    else if (!strcmp (f, "sex")) ch->sex = v;
    else if (!strcmp (f, "act")) ch->act = v;
    else if (!strcmp (f, "comm")) ch->comm = v;
    else if (!strcmp (f, "affected_by")) ch->affected_by = v;
    else if (!strcmp (f, "trust")) ch->trust = v;
    else if (!strcmp (f, "invis_level")) ch->invis_level = v;
    else if (!strcmp (f, "lines")) ch->lines = v;
    else if (!strcmp (f, "position")) ch->position = v;
    else if (!strcmp (f, "connected")) ch->desc->connected = v;
    else { fprintf (stderr, "iocheck: no field %s\n", f); exit (2); }
}

static CHAR_DATA *char_arg (const char *t) { return strcmp (t, "-") ? chars[atoi (t)] : NULL; }
static OBJ_DATA *obj_arg (const char *t) { return strcmp (t, "-") ? objs[atoi (t)] : NULL; }
static char *text_arg (const char *t)
{
    static char bufs[2][4096];
    static int which;
    if (!strcmp (t, "-")) return NULL;
    which = !which;
    strcpy (bufs[which], unesc (t));
    return bufs[which];
}

static int act_type (const char *t)
{
    if (!strcmp (t, "TO_ROOM")) return TO_ROOM;
    if (!strcmp (t, "TO_NOTVICT")) return TO_NOTVICT;
    if (!strcmp (t, "TO_VICT")) return TO_VICT;
    if (!strcmp (t, "TO_CHAR")) return TO_CHAR;
    fprintf (stderr, "iocheck: no act type %s\n", t);
    exit (2);
}

int main (void)
{
    static char line[65536];
    room.vnum = 1;
    room.name = "A Test Room";
    room.area = &area;
    area.name = "Test";
    mob_index.vnum = 1;
    obj_index.vnum = 1;

    while (fgets (line, sizeof (line), stdin))
    {
        char *cmd = line, *rest;
        line[strcspn (line, "\n")] = '\0';
        if (line[0] == '\0' || line[0] == '#')
            continue;
        rest = strchr (line, ' ');
        if (rest) *rest++ = '\0'; else rest = "";
        printf ("%s", cmd);

        if (!strcmp (cmd, "new"))
        {
            int sv[2];
            socketpair (AF_UNIX, SOCK_STREAM, 0, sv);
            fcntl (sv[0], F_SETFL, O_NONBLOCK);
            fcntl (sv[1], F_SETFL, O_NONBLOCK);
            d = new_descriptor ();
            d->descriptor = sv[0];
            d->connected = atoi (rest);
            d->host = str_dup ("test");
            d->next = descriptor_list;
            descriptor_list = d;
            descs[ndesc] = d;
            peers[ndesc++] = peer = sv[1];
            printf (" %d", ndesc - 1);
        }
        else if (!strcmp (cmd, "ansi")) d->ansi = atoi (rest);
        else if (!strcmp (cmd, "fcommand")) d->fcommand = atoi (rest);
        else if (!strcmp (cmd, "inbuf")) strcpy (d->inbuf, unesc (rest));
        else if (!strcmp (cmd, "send"))
        {
            char *s = unesc (rest);
            if (write (peer, s, unesc_len) < 0) perror ("send");
        }
        else if (!strcmp (cmd, "read"))
        {
            printf (" %d inbuf=", read_from_descriptor (d));
            escs (d->inbuf);
            recv_all ();
        }
        else if (!strcmp (cmd, "buffer"))
        {
            read_from_buffer (d);
            printf (" incomm=");
            escs (d->incomm);
            printf (" inlast=");
            escs (d->inlast);
            printf (" repeat=%d inbuf=", d->repeat);
            escs (d->inbuf);
            recv_all ();
            d->incomm[0] = '\0';  /* as the game loop does once it has run the command */
        }
        else if (!strcmp (cmd, "out"))
        {
            int n = atoi (rest);
            char *s = strchr (rest, ' ');
            write_to_buffer (d, s ? unesc (s + 1) : "", n);
            printf (" outtop=%d outsize=%d", d->outtop, d->outsize);
        }
        else if (!strcmp (cmd, "desc")) send_to_desc (unesc (rest), d);
        else if (!strcmp (cmd, "flush"))
        {
            printf (" %d", process_output (d, atoi (rest)));
            recv_all ();
        }
        else if (!strcmp (cmd, "recv")) recv_all ();
        else if (!strcmp (cmd, "show"))
        {
            show_string (d, unesc (rest));
            printf (" more=%d", d->showstr_point != NULL);
        }
        else if (!strcmp (cmd, "pc") || !strcmp (cmd, "npc"))
        {
            ch = new_char ();
            if (!strcmp (cmd, "pc"))
            {
                ch->name = str_dup ("Tester");
                ch->desc = d;
                d->character = ch;
                d->connected = CON_PLAYING;
            }
            else
            {
                ch->act = ACT_IS_NPC;
                ch->pIndexData = &mob_index;
                ch->short_descr = str_dup (unesc (rest));
                ch->name = str_dup ("mob");
            }
            char_to_room (ch, &room);
            chars[nchar++] = ch;
            printf (" %d", nchar - 1);
        }
        else if (!strcmp (cmd, "use"))
        {
            int k = atoi (rest), i;
            ch = chars[k];
            if (ch->desc)
                for (i = 0; i < ndesc; i++)
                    if (descs[i] == ch->desc) { d = descs[i]; peer = peers[i]; }
        }
        else if (!strcmp (cmd, "set"))
        {
            char field[64];
            long v;
            sscanf (rest, "%63s %ld", field, &v);
            set_field (field, v);
        }
        else if (!strcmp (cmd, "str"))
        {
            char *s = strchr (rest, ' ');
            char *v = str_dup (s ? unesc (s + 1) : "");
            if (s) *s = '\0';
            if (!strcmp (rest, "name")) ch->name = v;
            else if (!strcmp (rest, "short")) ch->short_descr = v;
            else if (!strcmp (rest, "prompt")) ch->prompt = v;
            else if (!strcmp (rest, "prefix")) ch->prefix = v;
        }
        else if (!strcmp (cmd, "room"))
        {
            int flags, sector, light;
            sscanf (rest, "%d %d %d", &flags, &sector, &light);
            room.room_flags = flags;
            room.sector_type = sector;
            room.light = light;
        }
        else if (!strcmp (cmd, "roomname")) room.name = str_dup (unesc (rest));
        else if (!strcmp (cmd, "sun")) weather_info.sunlight = atoi (rest);
        else if (!strcmp (cmd, "obj"))
        {
            OBJ_DATA *obj = calloc (1, sizeof (*obj));
            char *s = strchr (rest, ' ');
            obj->extra_flags = atoi (rest);
            obj->item_type = ITEM_TRASH;
            obj->pIndexData = &obj_index;
            obj->short_descr = str_dup (s ? unesc (s + 1) : "");
            objs[nobj++] = obj;
            printf (" %d", nobj - 1);
        }
        else if (!strcmp (cmd, "char")) send_to_char (unesc (rest), ch);
        else if (!strcmp (cmd, "page"))
        {
            page_to_char (unesc (rest), ch);
            printf (" more=%d", d->showstr_point != NULL);
        }
        else if (!strcmp (cmd, "prompt")) bust_a_prompt (ch);
        else if (!strcmp (cmd, "colour"))
        {
            char who[16], codes[256], buf[64];
            int i;
            sscanf (rest, "%15s %255s", who, codes);
            for (i = 0; codes[i]; i++)
            {
                int n = colour (codes[i], char_arg (who), buf);
                printf (" %c=", codes[i]);
                esc (buf, n);
            }
        }
        else if (!strcmp (cmd, "act") || !strcmp (cmd, "actt"))
        {
            char type[32], a[16], b[4096], c[4096];
            int off = 0;
            sscanf (rest, "%31s %15s %4095s %4095s %n", type, a, b, c, &off);
            if (!strcmp (cmd, "act"))
                act_new (unesc (rest + off), char_arg (a), obj_arg (b), char_arg (c), act_type (type),
                         POS_RESTING);
            else
            {
                char *t1 = text_arg (b), *t2 = text_arg (c);
                act_new (unesc (rest + off), char_arg (a), t1, t2, act_type (type), POS_RESTING);
            }
        }
        else
        {
            fprintf (stderr, "iocheck: unknown command %s\n", cmd);
            return 2;
        }
        printf ("\n");
        fflush (stdout);
    }
    return 0;
}
