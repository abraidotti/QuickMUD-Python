/* scenario: play a scenario file through the C game, for charm_tools port scenarios (abraidotti/charm#35).
 *
 * Linked against the game's object files, with comm.c compiled as -Dmain=game_main, as worldcheck is. Nothing
 * here is the game's: it calls the game's own nanny, interpret (through substitute_alias), update_handler and
 * process_output, in the order game_loop_unix calls them, on descriptors whose "socket" is one end of a
 * socketpair. There is no network and no real clock: a pulse is a call, and the clock moves a second every 4.
 *
 * Usage: scenario < FILE (run from the area directory, like the game). Linked with -Wl,--wrap=random, so every
 * random() the game draws is counted and hashed.
 *
 * The scenario format, one thing per line (# starts a comment line):
 *   @seed N              CHARM_SEED (before anything else; default 20261117)
 *   @clock T             current_time at boot (before anything else; default 1763400000)
 *   @updates all|area    which updates update_handler runs (before anything else; default area: CHARM_UPDATES)
 *   @connect NAME        a new connection, called NAME in the output, which becomes the one lines go to
 *   @as NAME             send the following lines to connection NAME
 *   @pulse N             run N pulses with no new input
 *   @mob VNUM ROOM       create_mobile and char_to_room
 *   @obj VNUM ROOM       create_object (level 0) and obj_to_room
 *   @state               dump the characters and objects in every room a connection's character is in
 *   @return              an empty line of input (blank lines are skipped), then one pulse
 *   @file PATH           print a file the game wrote, such as ../player/NAME (relative to the area directory)
 *   anything else        a line of input for the current connection, then one pulse
 *
 * The output, for every step (a line or an @ line):
 *   step N TEXT          what the step was
 *   out NAME "BYTES"     what connection NAME was sent during the step (escaped: see esc)
 *   closed NAME          the game closed connection NAME
 *   file PATH "BYTES"    @file's file, or "file PATH missing"
 *   rng DRAWS HASH       random() calls so far, and an FNV-1a hash of every value they returned
 *   state ...            @state's lines
 *
 * A comment line "# expect: stopped NotPorted" says the Python game is to stop with NotPorted in this scenario
 * (charm.testing.scenario compares only what comes before). The C ignores it, as it does every comment.
 *
 * Part of charm_tools (MIT, tools/LICENSE). It calls the game's code but contains none of it.
 */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>
#include "merc.h"
#include "recycle.h"

void boot_db (void);                                /* db.c */
void qmconfig_read (void);                          /* act_wiz.c */
void update_handler (void);                         /* update.c */
void nanny (DESCRIPTOR_DATA * d, char *argument);  /* nanny.c */
void read_from_buffer (DESCRIPTOR_DATA * d);        /* comm.c */
bool process_output (DESCRIPTOR_DATA * d, bool fPrompt);
void stop_idling (CHAR_DATA * ch);
void show_string (struct descriptor_data *d, char *input);
void string_add (CHAR_DATA * ch, char *argument);   /* string.c */
bool run_olc_editor (DESCRIPTOR_DATA * d);          /* olc.c */
void substitute_alias (DESCRIPTOR_DATA * d, char *argument);  /* alias.c */
extern int mud_ansiprompt, mud_ansicolor;          /* comm.c */

/* -- random(), counted ------------------------------------------------------------------------------------- */

long __real_random (void);
static unsigned long draws;
static unsigned int rng_hash = 2166136261u;

long __wrap_random (void)
{
    long v = __real_random ();
    int i;

    draws++;
    for (i = 0; i < 4; i++)  /* FNV-1a over the value's 4 low bytes, little end first */
    {
        rng_hash ^= (unsigned int) ((v >> (8 * i)) & 0xff);
        rng_hash *= 16777619u;
    }
    return v;
}

/* -- connections ------------------------------------------------------------------------------------------- */

#define MAX_CONN 16

struct conn
{
    char name[32];
    DESCRIPTOR_DATA *d;
    int peer;      /* our end of the socketpair: what the game writes to d->descriptor arrives here */
    bool closed;
};

static struct conn conns[MAX_CONN];
static int nconn, current = -1;
static long pulses;
static time_t start_time;

static int find_conn (const char *name)
{
    int i;
    for (i = 0; i < nconn; i++)
        if (!strcmp (conns[i].name, name))
            return i;
    fprintf (stderr, "scenario: no connection called %s\n", name);
    exit (2);
}

static bool listed (DESCRIPTOR_DATA * d)
{
    DESCRIPTOR_DATA *x;
    for (x = descriptor_list; x != NULL; x = x->next)
        if (x == d)
            return TRUE;
    return FALSE;
}

