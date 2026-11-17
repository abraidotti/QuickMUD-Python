/* rngcheck: print streams of the C game's own random numbers, for charm_tools port rng (abraidotti/charm#23).
 *
 * Linked against the game's object files, with comm.c compiled as -Dmain=game_main, so these are the game's real
 * init_mm, number_mm, number_range and the rest, not copies. Each stream reseeds through init_mm with CHARM_SEED,
 * so the seeding path is tested too.
 *
 * Usage: rngcheck COUNT SEED...
 * Output, per seed and stream: "stream SEED NAME ARGS" (ARGS is how each draw's arguments cycle; "-" for none),
 * then "values V1 V2 ...". init_mm's log line goes to stderr.
 *
 * Part of charm_tools (MIT, tools/LICENSE). It calls the game's code but contains none of it.
 */
#include <stdio.h>
#include <stdlib.h>
#include "merc.h"

void init_mm (void);  /* db.c; not in a header */

static const int ranges[][2] = { {0, 0}, {1, 1}, {1, 6}, {0, 99}, {-5, 5}, {1, 1000}, {3, 2}, {1, 2}, {0, 1 << 20} };
static const int fuzzy[] = { 0, 1, 2, 5, 10, 100 };
static const int bits[] = { 0, 1, 2, 3, 4, 5, 6, 7, 8 };
static const int dices[][2] = { {0, 6}, {1, 0}, {3, 1}, {1, 6}, {2, 8}, {3, 6}, {10, 10} };

#define N(a) ((int) (sizeof (a) / sizeof (a)[0]))

static void seed (const char *s)
{
    setenv ("CHARM_SEED", s, 1);
    init_mm ();
}

static void header (const char *s, const char *name)
{
    printf ("stream %s %s", s, name);
}

int main (int argc, char **argv)
{
    int count, a, i;

    if (argc < 3)
    {
        fprintf (stderr, "usage: %s COUNT SEED...\n", argv[0]);
        return 2;
    }
    count = atoi (argv[1]);
    for (a = 2; a < argc; a++)
    {
        const char *s = argv[a];

        seed (s); header (s, "random"); printf (" -\nvalues");
        for (i = 0; i < count; i++) printf (" %ld", random ());
        printf ("\n");

        seed (s); header (s, "number_mm"); printf (" -\nvalues");
        for (i = 0; i < count; i++) printf (" %ld", number_mm ());
        printf ("\n");

        seed (s); header (s, "number_range");
        for (i = 0; i < N (ranges); i++) printf (" %d,%d", ranges[i][0], ranges[i][1]);
        printf ("\nvalues");
        for (i = 0; i < count; i++) printf (" %d", number_range (ranges[i % N (ranges)][0], ranges[i % N (ranges)][1]));
        printf ("\n");

        seed (s); header (s, "number_percent"); printf (" -\nvalues");
        for (i = 0; i < count; i++) printf (" %d", number_percent ());
        printf ("\n");

        seed (s); header (s, "number_door"); printf (" -\nvalues");
        for (i = 0; i < count; i++) printf (" %d", number_door ());
        printf ("\n");

        seed (s); header (s, "number_bits");
        for (i = 0; i < N (bits); i++) printf (" %d", bits[i]);
        printf ("\nvalues");
        for (i = 0; i < count; i++) printf (" %d", number_bits (bits[i % N (bits)]));
        printf ("\n");

        seed (s); header (s, "number_fuzzy");
        for (i = 0; i < N (fuzzy); i++) printf (" %d", fuzzy[i]);
        printf ("\nvalues");
        for (i = 0; i < count; i++) printf (" %d", number_fuzzy (fuzzy[i % N (fuzzy)]));
        printf ("\n");

        seed (s); header (s, "dice");
        for (i = 0; i < N (dices); i++) printf (" %d,%d", dices[i][0], dices[i][1]);
        printf ("\nvalues");
        for (i = 0; i < count; i++) printf (" %d", dice (dices[i % N (dices)][0], dices[i % N (dices)][1]));
        printf ("\n");
    }
    return 0;
}