static void connect_as (const char *name)
{
    int sv[2];
    DESCRIPTOR_DATA *d;
    struct conn *c;

    if (nconn == MAX_CONN || socketpair (AF_UNIX, SOCK_STREAM, 0, sv) < 0)
    {
        fprintf (stderr, "scenario: can't connect %s\n", name);
        exit (2);
    }
    fcntl (sv[1], F_SETFL, O_NONBLOCK);
    d = new_descriptor ();
    d->descriptor = sv[0];
    d->connected = mud_ansiprompt ? CON_ANSI : CON_GET_NAME;
    d->ansi = mud_ansicolor;
    d->host = str_dup ("scenario");
    d->next = descriptor_list;
    descriptor_list = d;
    c = &conns[nconn];
    snprintf (c->name, sizeof c->name, "%s", name);
    c->d = d;
    c->peer = sv[1];
    c->closed = FALSE;
    current = nconn++;
    /* The greeting, as init_descriptor sends it. */
    if (!mud_ansiprompt)
    {
        extern char *help_greeting;
        send_to_desc (help_greeting[0] == '.' ? help_greeting + 1 : help_greeting, d);
    }
}

/* -- the pulse: game_loop_unix's input, update and output steps, without select() -------------------------- */

static void pulse (void)
{
    DESCRIPTOR_DATA *d, *d_next;

    for (d = descriptor_list; d != NULL; d = d_next)
    {
        d_next = d->next;
        d->fcommand = FALSE;
        if (d->character != NULL && d->character->daze > 0)
            --d->character->daze;
        if (d->character != NULL && d->character->wait > 0)
        {
            --d->character->wait;
            continue;
        }
        read_from_buffer (d);
        if (d->incomm[0] != '\0')
        {
            d->fcommand = TRUE;
            stop_idling (d->character);
            if (d->showstr_point)
                show_string (d, d->incomm);
            else if (d->pString)
                string_add (d->character, d->incomm);
            else if (d->connected == CON_PLAYING)
            {
                if (!run_olc_editor (d))
                    substitute_alias (d, d->incomm);
            }
            else
                nanny (d, d->incomm);
            d->incomm[0] = '\0';
        }
    }
    update_handler ();
    for (d = descriptor_list; d != NULL; d = d_next)
    {
        d_next = d->next;
        if (d->fcommand || d->outtop > 0)
        {
            if (!process_output (d, TRUE))
            {
                if (d->character != NULL && d->connected == CON_PLAYING)
                    save_char_obj (d->character);
                d->outtop = 0;
                close_socket (d);
            }
        }
    }
    pulses++;
    current_time = start_time + pulses / PULSE_PER_SECOND;
}

/* -- output ------------------------------------------------------------------------------------------------ */

/* Bytes on one line: \\, \", \n, \r, and \xNN for anything outside printable ASCII. */
static void esc (const unsigned char *s, size_t n)
{
    size_t i;
    putchar ('"');
    for (i = 0; i < n; i++)
    {
        if (s[i] == '\\') fputs ("\\\\", stdout);
        else if (s[i] == '"') fputs ("\\\"", stdout);
        else if (s[i] == '\n') fputs ("\\n", stdout);
        else if (s[i] == '\r') fputs ("\\r", stdout);
        else if (s[i] < 32 || s[i] > 126) printf ("\\x%02x", s[i]);
        else putchar (s[i]);
    }
    putchar ('"');
}

static void collect (void)
{
    static unsigned char buf[65536];
    int i;

    for (i = 0; i < nconn; i++)
    {
        struct conn *c = &conns[i];
        size_t got = 0;
        ssize_t n;

        if (c->closed)
            continue;
        while (got < sizeof buf && (n = read (c->peer, buf + got, sizeof buf - got)) > 0)
            got += n;
        if (got > 0)
        {
            printf ("out %s ", c->name);
            esc (buf, got);
            putchar ('\n');
        }
        if (!listed (c->d))  /* close_socket took it off the list (and closed its end) */
        {
            printf ("closed %s\n", c->name);
            c->closed = TRUE;
            close (c->peer);
        }
    }
    printf ("rng %lu %08x\n", draws, rng_hash);
}

static void dump_obj (const char *where, OBJ_DATA * obj, int depth)
{
    OBJ_DATA *in;
    printf ("state %*sobj %s %d wear %d timer %d cost %d values %d %d %d %d %d\n", depth * 2, "", where,
            obj->pIndexData->vnum, obj->wear_loc, obj->timer, obj->cost, obj->value[0], obj->value[1],
            obj->value[2], obj->value[3], obj->value[4]);
    for (in = obj->contains; in != NULL; in = in->next_content)
        dump_obj ("in", in, depth + 1);
}

static void state (void)
{
    ROOM_INDEX_DATA *seen[MAX_CONN];
    int nseen = 0, i, j;

    for (i = 0; i < nconn; i++)
    {
        ROOM_INDEX_DATA *room;
        CHAR_DATA *ch;
        OBJ_DATA *obj;
        AFFECT_DATA *af;

        if (conns[i].closed || !listed (conns[i].d) || conns[i].d->character == NULL
            || (room = conns[i].d->character->in_room) == NULL)
            continue;
        for (j = 0; j < nseen && seen[j] != room; j++)
            ;
        if (j < nseen)
            continue;
        seen[nseen++] = room;
        printf ("state room %d light %d people", room->vnum, room->light);
        for (ch = room->people; ch != NULL; ch = ch->next_in_room)
            printf (" %s", IS_NPC (ch) ? "mob" : "player");
        putchar ('\n');
        for (ch = room->people; ch != NULL; ch = ch->next_in_room)
        {
            printf ("state char %s %d pos %d hit %d/%d mana %d/%d move %d/%d wait %d daze %d exp %d gold %ld "
                    "silver %ld act %ld affected_by %ld\n", IS_NPC (ch) ? "mob" : ch->name,
                    IS_NPC (ch) ? ch->pIndexData->vnum : ch->level, ch->position, ch->hit, ch->max_hit,
                    ch->mana, ch->max_mana, ch->move, ch->max_move, ch->wait, ch->daze, ch->exp, ch->gold,
                    ch->silver, ch->act, ch->affected_by);
            for (af = ch->affected; af != NULL; af = af->next)
                printf ("state   affect %d level %d duration %d location %d modifier %d bitvector %d\n", af->type,
                        af->level, af->duration, af->location, af->modifier, af->bitvector);
            for (obj = ch->carrying; obj != NULL; obj = obj->next_content)
                dump_obj ("carried", obj, 1);
        }
        for (obj = room->contents; obj != NULL; obj = obj->next_content)
            dump_obj ("floor", obj, 0);
    }
}

/* -- the script -------------------------------------------------------------------------------------------- */

static void chomp (char *s)
{
    size_t n = strlen (s);
    while (n > 0 && (s[n - 1] == '\n' || s[n - 1] == '\r'))
        s[--n] = '\0';
}

int main (void)
{
    char line[MAX_STRING_LENGTH];
    const char *seed = "20261117", *updates = "area";
    long clock = 1763400000;
    bool booted = FALSE;
    long step = 0;

    while (fgets (line, sizeof line, stdin) != NULL)
    {
        char word[32];
        long a = 0, b = 0;

        chomp (line);
        if (line[0] == '#' || line[0] == '\0')
            continue;
        if (!booted)
        {
            static char seedbuf[32], updbuf[16];
            if (sscanf (line, "@seed %31s", seedbuf) == 1) { seed = seedbuf; continue; }
            if (sscanf (line, "@clock %ld", &clock) == 1) continue;
            if (sscanf (line, "@updates %15s", updbuf) == 1) { updates = updbuf; continue; }
            setenv ("CHARM_SEED", seed, 1);
            if (!strcmp (updates, "area"))
                setenv ("CHARM_UPDATES", "area", 1);
            current_time = start_time = (time_t) clock;
            if ((fpReserve = fopen (NULL_FILE, "r")) == NULL)  /* main reserves one, which file code swaps */
            {
                perror (NULL_FILE);
                return 2;
            }
            qmconfig_read ();
            boot_db ();
            booted = TRUE;
            printf ("boot seed %s clock %ld updates %s\n", seed, clock, updates);
            collect ();
        }
        printf ("step %ld ", ++step);
        esc ((unsigned char *) line, strlen (line));
        putchar ('\n');
        if (line[0] != '@' || !strcmp (line, "@return"))
        {
            DESCRIPTOR_DATA *d;
            if (line[0] == '@')
                line[0] = '\0';  /* @return: the input is the empty line */
            if (current < 0 || conns[current].closed || !listed (d = conns[current].d))
            {
                fprintf (stderr, "scenario: step %ld: no open connection to send to\n", step);
                return 2;
            }
            if (strlen (d->inbuf) + strlen (line) + 2 >= sizeof d->inbuf)
            {
                fprintf (stderr, "scenario: step %ld: the input buffer is full\n", step);
                return 2;
            }
            strcat (d->inbuf, line);
            strcat (d->inbuf, "\n");
            pulse ();
        }
        else if (sscanf (line, "@connect %31s", word) == 1)
            connect_as (word);
        else if (sscanf (line, "@as %31s", word) == 1)
            current = find_conn (word);
        else if (sscanf (line, "@pulse %ld", &a) == 1)
            while (a-- > 0)
                pulse ();
        else if (sscanf (line, "@mob %ld %ld", &a, &b) == 2)
        {
            CHAR_DATA *mob = create_mobile (get_mob_index (a));
            char_to_room (mob, get_room_index (b));
        }
        else if (sscanf (line, "@obj %ld %ld", &a, &b) == 2)
            obj_to_room (create_object (get_obj_index (a), 0), get_room_index (b));
        else if (!strcmp (line, "@state"))
            state ();
        else if (!strncmp (line, "@file ", 6))
        {
            static unsigned char fbuf[262144];
            FILE *fp = fopen (line + 6, "rb");
            if (fp == NULL)
                printf ("file %s missing\n", line + 6);
            else
            {
                size_t n = fread (fbuf, 1, sizeof fbuf, fp);
                fclose (fp);
                printf ("file %s ", line + 6);
                esc (fbuf, n);
                putchar ('\n');
            }
        }
        else
        {
            fprintf (stderr, "scenario: step %ld: unknown line %s\n", step, line);
            return 2;
        }
        collect ();
        fflush (stdout);
    }
    return 0;
}
